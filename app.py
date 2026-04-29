import io
import json
import logging
import os
import re
import shutil
import uuid
import zipfile
import csv
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    redirect,
    request,
    send_file,
    send_from_directory,
    url_for,
)
from flask_cors import CORS
from pathlib import Path
from urllib.parse import quote
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

from config import Config
from utils.image_augment import allowed_op_ids, build_augment_zip, list_augment_options
from utils.image_converter import ImageConverter
from utils.model_converter import ModelConverter
from utils.news_summarizer import NewsSummarizer
from utils.ai_text_cleaner import (
    build_openai_client,
    clean_text,
    export_optional_deps_status,
    generate_content,
    generate_file_fill,
    write_docx_bytes,
    write_pdf_bytes,
    write_xlsx_smart_bytes,
)
from utils.aspose_docx_processor import (
    docx_has_processable_blocks,
    ensure_aspose_installed,
    plain_text_preview_from_docx_bytes,
)
from utils.office_extract import extract_office_text, sniff_office_kind
from utils.text_format import decode_text_file_bytes, sanitize_xml_compatible_text
from openai import APIError, RateLimitError
from utils.dataset_tools import (
    build_output_zip,
    collect_items,
    detect_annotation_format,
    safe_unzip_bytes,
    split_items,
    DatasetItem,
)
from utils.baidu_image_scraper import scrape_baidu_image_urls
from utils.image_dataset_cleaner import CleanConfig, clean_images, write_report_jsonl
from utils.mm_clean_qwen import build_modelscope_mm_client, qwen_mm_clean_one, SUPPORTED_MM_MODELS
from utils.aspose_doc_merge import convert_doc_aspose, merge_docs_aspose
from utils.excel_merge import MergeXlsxOptions, merge_xlsx_bytes
from utils.labelimg_launcher import launch_labelimg
from utils.kb_ingest_pipeline import (
    DEFAULT_KB_ROOTS,
    assess_and_fix_one,
    assess_roots_and_write_report,
    chunk_stable_id,
    chunk_text,
    kb_bucket_for_path,
    scan_ai_folder,
)
from utils.kb_vector_store import get_or_create_collection, query as kb_query, upsert_texts
from utils.kb_embeddings import build_modelscope_embed_client, embed_texts, get_embed_model
from utils.ai_tutor_prompt import AI_TUTOR_API_MCP_APPENDIX, AI_TUTOR_SYSTEM_PROMPT

from utils.modelscope_ai import (
    chat_completion,
    fetch_image_as_data_url,
    get_image_task,
    start_image_generation,
)
from utils.auth_db import (
    check_email_code,
    check_password_reset_code,
    create_user,
    init_auth_db,
    get_user_by_email,
    get_user_by_id,
    seed_default_user,
    update_user_password,
    upsert_email_code,
    upsert_password_reset_code,
    verify_login,
)
from utils.community_db import (
    CATEGORIES,
    init_community_db,
    create_post as db_create_post,
    list_posts as db_list_posts,
    get_post as db_get_post,
    delete_post as db_delete_post,
    create_reply as db_create_reply,
    list_replies as db_list_replies,
)
from utils.email_sender import send_qq_email
import hashlib
import time
import threading
from datetime import date, datetime

logger = logging.getLogger(__name__)

# 统一控制台日志格式（含新闻爬取与总结）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)

# 加载环境变量（显式指向项目根目录 .env，避免从其他工作目录启动时读不到）
_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=False)

from utils.modelscope_runtime_config import load_and_apply_runtime_modelscope

load_and_apply_runtime_modelscope()

# 设置 NEWS_DEBUG=1 可输出每条正文的请求耗时等 DEBUG 日志
if os.getenv("NEWS_DEBUG", "").strip().lower() in ("1", "true", "yes", "on"):
    logging.getLogger("utils.softunis_scraper").setLevel(logging.DEBUG)
    logging.getLogger("utils.tencent_news_scraper").setLevel(logging.DEBUG)
    logging.getLogger("utils.news_summarizer").setLevel(logging.DEBUG)
    logger.info("NEWS_DEBUG 已开启：新闻爬取/总结模块输出 DEBUG 级别日志")

app = Flask(__name__)
app.config.from_object(Config)
CORS(app, resources={r"/api/*": {"origins": "*"}})
Config.init_app(app)
init_auth_db()
seed_default_user()
init_community_db()

from flask import session  # noqa: E402

# 初始化图片转换器和音频修复器（Python 3.13+ 无 audioop 时 pydub 不可用，跳过音频功能）
converter = ImageConverter(app.config['UPLOAD_FOLDER'], app.config['DOWNLOAD_FOLDER'])
audio_repair = None
try:
    from utils.audio_repair import AudioRepair

    audio_repair = AudioRepair()
except ModuleNotFoundError as e:
    logger.warning(
        "音频修复已禁用（缺少依赖）: %s。Python 3.13+ 请执行: pip install audioop-lts",
        e,
    )
except Exception as e:
    logger.warning("音频修复初始化失败，已禁用: %s", e)

# 初始化模型转换器（可选，如果依赖不完整会失败但不会阻止应用启动）
try:
    model_converter = ModelConverter(app.config['UPLOAD_FOLDER'], app.config['DOWNLOAD_FOLDER'])
except Exception as e:
    logger.warning("模型转换器初始化失败：%s", e)
    logger.info("图片和音频转换功能仍然可用")
    model_converter = None

# 初始化每日必读资讯（软盟 AI 列表 + 总结）
try:
    news_summarizer = NewsSummarizer()
    logger.info("每日必读资讯模块初始化成功")
except Exception as e:
    logger.warning("每日必读资讯模块初始化失败：%s", e)
    news_summarizer = NewsSummarizer()


def _refresh_news_summarizer():
    """ModelScope 配置变更后重建必读资讯模块内 OpenAI 客户端"""
    global news_summarizer
    try:
        news_summarizer = NewsSummarizer()
        return True, ""
    except Exception as e:
        logger.exception("刷新 NewsSummarizer 失败")
        return False, str(e)


NEWS_PUSHPLUS_FILE = Path(__file__).resolve().parent / "instance" / "news_pushplus.json"
NEWS_PUSHPLUS_DEFAULT = {
    "enabled": False,
    "token": "",
    "feed": "softunis",
    "softunis_tag": "ai",
    "qq_channel": "tech",
    "limit": 5,
    "use_ai": True,
    "push_time": "08:30",
    "last_push_date": "",
}
_news_pushplus_lock = threading.Lock()


def _news_pushplus_load() -> dict:
    cfg = dict(NEWS_PUSHPLUS_DEFAULT)
    try:
        if NEWS_PUSHPLUS_FILE.is_file():
            raw = json.loads(NEWS_PUSHPLUS_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg.update(raw)
    except Exception:
        logger.exception("读取 PushPlus 配置失败")
    return cfg


def _news_pushplus_save(cfg: dict) -> None:
    p = NEWS_PUSHPLUS_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_news_markdown(result: dict, cfg: dict) -> str:
    articles = result.get("articles") or []
    summary = (result.get("combined_summary") or result.get("summary") or "").strip()
    feed = cfg.get("feed", "softunis")
    channel = cfg.get("softunis_tag") if feed == "softunis" else cfg.get("qq_channel")
    lines = [
        f"# 每日必读资讯（{datetime.now().strftime('%Y-%m-%d')}）",
        "",
        f"- 来源：{feed}",
        f"- 分类：{channel or '-'}",
        f"- 篇数：{len(articles)}",
        "",
    ]
    if summary:
        lines.extend(["## AI 简报", summary, ""])
    if articles:
        lines.append("## 文章详情")
        for i, a in enumerate(articles, 1):
            title = (a.get("title") or "").strip() or f"第{i}篇"
            url = (a.get("url") or "").strip()
            source = (a.get("source") or "").strip()
            art_summary = (a.get("summary") or "").strip()
            description = (a.get("description") or "").strip()
            body = art_summary or description

            # 标题行
            header = f"### {i}. {title}" if not url else f"### {i}. [{title}]({url})"
            if source:
                header += f"  `{source}`"
            lines.append(header)

            # 分段落正文
            if body:
                for para in body.split("\n"):
                    para = para.strip()
                    if para:
                        lines.append(para)
                lines.append("")
            else:
                lines.append("")
    return "\n".join(lines)


def _pushplus_send(token: str, title: str, content: str) -> None:
    resp = requests.post(
        "http://www.pushplus.plus/send",
        json={
            "token": token,
            "title": title,
            "content": content,
            "template": "markdown",
        },
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    if isinstance(data, dict) and data.get("code") not in (None, 200):
        raise RuntimeError(f"PushPlus 返回异常: {data.get('msg') or data}")


def _pushplus_news_once(cfg: dict) -> dict:
    feed = (cfg.get("feed") or "softunis").strip().lower()
    if feed not in ("softunis", "tencent"):
        feed = "softunis"
    try:
        limit = int(cfg.get("limit") or 5)
    except (TypeError, ValueError):
        limit = 5
    if limit not in (1, 3, 5, 10):
        limit = 5
    use_ai = bool(cfg.get("use_ai", True))
    qq_channel = (cfg.get("qq_channel") or "tech").strip().lower()
    softunis_tag = (cfg.get("softunis_tag") or "ai").strip().lower()
    result = news_summarizer.search_and_summarize(
        limit=limit,
        use_ai=use_ai,
        feed=feed,
        qq_channel=qq_channel if feed == "tencent" else None,
        softunis_tag=softunis_tag if feed == "softunis" else None,
    )
    if not result.get("success"):
        raise RuntimeError(result.get("message") or result.get("error") or "资讯拉取失败")

    # 为推送生成逐篇摘要（search_and_summarize 返回的 articles 无 summary）
    raw_articles = result.get("articles") or []
    if use_ai and raw_articles:
        try:
            summarized = news_summarizer.batch_summarize(raw_articles, use_ai=True)
            result["articles"] = summarized
        except Exception:
            logger.warning("PushPlus 推送逐篇摘要生成失败，使用文章列表原文")

    content = _build_news_markdown(result, cfg)
    title = f"每日必读资讯 {datetime.now().strftime('%Y-%m-%d')}"
    _pushplus_send((cfg.get("token") or "").strip(), title, content)
    return result


def _news_pushplus_scheduler_loop():
    logger.info("PushPlus 定时推送线程已启动")
    while True:
        try:
            with _news_pushplus_lock:
                cfg = _news_pushplus_load()
                enabled = bool(cfg.get("enabled"))
                token = (cfg.get("token") or "").strip()
                push_time = (cfg.get("push_time") or "08:30").strip()
                today = date.today().isoformat()
                now_hm = datetime.now().strftime("%H:%M")
                should_push = (
                    enabled
                    and bool(token)
                    and push_time == now_hm
                    and cfg.get("last_push_date") != today
                )
                if should_push:
                    _pushplus_news_once(cfg)
                    cfg["last_push_date"] = today
                    _news_pushplus_save(cfg)
                    logger.info("PushPlus 每日资讯推送成功: %s", today)
        except Exception:
            logger.exception("PushPlus 定时推送执行失败")
        time.sleep(20)


def _maybe_start_news_pushplus_scheduler():
    """
    debug 模式下 reloader 会启动两次进程，仅在主子进程中启动线程。
    """
    if os.getenv("FLASK_DEBUG", "").strip().lower() in ("1", "true", "yes", "on"):
        if os.getenv("WERKZEUG_RUN_MAIN") != "true":
            return
    th = threading.Thread(target=_news_pushplus_scheduler_loop, daemon=True, name="news-pushplus")
    th.start()


_maybe_start_news_pushplus_scheduler()


@app.route("/api/settings/modelscope", methods=["GET"])
def modelscope_settings_get():
    from utils.modelscope_runtime_config import get_public_settings

    return jsonify({"success": True, **get_public_settings()})


@app.route("/api/settings/modelscope", methods=["POST"])
def modelscope_settings_post():
    from utils.modelscope_runtime_config import apply_runtime_payload, get_public_settings

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"success": False, "error": "请提交 JSON"}), 400
    try:
        apply_runtime_payload(payload)
    except Exception as e:
        logger.exception("保存 ModelScope 配置")
        return jsonify({"success": False, "error": str(e)}), 500

    ok, err = _refresh_news_summarizer()
    return jsonify(
        {
            "success": True,
            "news_summarizer_refreshed": ok,
            "refresh_error": err or None,
            **get_public_settings(),
        }
    )


# ==================== 数据标注划分（标注转换 + 数据集划分） ====================

@app.route("/api/dataset/process", methods=["POST"])
def dataset_process():
    """
    multipart:
      - file: .zip
      - in_format: auto|yolo|coco|voc
      - out_format: yolo|coco|voc
      - train/val/test: float
      - seed: int
      - name: output zip base name (optional)
    """
    try:
        if not _require_login():
            return _auth_required_json()
        uf = request.files.get("file")
        if not uf or not uf.filename:
            return jsonify({"success": False, "error": "请上传 .zip 数据集"}), 400
        if not uf.filename.lower().endswith(".zip"):
            return jsonify({"success": False, "error": "仅支持 .zip 压缩包"}), 400
        in_fmt = (request.form.get("in_format") or "auto").strip().lower()
        out_fmt = (request.form.get("out_format") or "yolo").strip().lower()
        train = float(request.form.get("train") or "0.8")
        val = float(request.form.get("val") or "0.2")
        test = float(request.form.get("test") or "0")
        seed = int(float(request.form.get("seed") or "42"))
        name = (request.form.get("name") or "").strip() or "dataset_out"

        raw = uf.read()
        tmp_id = uuid.uuid4().hex
        tmp_dir = Path(app.config["UPLOAD_FOLDER"]) / f"_dataset_{tmp_id}"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            safe_unzip_bytes(raw, tmp_dir)
            detected = detect_annotation_format(tmp_dir)
            if in_fmt == "auto":
                in_fmt = detected
            if in_fmt not in ("yolo", "coco", "voc"):
                return jsonify(
                    {
                        "success": False,
                        "error": f"无法识别输入标注格式（detect={detected}），请手动选择 YOLO/COCO/VOC",
                    }
                ), 400
            if out_fmt not in ("yolo", "coco", "voc"):
                out_fmt = "yolo"

            items = collect_items(tmp_dir, in_format=in_fmt)
            splits = split_items(items, train, val, test, seed=seed)
            payload = build_output_zip(tmp_dir, splits, out_format=out_fmt, in_format=in_fmt)
        finally:
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

        dl_name = f"{secure_filename(name) or 'dataset_out'}.zip"
        return send_file(
            io.BytesIO(payload),
            mimetype="application/zip",
            as_attachment=True,
            download_name=dl_name,
        )
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.exception("dataset process")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/dataset/process-local", methods=["POST"])
def dataset_process_local():
    """
    使用本地目录（LabelImg 标注后的目录）进行格式转换和数据集划分
    JSON:
      - images_dir: 图片目录（必填）
      - labels_dir: 标注目录（必填，如果不填则从images_dir推断）
      - in_format: auto|yolo|coco|voc
      - out_format: yolo|coco|voc
      - train/val/test: float
      - seed: int
      - name: output zip base name (optional)
    """
    try:
        if not _require_login():
            return _auth_required_json()
        data = request.get_json(silent=True) or {}
        images_dir = (data.get("images_dir") or "").strip()
        labels_dir = (data.get("labels_dir") or "").strip() or None
        in_fmt = (data.get("in_format") or "auto").strip().lower()
        out_fmt = (data.get("out_format") or "yolo").strip().lower()
        train = float(data.get("train") or "0.8")
        val = float(data.get("val") or "0.2")
        test = float(data.get("test") or "0")
        seed = int(float(data.get("seed") or "42"))
        name = (data.get("name") or "").strip() or "dataset_out"

        if not images_dir:
            return jsonify({"success": False, "error": "请填写图片目录"}), 400

        # 验证目录存在
        img_dir = Path(images_dir).expanduser().resolve()
        if not img_dir.exists():
            return jsonify({"success": False, "error": f"图片目录不存在：{img_dir}"}), 400
        if not img_dir.is_dir():
            return jsonify({"success": False, "error": f"图片路径不是目录：{img_dir}"}), 400

        # 确定标注目录
        if labels_dir:
            lbl_dir = Path(labels_dir).expanduser().resolve()
        else:
            # 尝试常见的标注目录名称
            possible_names = ["labels", "Annotations", "annotations", "label"]
            lbl_dir = None
            for pname in possible_names:
                candidate = img_dir.parent / pname
                if candidate.exists() and candidate.is_dir():
                    lbl_dir = candidate
                    break
            if not lbl_dir:
                return jsonify({
                    "success": False,
                    "error": f"未找到标注目录，请手动指定 labels_dir\n尝试过的目录：{', '.join(str(img_dir.parent / p) for p in possible_names)}"
                }), 400

        if not lbl_dir.exists():
            return jsonify({"success": False, "error": f"标注目录不存在：{lbl_dir}"}), 400

        # 自动检测输入格式
        detected = detect_annotation_format(lbl_dir)
        if in_fmt == "auto":
            in_fmt = detected
        if in_fmt not in ("yolo", "coco", "voc"):
            return jsonify(
                {
                    "success": False,
                    "error": f"无法识别输入标注格式（detect={detected}），请手动选择 YOLO/COCO/VOC",
                }
            ), 400
        if out_fmt not in ("yolo", "coco", "voc"):
            out_fmt = "yolo"

        # 创建临时目录，复制图片和标注文件到标准结构
        tmp_id = uuid.uuid4().hex
        tmp_dir = Path(app.config["UPLOAD_FOLDER"]) / f"_dataset_local_{tmp_id}"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            # 创建 images 和 labels 目录
            tmp_img_dir = tmp_dir / "images"
            tmp_lbl_dir = tmp_dir / "labels"
            tmp_img_dir.mkdir(parents=True, exist_ok=True)
            tmp_lbl_dir.mkdir(parents=True, exist_ok=True)

            # 构建图片名到标注名的映射
            img_to_label: Dict[str, Optional[Path]] = {}
            
            # 遍历图片目录，找到对应的标注文件
            img_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
            label_ext = ".txt" if in_fmt == "yolo" else (".xml" if in_fmt == "voc" else ".json")
            
            for img_path in sorted(img_dir.iterdir()):
                if img_path.is_file() and img_path.suffix.lower() in img_exts:
                    stem = img_path.stem
                    # 复制图片到 images/
                    shutil.copy2(img_path, tmp_img_dir / img_path.name)
                    # 查找对应标注文件
                    label_path = lbl_dir / f"{stem}{label_ext}"
                    if label_path.exists():
                        img_to_label[img_path.name] = label_path
                        # 复制标注文件
                        shutil.copy2(label_path, tmp_lbl_dir / label_path.name)
                    else:
                        img_to_label[img_path.name] = None

            # 检查找到多少有标注的图片
            labeled_count = sum(1 for v in img_to_label.values() if v is not None)
            logger.info(f"找到 {len(img_to_label)} 张图片，其中 {labeled_count} 张有标注")

            if labeled_count == 0:
                return jsonify({"success": False, "error": f"未找到标注文件（目录：{lbl_dir}，格式：{in_fmt}）"}), 400

            # 使用 collect_items 收集项目
            items = collect_items(tmp_dir, in_format=in_fmt)
            
            if not items:
                return jsonify({"success": False, "error": "未找到匹配的标注文件"}), 400

            # 数据集划分
            splits = split_items(items, train, val, test, seed=seed)

            # 生成输出 zip
            payload = build_output_zip(tmp_dir, splits, out_format=out_fmt, in_format=in_fmt)
        finally:
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

        dl_name = f"{secure_filename(name) or 'dataset_out'}.zip"
        return send_file(
            io.BytesIO(payload),
            mimetype="application/zip",
            as_attachment=True,
            download_name=dl_name,
        )
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.exception("dataset process-local")
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== SSE 实时进度推送（数据集制作） ====================

# 全局进度存储（简单实现，生产环境建议用 Redis）
_dataset_progress: Dict[str, Dict] = {}


def _emit_sse_progress(task_id: str, stage: str, current: int, total: int, message: str = "") -> None:
    """更新任务进度，供 SSE 端点轮询/流式读取"""
    _dataset_progress[task_id] = {
        "stage": stage,
        "current": current,
        "total": total,
        "message": message or _stage_message(stage, current, total),
    }


def _stage_message(stage: str, current: int, total: int) -> str:
    messages = {
        "downloading": f"正在下载图片 ({current}/{total})...",
        "filtering": f"本地过滤中 ({current}/{total})...",
        "ai_cleaning": f"AI 清洗中 ({current}/{total})...",
        "saving": f"保存结果中...",
        "done": f"处理完成，共保留 {current} 张图片",
    }
    return messages.get(stage, f"处理中... {stage} {current}/{total}")


@app.route("/api/dataset/progress/<task_id>")
def dataset_progress_stream(task_id: str):
    """
    SSE 实时进度端点。
    
    用法：
      1. 前端调用 /api/dataset/scrape-clean 获取 task_id
      2. 同时监听 /api/dataset/progress/<task_id> 接收进度
    """
    from flask import Response as FlaskResponse
    
    def generate():
        last_sent = ""
        timeout_counter = 0
        max_timeouts = 120  # 最大等待次数 (约60秒)
        
        while True:
            data = _dataset_progress.get(task_id)
            if data:
                payload = json.dumps(data, ensure_ascii=False)
                if payload != last_sent:
                    yield f"data: {payload}\n\n"
                    last_sent = payload
                    
                    # 任务完成则关闭连接
                    if data.get("stage") == "done":
                        break
            
            import time
            time.sleep(0.5)
            
            timeout_counter += 1
            if timeout_counter > max_timeouts and not data:
                yield f"data: {json.dumps({'error': 'timeout', 'message': '等待超时'})}\n\n"
                break
    
    return FlaskResponse(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.route("/api/dataset/scrape-clean", methods=["POST"])
def dataset_scrape_clean():
    """
    FormData:
      - query: str
      - count: int
      - min_width/min_height: int
      - seed: int
      - name: zip base name
    Returns: zip (images/ + report.jsonl)
    """
    try:
        if not _require_login():
            return _auth_required_json()
        query = (request.form.get("query") or "").strip()
        if not query:
            return jsonify({"success": False, "error": "请输入爬取关键词"}), 400
        count = int(float(request.form.get("count") or "50"))
        count = max(1, min(count, 500))
        min_w = int(float(request.form.get("min_width") or "256"))
        min_h = int(float(request.form.get("min_height") or "256"))
        mm_model = _resolve_mm_model(request.form.get("model") or "")
        seed = int(float(request.form.get("seed") or "42"))
        name = (request.form.get("name") or "").strip() or f"dataset_{query}"

        # 生成任务ID用于 SSE 进度推送
        task_id = uuid.uuid4().hex[:12]
        
        def on_progress(stage: str, current: int, total: int) -> None:
            _emit_sse_progress(task_id, stage, current, total)

        # scrape urls (已优化默认参数)
        _emit_sse_progress(task_id, "downloading", 0, count)
        
        max_links = int(os.getenv("DATASET_SCRAPE_MAX_LINKS", "800"))
        delay_ms = int(os.getenv("DATASET_SCRAPE_DELAY_MS", "150"))  # 优化：350->150
        timeout_sec = int(os.getenv("DATASET_SCRAPE_TIMEOUT_SEC", "30"))  # 优化：45->30
        
        scraped = scrape_baidu_image_urls(
            query,
            count=count,
            max_links=max_links,
            delay_ms=delay_ms,
            timeout_sec=timeout_sec,
            headless=True,
        )
        urls = [x.url for x in scraped]
        if not urls:
            return jsonify({"success": False, "error": "未抓取到图片链接，请稍后重试或换关键词"}), 400

        _emit_sse_progress(task_id, "scraped", len(urls), len(urls))

        tmp_id = uuid.uuid4().hex
        tmp_dir = Path(app.config["UPLOAD_FOLDER"]) / f"_scrape_{tmp_id}"
        out_dir = tmp_dir / "images"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            cfg = CleanConfig(
                query=query,
                count=count,
                mm_model=mm_model,
                min_width=min_w,
                min_height=min_h,
                enable_nsfw=True,
                enable_match_query=True,
            )
            report, _kept = clean_images(urls, out_dir, cfg=cfg, progress_callback=on_progress)
            report_path = tmp_dir / "report.jsonl"
            write_report_jsonl(report, report_path)

            # zip
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for p in sorted(out_dir.glob("*")):
                    if p.is_file():
                        zf.write(p, arcname=f"images/{p.name}")
                zf.write(report_path, arcname="report.jsonl")
            payload = buf.getvalue()
        finally:
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

        # 清理进度数据
        _dataset_progress.pop(task_id, None)

        dl = (secure_filename(name) or "dataset").strip() + ".zip"
        return send_file(
            io.BytesIO(payload),
            mimetype="application/zip",
            as_attachment=True,
            download_name=dl,
        )
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.exception("dataset scrape-clean")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/dataset/scrape-only", methods=["POST"])
def dataset_scrape_only():
    """
    仅爬取图片并打包zip（不清洗）
    FormData:
      - query: str
      - count: int
      - name: str (optional)
    Returns: zip (images/)
    """
    try:
        if not _require_login():
            return _auth_required_json()
        query = (request.form.get("query") or "").strip()
        if not query:
            return jsonify({"success": False, "error": "请输入爬取关键词"}), 400
        count = int(float(request.form.get("count") or "50"))
        count = max(1, min(count, 500))
        name = (request.form.get("name") or "").strip() or f"dataset_{query}"

        # 已优化默认参数
        max_links = int(os.getenv("DATASET_SCRAPE_MAX_LINKS", "800"))
        delay_ms = int(os.getenv("DATASET_SCRAPE_DELAY_MS", "150"))  # 优化：350->150
        timeout_sec = int(os.getenv("DATASET_SCRAPE_TIMEOUT_SEC", "30"))  # 优化：45->30
        scraped = scrape_baidu_image_urls(
            query,
            count=count,
            max_links=max_links,
            delay_ms=delay_ms,
            timeout_sec=timeout_sec,
            headless=True,
        )
        urls = [x.url for x in scraped]
        if not urls:
            return jsonify({"success": False, "error": "未抓取到图片链接，请稍后重试或换关键词"}), 400

        tmp_id = uuid.uuid4().hex
        tmp_dir = Path(app.config["UPLOAD_FOLDER"]) / f"_scrape_{tmp_id}"
        out_dir = tmp_dir / "images"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)

        download_count = 0
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://image.baidu.com/",
        })
        for idx, url in enumerate(urls[:count], 1):
            try:
                r = session.get(url, timeout=10, allow_redirects=True)
                if r.status_code == 200 and len(r.content) > 1000:
                    ext = _ext_from_url(url) or ".jpg"
                    fname = f"{idx:04d}{ext}"
                    (out_dir / fname).write_bytes(r.content)
                    download_count += 1
                else:
                    logger.warning(f"scrape-only skip idx={idx} status={r.status_code} size={len(r.content)}")
            except Exception as ex:
                logger.warning(f"scrape-only download idx={idx} failed: {ex}")

        logger.info(f"scrape-only query={query} urls={len(urls)} downloaded={download_count}")
        if download_count == 0:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return jsonify({"success": False, "error": "图片下载失败，可能是网络问题，请重试"}), 400

        # zip
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(out_dir.glob("*")):
                if p.is_file():
                    zf.write(p, arcname=f"images/{p.name}")
        payload = buf.getvalue()

        shutil.rmtree(tmp_dir, ignore_errors=True)

        dl = (secure_filename(name) or "dataset").strip() + ".zip"
        return send_file(
            io.BytesIO(payload),
            mimetype="application/zip",
            as_attachment=True,
            download_name=dl,
        )
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.exception("dataset scrape-only")
        return jsonify({"success": False, "error": str(e)}), 500


def _ext_from_url(url: str) -> str:
    """从URL中提取文件扩展名"""
    parsed = url.split("?")[0].lower()
    for ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"]:
        if ext in parsed:
            return ext
    return ".jpg"


_MM_CAPTION_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif"}


def _truncate_to_20_chars(text: str, limit: int = 20) -> str:
    # 统一换行和多空白，输出 20 字以内描述
    normalized = re.sub(r"\s+", "", str(text or "").strip())
    return normalized[: max(1, int(limit or 20))]


def _make_caption_unique(caption: str, used: set[str], limit: int = 20) -> str:
    base = _truncate_to_20_chars(caption, limit=limit) or "图像内容描述"
    if base not in used:
        used.add(base)
        return base
    idx = 2
    while True:
        suffix = str(idx)
        room = max(1, limit - len(suffix))
        cand = _truncate_to_20_chars(base[:room] + suffix, limit=limit)
        if cand not in used:
            used.add(cand)
            return cand
        idx += 1


def _normalize_english_prefix(raw: str, fallback: str = "image") -> str:
    s = (raw or "").strip().lower()
    # 若包含中文，优先转拼音再清洗为英文前缀
    if re.search(r"[\u4e00-\u9fff]", s):
        try:
            from pypinyin import Style, lazy_pinyin  # type: ignore[import-not-found] # noqa: PLC0415

            py_parts = lazy_pinyin(s, style=Style.NORMAL, errors="ignore")
            s = "_".join([p for p in py_parts if p]).strip().lower()
        except Exception:
            # 未安装 pypinyin 或转换失败时沿用原始规则
            pass
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        return fallback
    return s


def _english_numbered_name(index: int, ext: str, prefix: str = "image") -> str:
    x = (ext or ".jpg").lower()
    if not x.startswith("."):
        x = "." + x
    if x not in _MM_CAPTION_ALLOWED_EXTS:
        x = ".jpg"
    p = _normalize_english_prefix(prefix, fallback="image")
    return f"{p}_{index:04d}{x}"


def _build_caption_export_bytes(rows: List[Dict[str, str]], fmt: str) -> Tuple[bytes, str, str]:
    fmt = (fmt or "txt").strip().lower()
    if fmt not in ("txt", "jsonl", "csv"):
        fmt = "txt"
    if fmt == "jsonl":
        payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows).encode("utf-8")
        return payload, "application/x-ndjson; charset=utf-8", "jsonl"
    if fmt == "csv":
        sio = io.StringIO()
        writer = csv.DictWriter(sio, fieldnames=["image", "caption"])
        writer.writeheader()
        writer.writerows(rows)
        return sio.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", "csv"
    lines = [f"{r.get('image', '')}\t{r.get('caption', '')}" for r in rows]
    return "\n".join(lines).encode("utf-8"), "text/plain; charset=utf-8", "txt"


def _describe_image_20chars(client: Any, image_bytes: bytes, query: str = "") -> str:
    mm = qwen_mm_clean_one(client, query=(query or "").strip(), image_bytes=image_bytes)
    caption_raw = mm.get("caption") if isinstance(mm, dict) else ""
    caption = _truncate_to_20_chars(str(caption_raw or ""))
    if not caption:
        caption = "图像内容描述生成失败"
    return caption


def _has_quota_error(report_rows: List[Dict[str, Any]]) -> bool:
    for row in report_rows:
        mm = row.get("mm")
        if not isinstance(mm, dict):
            continue
        err = str(mm.get("_error") or "").lower()
        if "429" in err or "quota" in err or "exceeded" in err:
            return True
    return False


def _resolve_mm_model(raw: str) -> str:
    model = (raw or "").strip() or os.getenv("DATASET_QWEN_MODEL", "").strip() or SUPPORTED_MM_MODELS[0]
    if model not in SUPPORTED_MM_MODELS:
        return SUPPORTED_MM_MODELS[0]
    return model


@app.route("/api/mm-align/models")
def mm_align_models():
    return jsonify(
        {
            "success": True,
            "models": list(SUPPORTED_MM_MODELS),
            "default_model": _resolve_mm_model(""),
        }
    )


@app.route("/api/mm-align/scrape-clean-caption", methods=["POST"])
def mm_align_scrape_clean_caption():
    """
    FormData:
      - query: str
      - count: int
      - min_width/min_height: int
      - export_format: txt|jsonl|csv
      - name: 输出包名（可选）
    Returns: zip(images/ + captions.xxx + report.jsonl)
    """
    try:
        if not _require_login():
            return _auth_required_json()
        query = (request.form.get("query") or "").strip()
        if not query:
            return jsonify({"success": False, "error": "请输入爬取关键词"}), 400
        count = max(1, min(int(float(request.form.get("count") or "50")), 500))
        min_w = int(float(request.form.get("min_width") or "256"))
        min_h = int(float(request.form.get("min_height") or "256"))
        export_fmt = (request.form.get("export_format") or "txt").strip().lower()
        mm_model = _resolve_mm_model(request.form.get("model") or "")
        name = (request.form.get("name") or "").strip() or f"dataset_{query}"
        file_prefix = _normalize_english_prefix(query, fallback="image")

        max_links = int(os.getenv("DATASET_SCRAPE_MAX_LINKS", "800"))
        delay_ms = int(os.getenv("DATASET_SCRAPE_DELAY_MS", "150"))
        timeout_sec = int(os.getenv("DATASET_SCRAPE_TIMEOUT_SEC", "30"))
        scraped = scrape_baidu_image_urls(
            query,
            count=count,
            max_links=max_links,
            delay_ms=delay_ms,
            timeout_sec=timeout_sec,
            headless=True,
        )
        urls = [x.url for x in scraped]
        if not urls:
            return jsonify({"success": False, "error": "未抓取到图片链接，请稍后重试或换关键词"}), 400

        tmp_id = uuid.uuid4().hex
        tmp_dir = Path(app.config["UPLOAD_FOLDER"]) / f"_mmalign_{tmp_id}"
        out_dir = tmp_dir / "images"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            cfg = CleanConfig(
                query=query,
                count=count,
                mm_model=mm_model,
                min_width=min_w,
                min_height=min_h,
                enable_nsfw=True,
                enable_match_query=True,
            )
            report, _kept = clean_images(urls, out_dir, cfg=cfg)
            quota_exhausted = _has_quota_error(report)
            if not _kept and quota_exhausted:
                # 配额耗尽时降级为本地过滤，避免导出空 images/
                cfg_fallback = CleanConfig(
                    query=query,
                    count=count,
                    mm_model=mm_model,
                    min_width=min_w,
                    min_height=min_h,
                    enable_nsfw=False,
                    enable_match_query=False,
                )
                report, _kept = clean_images(urls, out_dir, cfg=cfg_fallback)
            report_path = tmp_dir / "report.jsonl"
            write_report_jsonl(report, report_path)

            captions_rows: List[Dict[str, str]] = []
            caption_used: set[str] = set()
            file_rename_map: Dict[str, str] = {}
            caption_client = None if quota_exhausted else build_modelscope_mm_client()
            kept_index = 0
            for r in report:
                if not r.get("kept"):
                    continue
                img_name = str(r.get("path") or "").strip()
                if not img_name:
                    continue
                kept_index += 1
                old_path = out_dir / img_name
                ext = old_path.suffix.lower() or ".jpg"
                new_img_name = _english_numbered_name(kept_index, ext, prefix=file_prefix)
                file_rename_map[img_name] = new_img_name

                raw = old_path.read_bytes() if old_path.is_file() else b""
                if raw and caption_client is not None:
                    mm = qwen_mm_clean_one(caption_client, query=query, image_bytes=raw, model=mm_model)
                    cap = _truncate_to_20_chars(str((mm or {}).get("caption") or ""))
                elif raw:
                    cap = f"{query}相关图片描述{kept_index}"
                else:
                    cap = ""
                if not cap:
                    cap = "图像描述缺失"
                cap = _make_caption_unique(cap, caption_used, limit=20)
                captions_rows.append({"image": new_img_name, "caption": cap})

            payload_caption, caption_mime, caption_ext = _build_caption_export_bytes(captions_rows, export_fmt)
            caption_name = f"captions.{caption_ext}"

            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for p in sorted(out_dir.glob("*")):
                    if p.is_file():
                        mapped_name = file_rename_map.get(p.name, p.name)
                        zf.write(p, arcname=f"images/{mapped_name}")
                zf.write(report_path, arcname="report.jsonl")
                zf.writestr(caption_name, payload_caption)
            payload = buf.getvalue()
            _ = caption_mime  # 保留变量便于后续扩展
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        dl = (secure_filename(name) or "dataset").strip() + ".zip"
        return send_file(
            io.BytesIO(payload),
            mimetype="application/zip",
            as_attachment=True,
            download_name=dl,
        )
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.exception("mm align scrape-clean-caption")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/mm-align/upload-caption", methods=["POST"])
def mm_align_upload_caption():
    """
    multipart:
      - files[]: image files 或 zip 压缩包
      - export_format: txt|jsonl|csv
      - name: 输出文件名主名（可选）
      - query: 可选，作为描述上下文
    Returns: captions.xxx
    """
    try:
        if not _require_login():
            return _auth_required_json()
        files = request.files.getlist("files")
        if not files:
            return jsonify({"success": False, "error": "请至少上传一张图片"}), 400
        export_fmt = (request.form.get("export_format") or "txt").strip().lower()
        query = (request.form.get("query") or "").strip()
        name = (request.form.get("name") or "").strip() or "captions"
        mm_model = _resolve_mm_model(request.form.get("model") or "")
        file_prefix = _normalize_english_prefix(query, fallback="image")

        client = build_modelscope_mm_client()
        rows: List[Dict[str, str]] = []
        used_caption: set[str] = set()
        img_idx = 0
        upload_items: List[Tuple[str, str, bytes]] = []  # (orig_name, ext, raw)
        for f in files:
            if not f or not f.filename:
                continue
            raw = f.read()
            if not raw:
                continue
            ext = Path(f.filename).suffix.lower()
            if ext == ".zip":
                try:
                    with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
                        for zi in zf.infolist():
                            if zi.is_dir():
                                continue
                            inner_name = Path(zi.filename).name
                            inner_ext = Path(inner_name).suffix.lower()
                            if inner_ext not in _MM_CAPTION_ALLOWED_EXTS:
                                continue
                            try:
                                inner_raw = zf.read(zi)
                            except Exception:
                                continue
                            if inner_raw:
                                upload_items.append((inner_name, inner_ext, inner_raw))
                except Exception:
                    logger.warning("mm align upload: invalid zip %s", f.filename)
                continue
            if ext in _MM_CAPTION_ALLOWED_EXTS:
                upload_items.append((f.filename, ext, raw))

        for _orig_name, ext, raw in upload_items:
            img_idx += 1
            fname = _english_numbered_name(img_idx, ext, prefix=file_prefix)
            mm = qwen_mm_clean_one(client, query=query, image_bytes=raw, model=mm_model)
            caption = _truncate_to_20_chars(str((mm or {}).get("caption") or ""))
            caption = _make_caption_unique(caption, used_caption, limit=20)
            rows.append({"image": fname, "caption": caption})

        if not rows:
            return jsonify({"success": False, "error": "未检测到可用图片文件"}), 400

        payload, mime, ext = _build_caption_export_bytes(rows, export_fmt)
        dl = f"{secure_filename(name) or 'captions'}.{ext}"
        return send_file(
            io.BytesIO(payload),
            mimetype=mime,
            as_attachment=True,
            download_name=dl,
        )
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.exception("mm align upload-caption")
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== 数据标注（LabelImg 启动器） ====================

@app.route("/api/labelimg/launch", methods=["POST"])
def labelimg_launch():
    """
    JSON:
      - images_dir: 图片目录（必填）
      - save_dir: 标注保存目录（可选）
    """
    try:
        if not _require_login():
            return _auth_required_json()
        data = request.get_json(silent=True) or {}
        images_dir = (data.get("images_dir") or "").strip()
        save_dir = (data.get("save_dir") or "").strip() or None
        if not images_dir:
            return jsonify({"success": False, "error": "请填写图片目录 images_dir"}), 400
        pid, cmd = launch_labelimg(images_dir=images_dir, save_dir=save_dir)
        return jsonify({"success": True, "pid": pid, "cmd": cmd})
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.exception("labelimg launch failed")
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== 文档格式转换与合并 ====================

@app.route("/api/docs/merge-convert", methods=["POST"])
def docs_merge_convert():
    """
    multipart:
      - files[]: 多个文档（目前支持 .docx；可按后续扩展 pdf 等）
      - order: JSON 数组（可选），例如 [2,0,1]，表示按上传索引重排
      - out_format: docx|pdf
      - name: 输出文件名主名（可选）
      - header_case_insensitive: true|false（Excel 合并时列名大小写是否视为同列）
      - column_merge_mode: union|intersection（Excel 合并列策略）
    """
    try:
        if not _require_login():
            return _auth_required_json()
        files = request.files.getlist("files")
        if not files:
            return jsonify({"success": False, "error": "请上传要合并/转换的文档"}), 400
        out_format = (request.form.get("out_format") or "docx").strip().lower()
        if out_format not in ("docx", "pdf"):
            out_format = "docx"
        name = (request.form.get("name") or "").strip() or "merged"
        header_case_insensitive = (request.form.get("header_case_insensitive") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        column_merge_mode = (request.form.get("column_merge_mode") or "union").strip().lower()
        if column_merge_mode not in ("union", "intersection"):
            column_merge_mode = "union"

        raw_items = []
        for f in files:
            if not f or not f.filename:
                continue
            fn = f.filename
            data = f.read()
            raw_items.append((fn, data))
        if not raw_items:
            return jsonify({"success": False, "error": "未读取到上传文件"}), 400

        # reorder
        order_raw = (request.form.get("order") or "").strip()
        items = raw_items
        if order_raw:
            try:
                idxs = json.loads(order_raw)
                if isinstance(idxs, list) and all(isinstance(x, int) for x in idxs):
                    tmp = []
                    for i in idxs:
                        if 0 <= i < len(raw_items):
                            tmp.append(raw_items[i])
                    if tmp:
                        items = tmp
            except Exception:
                pass

        exts = []
        for fn, _ in items:
            low = fn.lower()
            if low.endswith(".docx"):
                exts.append("docx")
            elif low.endswith(".xlsx") or low.endswith(".xlsm"):
                exts.append("xlsx")
            else:
                exts.append("")

        if any(x == "" for x in exts) or len(set(exts)) != 1:
            return jsonify(
                {"success": False, "error": "请上传同一种类型文件：仅支持 .docx 或 .xlsx/.xlsm"}
            ), 400

        kind = exts[0]
        if kind == "docx":
            if len(items) == 1:
                payload = convert_doc_aspose(items[0][1], out_format=out_format)
            else:
                merged = merge_docs_aspose(items)
                payload = (
                    convert_doc_aspose(merged, out_format=out_format)
                    if out_format != "docx"
                    else merged
                )
            mime = (
                "application/pdf"
                if out_format == "pdf"
                else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            dl = f"{secure_filename(name) or 'merged'}.{out_format}"
        else:
            # xlsx merge → always output xlsx
            payload = merge_xlsx_bytes(
                items,
                opts=MergeXlsxOptions(
                    skip_duplicate_header=True,
                    align_by_header=True,
                    header_case_insensitive=header_case_insensitive,
                    column_merge_mode=column_merge_mode,
                ),
            )
            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            out_format = "xlsx"
            dl = f"{secure_filename(name) or 'merged'}.{out_format}"

        return send_file(
            io.BytesIO(payload),
            mimetype=mime,
            as_attachment=True,
            download_name=dl,
        )
    except ImportError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.exception("docs merge-convert")
        return jsonify({"success": False, "error": str(e)}), 500


def _vue_dist_dir() -> Path:
    return Path(__file__).resolve().parent / "frontend" / "dist"


def _serve_vue_spa():
    dist = _vue_dist_dir()
    index_file = dist / "index.html"
    if not index_file.is_file():
        return jsonify(
            {
                "success": False,
                "error": "Vue 前端未构建，请先在 frontend 目录执行 npm run build",
            }
        ), 503
    return send_from_directory(str(dist), "index.html")


@app.route('/')
def index():
    """Vue3 SPA 入口"""
    return _serve_vue_spa()


@app.route("/login")
def login_page():
    return _serve_vue_spa()


@app.route("/register")
def register_page():
    return _serve_vue_spa()


@app.route("/forgot")
def forgot_page():
    return redirect("/forgot-password")


@app.route("/forgot-password")
def forgot_password_page():
    return _serve_vue_spa()


def _password_ok(pw: str) -> bool:
    s = pw or ""
    if len(s) < 8:
        return False
    has_alpha = any(c.isalpha() for c in s)
    has_digit = any(c.isdigit() for c in s)
    return has_alpha and has_digit


def _code_hash(email: str, code: str) -> str:
    # 绑定 email，避免同码跨邮箱复用
    raw = ((email or "").strip().lower() + ":" + (code or "").strip()).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@app.route("/api/auth/register/request-code", methods=["POST"])
def auth_request_code():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return jsonify({"success": False, "error": "请输入有效邮箱"}), 400
    # QQ 邮箱限制可选：只允许 @qq.com
    if not email.endswith("@qq.com"):
        return jsonify({"success": False, "error": "仅支持 QQ 邮箱（@qq.com）"}), 400

    # 生成 6 位验证码
    import random

    code = f"{random.randint(0, 999999):06d}"
    expires = int(time.time()) + 10 * 60
    ch = _code_hash(email, code)
    upsert_email_code(email, ch, expires)
    try:
        send_qq_email(
            to_email=email,
            subject="注册验证码（10 分钟内有效）",
            content=f"正在注册云栈智助\n账户验证码为：{code}\n如果不是本人操作请忽略",
        )
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.exception("发送注册验证码失败")
        return jsonify({"success": False, "error": f"发送邮件失败：{e}"}), 502
    return jsonify({"success": True})


@app.route("/api/auth/reset/request-code", methods=["POST"])
def auth_reset_request_code():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return jsonify({"success": False, "error": "请输入有效邮箱"}), 400
    if not email.endswith("@qq.com"):
        return jsonify({"success": False, "error": "仅支持 QQ 邮箱（@qq.com）"}), 400
    if not get_user_by_email(email):
        return jsonify({"success": False, "error": "该邮箱未注册"}), 400

    import random

    code = f"{random.randint(0, 999999):06d}"
    expires = int(time.time()) + 10 * 60
    ch = _code_hash(email, code)
    upsert_password_reset_code(email, ch, expires)
    try:
        send_qq_email(
            to_email=email,
            subject="重置密码验证码（10 分钟内有效）",
            content=f"正在重置云栈智助密码\n账户验证码为：{code}\n如果不是本人操作请忽略",
        )
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.exception("发送重置密码验证码失败")
        return jsonify({"success": False, "error": f"发送邮件失败：{e}"}), 502
    return jsonify({"success": True})


@app.route("/api/auth/reset", methods=["POST"])
def auth_reset_password():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()
    new_password = data.get("password") or ""
    if not email or "@" not in email:
        return jsonify({"success": False, "error": "请输入有效邮箱"}), 400
    if not email.endswith("@qq.com"):
        return jsonify({"success": False, "error": "仅支持 QQ 邮箱（@qq.com）"}), 400
    if not (code.isdigit() and len(code) == 6):
        return jsonify({"success": False, "error": "请输入 6 位数字验证码"}), 400
    if not _password_ok(new_password):
        return jsonify({"success": False, "error": "密码至少 8 位，且必须包含英文字母与数字"}), 400

    ok, err = check_password_reset_code(email, _code_hash(email, code))
    if not ok:
        return jsonify({"success": False, "error": err}), 400
    try:
        update_user_password(email, new_password)
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.exception("reset password failed")
        return jsonify({"success": False, "error": f"重置失败：{e}"}), 500
    return jsonify({"success": True})


@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    code = (data.get("code") or "").strip()
    if not username:
        return jsonify({"success": False, "error": "请输入账号名"}), 400
    if not email or "@" not in email:
        return jsonify({"success": False, "error": "请输入有效邮箱"}), 400
    if not email.endswith("@qq.com"):
        return jsonify({"success": False, "error": "仅支持 QQ 邮箱（@qq.com）"}), 400
    if not _password_ok(password):
        return jsonify({"success": False, "error": "密码至少 8 位，且必须包含英文字母与数字"}), 400
    if not (code.isdigit() and len(code) == 6):
        return jsonify({"success": False, "error": "请输入 6 位数字验证码"}), 400

    ok, err = check_email_code(email, _code_hash(email, code))
    if not ok:
        return jsonify({"success": False, "error": err}), 400

    try:
        uid = create_user(username, email, password)
    except Exception as e:
        # 邮箱重复等
        return jsonify({"success": False, "error": f"注册失败：{e}"}), 400

    session["user_id"] = uid
    session["user_email"] = email
    session["user_name"] = username
    return jsonify({"success": True})


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    ok, uid, err = verify_login(email, password)
    if not ok or not uid:
        return jsonify({"success": False, "error": err or "登录失败"}), 400
    session["user_id"] = uid
    session["user_email"] = email
    u = get_user_by_id(uid)
    session["user_name"] = (u["username"] if u else "") or ""
    return jsonify({"success": True})


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    session.pop("user_id", None)
    session.pop("user_email", None)
    session.pop("user_name", None)
    return jsonify({"success": True})


@app.route("/api/auth/me")
def auth_me():
    return jsonify(
        {
            "success": True,
            "logged_in": bool(session.get("user_id")),
            "email": session.get("user_email"),
            "username": session.get("user_name"),
        }
    )


# ==================== Knowledge Base (AI 课程文档) ====================


@app.route("/api/kb/ingest", methods=["POST"])
def kb_ingest():
    try:
        if not _require_login():
            return _auth_required_json()
        data = request.get_json(silent=True) or {}
        project_root = Path(__file__).resolve().parent
        roots_spec = data.get("roots")
        if isinstance(roots_spec, list) and roots_spec:
            root_paths = [project_root / str(r).strip() for r in roots_spec if str(r).strip()]
        elif data.get("root"):
            root_paths = [project_root / str(data.get("root")).strip()]
        else:
            root_paths = [project_root / r for r in DEFAULT_KB_ROOTS]
        chunk_size = int(data.get("chunk_size") or 1100)
        overlap = int(data.get("overlap") or 160)
        top_n = int(data.get("top_n") or 999999)

        report_path = Path("reports/ingest_report.jsonl")
        counts = assess_roots_and_write_report(roots=root_paths, report_path=report_path)

        # build embeddings + upsert
        col = get_or_create_collection()
        client = build_modelscope_embed_client()
        model = get_embed_model()

        files: list = []
        for rp in root_paths:
            files.extend(scan_ai_folder(rp))
        files = files[: max(0, top_n)]
        ids, texts, metas = [], [], []
        for p in files:
            assessed, fixed = assess_and_fix_one(p)
            if assessed.status == "rejected":
                continue
            chunks = chunk_text(fixed.text, max_chars=chunk_size, overlap=overlap)
            bucket = kb_bucket_for_path(p, project_root)
            for i, ch in enumerate(chunks):
                cid = chunk_stable_id(p, assessed.text_hash, i)
                ids.append(cid)
                texts.append(ch)
                metas.append(
                    {
                        "source_path": str(p),
                        "chunk_id": i,
                        "ext": p.suffix.lower() or "",
                        "tags": ",".join(assessed.tags),
                        "kb_bucket": bucket,
                        "title": p.stem or "",
                    }
                )

        embs = embed_texts(client, texts, model=model)
        upsert_texts(col, ids=ids, texts=texts, metadatas=metas, embeddings=embs)
        return jsonify(
            {
                "success": True,
                "roots": [str(x) for x in root_paths],
                "counts": counts,
                "upserted_chunks": len(ids),
                "kb_dir": "instance/kb_chroma",
                "embed_model": model,
                "report_path": str(report_path),
            }
        )
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.exception("kb ingest")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/kb/search", methods=["POST"])
def kb_search():
    try:
        if not _require_login():
            return _auth_required_json()
        data = request.get_json(silent=True) or {}
        q = (data.get("query") or "").strip()
        top_k = int(data.get("top_k") or 6)
        if not q:
            return jsonify({"success": False, "error": "query 不能为空"}), 400
        col = get_or_create_collection()
        client = build_modelscope_embed_client()
        model = get_embed_model()
        qemb = embed_texts(client, [q], model=model)[0]
        where = None
        kb_bucket = (data.get("kb_bucket") or "").strip()
        if kb_bucket:
            where = {"kb_bucket": kb_bucket}
        hits = kb_query(col, query_embedding=qemb, top_k=top_k, where=where)
        return jsonify(
            {
                "success": True,
                "hits": [
                    {
                        "id": h.id,
                        "score": h.score,
                        "text": h.text,
                        "metadata": h.metadata,
                    }
                    for h in hits
                ],
            }
        )
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.exception("kb search")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/kb/ingest-report", methods=["GET"])
def kb_ingest_report():
    try:
        if not _require_login():
            return _auth_required_json()
        p = Path("reports/ingest_report.jsonl")
        if not p.exists():
            return jsonify({"success": True, "rows": [], "total": 0})
        # simple tail read
        rows = p.read_text(encoding="utf-8").splitlines()
        total = len(rows)
        # optional pagination
        try:
            limit = int(request.args.get("limit", "50"))
            offset = int(request.args.get("offset", "0"))
        except Exception:
            limit, offset = 50, 0
        limit = max(1, min(200, limit))
        offset = max(0, offset)
        sliced = rows[offset : offset + limit]
        out = []
        for line in sliced:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return jsonify({"success": True, "rows": out, "total": total})
    except Exception as e:
        logger.exception("kb report")
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== 云智学习（知识库优先，原 AI 助教） ====================


def _needs_example(user_text: str) -> bool:
    t = (user_text or "").strip().lower()
    keys = ("示例", "例子", "模板", "代码", "怎么写", "示范", "给我一段", "写一段", "sample", "example", "code", "template")
    return any(k.lower() in t for k in keys)


def _is_api_mcp_intent(user_text: str) -> bool:
    """用户问本站 API / MCP 调用时，优先检索 zsk/API_MCP 分桶。"""
    raw = user_text or ""
    t = raw.strip().lower()
    if not t:
        return False
    keys = (
        "mcp",
        "openapi",
        "restful",
        "curl",
        "endpoint",
        "rpc",
        "鉴权",
        "请求体",
        "请求头",
        "接口文档",
        "api文档",
        "怎么调",
        "如何调用",
        "调用示例",
        "/api/",
    )
    if any(k in t for k in keys):
        return True
    if "api" in t:
        return True
    if "接口" in raw:
        return True
    return False


def _kb_hits_for_tutor(col, qemb: list, msg: str, *, top_k: int) -> list:
    """API/MCP 意图：先查 api_mcp 分桶，不足再补全库。"""
    cap = max(top_k, 6)
    if not _is_api_mcp_intent(msg):
        return kb_query(col, query_embedding=qemb, top_k=cap)[:cap]

    scoped = kb_query(
        col,
        query_embedding=qemb,
        top_k=cap,
        where={"kb_bucket": "api_mcp"},
    )
    if len(scoped) >= 3:
        return scoped[:cap]

    broad = kb_query(col, query_embedding=qemb, top_k=cap)
    seen_ids = {h.id for h in scoped}
    out = list(scoped)
    for h in broad:
        if h.id in seen_ids:
            continue
        seen_ids.add(h.id)
        out.append(h)
        if len(out) >= cap:
            break
    return out[:cap]


@app.route("/api/ai-tutor/chat", methods=["POST"])
def ai_tutor_chat():
    try:
        if not _require_login():
            return _auth_required_json()
        data = request.get_json(silent=True) or {}
        msg = (data.get("message") or "").strip()
        if not msg:
            return jsonify({"success": False, "error": "message 不能为空"}), 400

        client = build_modelscope_embed_client()
        chat_model = (os.getenv("AI_TUTOR_CHAT_MODEL") or "moonshotai/Kimi-K2.5").strip()

        # 例外：用户明确要示例/代码 → 直接生成（API/MCP 调用类问题仍走知识库，便于返回文档中的调用示例）
        if _needs_example(msg) and not _is_api_mcp_intent(msg):
            example_hint = "\n\n【格式提醒】你正在为用户生成示例代码，所有代码、命令、配置、输出必须用 Markdown fenced code block（```lang ... ```）包裹，禁止纯文本行内缩进输出。"
            resp = client.chat.completions.create(
                model=chat_model,
                messages=[
                    {"role": "system", "content": AI_TUTOR_SYSTEM_PROMPT},
                    {"role": "user", "content": msg + example_hint},
                ],
                temperature=0.25,
                max_tokens=1200,
            )
            text = resp.choices[0].message.content if resp.choices else ""
            return jsonify({"success": True, "answer": text, "sources": []})

        # 知识库检索
        col = get_or_create_collection()
        embed_model = get_embed_model()
        qemb = embed_texts(client, [msg], model=embed_model)[0]
        top_k = int(data.get("top_k") or 6)
        hits = _kb_hits_for_tutor(col, qemb, msg, top_k=top_k)

        sources = []
        snippets = []
        for h in hits:
            meta = h.metadata or {}
            sources.append(
                {
                    "source_path": meta.get("source_path"),
                    "chunk_id": meta.get("chunk_id"),
                    "score": h.score,
                    "kb_bucket": meta.get("kb_bucket"),
                }
            )
            snippets.append(
                f"[kb_bucket={meta.get('kb_bucket')} source_path={meta.get('source_path')} chunk_id={meta.get('chunk_id')} score={h.score:.3f}]\n{h.text}"
            )

        kb_block = "\n\n".join(snippets).strip()
        format_hint = "\n\n【格式提醒】回答中所有代码、命令、配置、JSON、SQL、请求示例、终端输出必须用 Markdown fenced code block（```lang ... ```）包裹，禁止纯文本行内缩进输出。"
        user_prompt = f"""【用户问题】\n{msg}\n\n【知识库检索片段】\n{kb_block if kb_block else '（无）'}\n""" + format_hint

        system_msg = AI_TUTOR_SYSTEM_PROMPT
        if _is_api_mcp_intent(msg):
            system_msg = AI_TUTOR_SYSTEM_PROMPT + "\n" + AI_TUTOR_API_MCP_APPENDIX

        resp = client.chat.completions.create(
            model=chat_model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.25,
            max_tokens=1400,
        )
        text = resp.choices[0].message.content if resp.choices else ""
        return jsonify({"success": True, "answer": text, "sources": sources})
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.exception("ai tutor chat")
        return jsonify({"success": False, "error": str(e)}), 500


def _require_login() -> bool:
    return bool(session.get("user_id"))


def _auth_required_json():
    return jsonify({"success": False, "error": "请先登录后再使用该功能"}), 401

@app.route("/api/image-augment/options")
def image_augment_options():
    """图片数据增强：可选增强类型列表"""
    return jsonify({"success": True, "options": list_augment_options()})


@app.route("/api/image-augment", methods=["POST"])
def image_augment():
    """多图上传，按所选增强类型各生成一张图，打包 ZIP 返回"""
    if not _require_login():
        return _auth_required_json()
    files = request.files.getlist("files")
    raw_ops = request.form.getlist("ops")
    fmt = (request.form.get("format") or "png").strip().lower()
    try:
        q = int(request.form.get("quality", 90))
    except (TypeError, ValueError):
        q = 90
    q = max(60, min(100, q))

    if not files or all(not (f and f.filename) for f in files):
        return jsonify({"success": False, "error": "请至少选择一张图片"}), 400

    allowed = allowed_op_ids()
    ops = list(dict.fromkeys([o.strip() for o in raw_ops if o and o.strip() in allowed]))
    if not ops:
        return jsonify({"success": False, "error": "请至少选择一种增强类型"}), 400

    max_files = 40
    max_ops = 16
    if len(files) > max_files:
        return jsonify({"success": False, "error": f"单次最多 {max_files} 张图片"}), 400
    if len(ops) > max_ops:
        return jsonify({"success": False, "error": f"最多选择 {max_ops} 种增强类型"}), 400

    items = []
    for f in files:
        if not f or not f.filename:
            continue
        if not converter.allowed_file(f.filename):
            continue
        data = f.read()
        if not data:
            continue
        items.append((f.filename, data))

    if not items:
        return jsonify({"success": False, "error": "没有有效的图片文件"}), 400

    try:
        payload = build_augment_zip(items, ops, fmt, quality=q)
    except Exception as e:
        logger.exception("image-augment")
        return jsonify({"success": False, "error": str(e)}), 500

    return send_file(
        io.BytesIO(payload),
        mimetype="application/zip",
        as_attachment=True,
        download_name="image_augment.zip",
    )


@app.route('/convert', methods=['POST'])
def convert_file():
    """转换文件接口"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '没有选择文件'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': '没有选择文件'})
    
    if not converter.allowed_file(file.filename):
        return jsonify({'success': False, 'error': '不支持的文件格式'})
    
    # 获取转换参数
    output_format = request.form.get('format', 'png')
    quality = float(request.form.get('quality', 0.85))
    mode = (request.form.get('mode') or 'convert').strip().lower()
    if mode not in ('convert', 'repair'):
        mode = 'convert'

    try:
        # 保存上传的文件
        filename = secure_filename(file.filename)
        unique_filename = str(uuid.uuid4()) + '_' + filename
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path)

        # 获取原始文件大小
        original_size = os.path.getsize(file_path)

        # 转换 / 修复并导出
        converted_data = converter.convert_image(file_path, output_format, quality, mode=mode)
        
        # 计算转换后的大小
        converted_size = len(converted_data) // 1024  # KB
        
        # 清理临时文件
        os.remove(file_path)
        
        return jsonify({
            'success': True,
            'converted_data': converted_data,
            'original_size': original_size,
            'converted_size': converted_size * 1024  # 转换为字节
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'转换失败: {str(e)}'})

@app.route('/repair-audio', methods=['POST'])
def repair_audio():
    """修复音频文件接口"""
    if audio_repair is None:
        return jsonify(
            {
                'success': False,
                'error': '音频修复不可用：请安装 pydub 与 ffmpeg；若使用 Python 3.13+ 可尝试 pip install pyaudioop-lts 或改用 Python 3.12。',
            }
        ), 503
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '没有选择文件'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': '没有选择文件'})
    
    if not audio_repair.allowed_file(file.filename):
        return jsonify({'success': False, 'error': '不支持的音频格式'})
    
    # 获取修复 / 转换参数
    output_format = request.form.get('format', 'wav')
    quality = int(request.form.get('quality', 320))
    auto_detect_mono = request.form.get('auto_detect_mono', 'true').lower() == 'true'
    enhance_stereo = request.form.get('enhance_stereo', 'true').lower() == 'true'
    mode = (request.form.get('mode') or 'repair').strip().lower()
    if mode not in ('convert', 'repair'):
        mode = 'repair'

    try:
        # 读取文件数据
        file_data = file.read()

        repaired_data, audio_info = audio_repair.repair_audio(
            file_data,
            output_format,
            quality,
            auto_detect_mono,
            enhance_stereo,
            mode=mode,
        )
        
        return jsonify({
            'success': True,
            'repaired_data': repaired_data,
            'audio_info': audio_info
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'处理失败: {str(e)}'})

@app.route('/download/<filename>')
def download_file(filename):
    """下载转换后的文件"""
    try:
        file_path = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        else:
            return jsonify({'error': '文件不存在'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/formats')
def get_formats():
    """获取支持的格式列表"""
    return jsonify({
        'input_formats': list(app.config['ALLOWED_EXTENSIONS']),
        'output_formats': list(app.config['OUTPUT_FORMATS'])
    })

@app.route('/api/model-formats')
def get_model_formats():
    """获取支持的模型格式列表"""
    if model_converter is None:
        return jsonify({
            'error': '模型转换器不可用，请检查依赖安装',
            'input_formats': [],
            'output_formats': []
        })
    
    supported_conversions = model_converter.get_supported_conversions()
    return jsonify({
        'input_formats': list(app.config['MODEL_ALLOWED_EXTENSIONS']),
        'output_formats': list(app.config['MODEL_OUTPUT_FORMATS']),
        'supported_conversions': supported_conversions,
        'available_libs': model_converter.available_libs
    })

@app.route('/convert-model', methods=['POST'])
def convert_model():
    """转换模型文件接口"""
    if model_converter is None:
        return jsonify({
            'success': False, 
            'error': '模型转换器不可用，请检查依赖安装。参考 SOLUTION.md 或 MODEL_INSTALL.md'
        })
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '没有选择文件'})

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': '没有选择文件'})

    # 检查是否为 YOLO 模型且未安装 ultralytics
    if (file.filename.lower().endswith('.pt') or file.filename.lower().endswith('.pth')) and \
       not model_converter.available_libs.get('ultralytics', False):
        logger.warning("检测到可能为 YOLO 模型，但 ultralytics 未安装")

    if not model_converter.allowed_file(file.filename):
        return jsonify({'success': False, 'error': '不支持的模型格式'})
    
    # 获取转换参数
    output_format = request.form.get('format', 'onnx')
    input_shape = request.form.get('input_shape', None)
    opset_version = int(request.form.get('opset_version', 12))
    
    # 解析input_shape
    if input_shape:
        try:
            input_shape = [int(x) for x in input_shape.split(',')]
        except ValueError:
            return jsonify({'success': False, 'error': '输入形状格式错误，应为逗号分隔的数字，如: 1,3,224,224'})
    
    file_path = None
    try:
        # 保存上传的文件
        filename = secure_filename(file.filename)
        unique_filename = str(uuid.uuid4()) + '_' + filename
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path)

        original_size = os.path.getsize(file_path)

        converted_data, model_info = model_converter.convert_model(
            file_path, output_format, input_shape, opset_version
        )

        import base64

        converted_b64 = base64.b64encode(converted_data).decode('utf-8')

        return jsonify({
            'success': True,
            'converted_data': converted_b64,
            'model_info': model_info,
            'original_size': original_size,
            'converted_size': len(converted_data)
        })

    except Exception as e:
        logger.exception("convert-model")
        return jsonify({'success': False, 'error': f'转换失败: {str(e)}'})
    finally:
        if file_path and os.path.isfile(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass

@app.errorhandler(413)
def too_large(e):
    """文件过大错误处理"""
    return jsonify({'success': False, 'error': '文件过大，最大支持 500MB'}), 413


# ==================== 每日必读资讯 API（固定 https://news.softunis.com/ai） ====================

@app.route('/api/news/search', methods=['POST'])
def search_news():
    """拉取软盟 AI 或腾讯新闻频道列表并可选 AI 总结"""
    try:
        data = request.get_json() or {}
        _allowed_limits = {1, 3, 5, 10}
        try:
            _lim = int(data.get("limit", 5))
        except (TypeError, ValueError):
            _lim = 5
        limit = _lim if _lim in _allowed_limits else 5
        use_ai = data.get('use_ai', True)
        feed = (data.get("feed") or "softunis").strip().lower()
        qq_channel = (data.get("qq_channel") or "tech").strip().lower()
        softunis_tag = (data.get("softunis_tag") or "ai").strip().lower()
        logger.info(
            "[API] POST /api/news/search limit=%s use_ai=%s feed=%s qq_channel=%s softunis_tag=%s",
            limit,
            use_ai,
            feed,
            qq_channel if feed == "tencent" else "-",
            softunis_tag if feed == "softunis" else "-",
        )

        result = news_summarizer.search_and_summarize(
            limit=limit,
            use_ai=use_ai,
            feed=feed,
            qq_channel=qq_channel if feed == "tencent" else None,
            softunis_tag=softunis_tag if feed == "softunis" else None,
        )
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'搜索失败：{str(e)}',
            'articles': []
        })

# ==================== 文档文稿处理（符号/空格清理 + PDF/Word/Excel） ====================

def _text_clean_client_and_model():
    client, _ = build_openai_client()
    from utils.openai_compat import get_default_clean_model  # noqa: PLC0415

    model = (os.getenv("AI_CLEAN_MODEL") or get_default_clean_model()).strip()
    return client, model


def _text_clean_download_basename(raw_title: str, method: str, ext: str) -> str:
    """
    用户填写「文档标题」时，用标题作为下载文件名（去掉非法字符，过长则截断加省略号）；
    未填写时仍为 document_{method}.ext。
    """
    raw = (raw_title or "").strip()
    if not raw:
        return f"document_{method}.{ext}"
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw)
    safe = re.sub(r"\s+", "_", safe).strip(" ._")
    if not safe:
        return f"document_{method}.{ext}"
    max_stem = 60
    if len(safe) > max_stem:
        safe = safe[: max_stem - 1].rstrip("._") + "…"
    return f"{safe}.{ext}"


def _export_basename_match_upload(original_filename: str, out_ext: str) -> str:
    """
    上传 Word/Excel 补全后下载：与上传文件名主名尽量一致（仅扩展名按导出格式，如 .docx/.xlsx）。
    仅移除路径与 Windows 非法字符，保留空格与常见 Unicode，避免与客户端 f.name 不一致。
    """
    raw = str(original_filename or "").strip().replace("\\", "/")
    base = Path(raw).name
    stem = Path(base).stem if base else ""
    stem = stem or "document"
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", stem)
    safe = safe.strip(" .") or "document"
    max_stem = 180
    if len(safe) > max_stem:
        safe = safe[: max_stem - 1].rstrip("._") + "…"
    ext = (out_ext or "docx").lower().lstrip(".")
    return f"{safe}.{ext}"


def _text_clean_office_attachment_response(
    payload: bytes, mimetype: str, download_name: str
) -> Response:
    """
    文档文稿导出：手写 Content-Disposition，优先 filename*=UTF-8''（RFC 5987）。
    Werkzeug 对非 ASCII 的 ASCII 回退偶发成极短串，前端误解析会得到类似「1.docx」。
    """
    name = (download_name or "document").strip() or "document"
    pct = quote(name, safe="")
    ext = Path(name).suffix.lower() or ".bin"
    safe = "".join(
        ch if 32 <= ord(ch) <= 126 and ch not in '<>:"/\\|?*' else "_"
        for ch in name
    )
    safe = safe.strip(" ._") or f"download{ext}"
    if len(safe) > 120:
        safe = safe[:117].rstrip("._") + "..."
    cd = f'attachment; filename*=UTF-8\'\'{pct}; filename="{safe}"'
    resp = Response(payload, mimetype=mimetype)
    resp.headers["Content-Disposition"] = cd
    return resp


def _openai_compatible_error_message(exc: BaseException) -> str:
    """从 ModelScope/OpenAI 兼容接口异常中解析对用户可读的 error.message。"""
    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            data = resp.json()
            if isinstance(data, dict):
                err = data.get("error")
                if isinstance(err, dict):
                    m = err.get("message")
                    if m:
                        return str(m).strip()
        except Exception:
            pass
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            m = err.get("message")
            if m:
                return str(m).strip()
    m = getattr(exc, "message", None)
    if m:
        return str(m).strip()
    s = str(exc).strip()
    return s or "模型接口调用失败"


def _rate_limit_user_message(exc: BaseException) -> str:
    """429 限流：附带接口原文与中文处置说明（换模型、稍后重试）。"""
    detail = _openai_compatible_error_message(exc)
    hint = (
        "【请求过于频繁（HTTP 429）】请间隔几分钟后再试。"
        "免费/共享额度下热门模型（如 moonshotai/Kimi-K2.5）易被限流；"
        "可将环境变量 AI_CLEAN_MODEL 改为 ModelScope 上其他模型，或使用更高配额的商用 API。"
    )
    if detail and detail != hint:
        return f"{detail}\n\n{hint}"
    return hint


@app.route("/api/text-clean/config")
def text_clean_config():
    client, _ = _text_clean_client_and_model()
    deps = export_optional_deps_status()
    try:
        import aspose.words as aw  # type: ignore  # noqa: F401

        aspose_installed = True
    except ImportError:
        aspose_installed = False
    return jsonify(
        {
            "success": True,
            "ai_available": bool(client),
            "export_deps": deps,
            "export_ready": all(deps.values()),
            "docx_file_fill_uses_aspose_only": True,
            "aspose_words_installed": aspose_installed,
        }
    )


@app.route("/api/text-clean/preview", methods=["POST"])
def text_clean_preview():
    try:
        if not _require_login():
            return _auth_required_json()
        client, model = _text_clean_client_and_model()
        uf = request.files.get("file")
        if uf and uf.filename and sniff_office_kind(uf.filename):
            instructions = (request.form.get("instructions") or "").strip()
            use_ai = request.form.get("use_ai", "true").lower() in ("1", "true", "yes", "on")
            if not instructions:
                return jsonify(
                    {
                        "success": False,
                        "error": "请填写对文档的处理要求（例如：补全未写栏目、按实验报告格式完善正文）",
                    }
                ), 400
            if not client:
                return jsonify(
                    {"success": False, "error": "未配置 MODELSCOPE_TOKEN，无法调用大模型处理文档"}
                ), 400
            raw = uf.read()
            kind = sniff_office_kind(uf.filename)
            if kind == "docx":
                try:
                    ensure_aspose_installed()
                except ImportError as e:
                    return jsonify({"success": False, "error": str(e)}), 400
                if not docx_has_processable_blocks(raw):
                    return jsonify(
                        {
                            "success": False,
                            "error": "文档主故事区无可用段落或表格，无法按版式保留方式处理",
                        }
                    ), 400
                _filled, aspose_docx = generate_file_fill(
                    client,
                    model,
                    instructions,
                    "",
                    office_kind=kind,
                    docx_bytes=raw,
                )
                if not aspose_docx:
                    return jsonify(
                        {
                            "success": False,
                            "error": "Word 处理未返回文档，请调整说明后重试",
                        }
                    ), 400
                cleaned = sanitize_xml_compatible_text(
                    plain_text_preview_from_docx_bytes(aspose_docx)
                )
                method = "api_aspose_structured"
            else:
                try:
                    kind, src_text = extract_office_text(uf.filename, raw)
                except ValueError as e:
                    return jsonify({"success": False, "error": str(e)}), 400
                except RuntimeError as e:
                    return jsonify({"success": False, "error": str(e)}), 400
                except Exception as e:
                    logger.exception("text-clean preview office extract")
                    return jsonify({"success": False, "error": f"读取文档失败：{e}"}), 400
                if not src_text:
                    return jsonify({"success": False, "error": "文档中未抽取到正文"}), 400
                filled, _aspose_docx = generate_file_fill(
                    client,
                    model,
                    instructions,
                    src_text,
                    office_kind=kind,
                    docx_bytes=None,
                )
                if not filled:
                    return jsonify(
                        {
                            "success": False,
                            "error": "模型未返回有效内容，请调整说明后重试",
                        }
                    ), 400
                cleaned, method = clean_text(
                    filled,
                    use_ai=use_ai,
                    client=client,
                    model=model,
                    force_local=False,
                )
            return jsonify(
                {
                    "success": True,
                    "cleaned": cleaned,
                    "method": method,
                    "source": "file_fill",
                    "office_kind": kind,
                    "aspose_structured": kind == "docx",
                }
            )

        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            data = {}
        source = (data.get("source") or "paste").strip().lower()
        use_ai = data.get("use_ai", True)

        if source == "generate":
            prompt = (data.get("prompt") or "").strip()
            gen_kind = (data.get("gen_kind") or "article").strip().lower()
            if gen_kind not in ("article", "table"):
                gen_kind = "article"
            if not prompt:
                return jsonify({"success": False, "error": "请输入生成提示（写作要求或表格说明）"}), 400
            if not client:
                return jsonify(
                    {"success": False, "error": "未配置 MODELSCOPE_TOKEN，无法调用 ModelScope 大模型生成"}
                ), 400
            raw = generate_content(client, model, prompt, gen_kind)
            if not raw:
                return jsonify({"success": False, "error": "模型未返回内容，请换提示重试"}), 400
            force_local = gen_kind == "table"
            cleaned, method = clean_text(
                raw,
                use_ai=bool(use_ai),
                client=client,
                model=model,
                force_local=force_local,
            )
            return jsonify(
                {
                    "success": True,
                    "cleaned": cleaned,
                    "method": method,
                    "generated": raw,
                    "gen_kind": gen_kind,
                    "source": "generate",
                }
            )

        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"success": False, "error": "请输入正文内容"}), 400
        cleaned, method = clean_text(text, use_ai=bool(use_ai), client=client, model=model)
        return jsonify({"success": True, "cleaned": cleaned, "method": method, "source": "paste"})
    except RateLimitError as e:
        logger.warning("text-clean preview rate limited: %s", e)
        return jsonify({"success": False, "error": _rate_limit_user_message(e)}), 429
    except APIError as e:
        logger.warning("text-clean preview API error: %s", e)
        return jsonify({"success": False, "error": _openai_compatible_error_message(e)}), 502
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.exception("text-clean preview")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/text-clean/export", methods=["POST"])
def text_clean_export():
    try:
        if not _require_login():
            return _auth_required_json()
        use_ai = request.form.get("use_ai", "true").lower() in ("1", "true", "yes", "on")
        fmt = (request.form.get("format") or "pdf").lower().strip()
        raw_title = (request.form.get("title") or "").strip()
        title = raw_title or "文稿"
        source = (request.form.get("source") or "paste").strip().lower()
        gen_kind = (request.form.get("gen_kind") or "article").strip().lower()
        if gen_kind not in ("article", "table"):
            gen_kind = "article"

        client, model = _text_clean_client_and_model()
        text = ""
        gen_kind_effective = gen_kind

        if source == "file_fill":
            uf = request.files.get("file")
            instructions = (request.form.get("instructions") or "").strip()
            original_filename = (request.form.get("original_filename") or "").strip()
            if not uf or not uf.filename:
                return jsonify({"success": False, "error": "请上传 Word 或 Excel 文件"}), 400
            if not sniff_office_kind(uf.filename):
                return jsonify({"success": False, "error": "仅支持 .docx 与 .xlsx/.xlsm"}), 400
            if not instructions:
                return jsonify({"success": False, "error": "请填写处理要求"}), 400
            if not client:
                return jsonify(
                    {"success": False, "error": "未配置 MODELSCOPE_TOKEN，无法调用大模型处理文档"}
                ), 400
            original_filename = original_filename or uf.filename
            raw = uf.read()
            kind = sniff_office_kind(uf.filename)
            stem = Path(original_filename.replace("\\", "/")).stem
            inner_title = raw_title or stem or "文稿"
            if kind == "docx":
                try:
                    ensure_aspose_installed()
                except ImportError as e:
                    return jsonify({"success": False, "error": str(e)}), 400
                if not docx_has_processable_blocks(raw):
                    return jsonify(
                        {
                            "success": False,
                            "error": "文档主故事区无可用段落或表格，无法按版式保留方式处理",
                        }
                    ), 400
                _filled, aspose_docx = generate_file_fill(
                    client,
                    model,
                    instructions,
                    "",
                    office_kind=kind,
                    docx_bytes=raw,
                )
                if not aspose_docx:
                    return jsonify(
                        {
                            "success": False,
                            "error": "Word 处理未返回文档，请调整说明后重试",
                        }
                    ), 400
                fmt = "docx"
                payload = aspose_docx
            else:
                try:
                    kind, src_text = extract_office_text(uf.filename, raw)
                except ValueError as e:
                    return jsonify({"success": False, "error": str(e)}), 400
                except RuntimeError as e:
                    return jsonify({"success": False, "error": str(e)}), 400
                except Exception as e:
                    logger.exception("text-clean export office extract")
                    return jsonify({"success": False, "error": f"读取文档失败：{e}"}), 400
                if not src_text:
                    return jsonify({"success": False, "error": "文档中未抽取到正文"}), 400
                filled, _aspose_xlsx = generate_file_fill(
                    client,
                    model,
                    instructions,
                    src_text,
                    office_kind=kind,
                    docx_bytes=None,
                )
                fmt = "xlsx"
                if not filled:
                    return jsonify(
                        {"success": False, "error": "模型未返回有效内容，请调整说明后重试"}
                    ), 400
                cleaned, method = clean_text(
                    filled,
                    use_ai=use_ai,
                    client=client,
                    model=model,
                    force_local=False,
                )
                payload = write_xlsx_smart_bytes(inner_title, cleaned)
            ext = fmt
            mime = (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                if fmt == "docx"
                else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            name = _export_basename_match_upload(original_filename, ext)
            return _text_clean_office_attachment_response(payload, mime, name)

        if source == "generate":
            prompt = (request.form.get("prompt") or "").strip()
            if not prompt:
                return jsonify({"success": False, "error": "请输入生成提示"}), 400
            if not client:
                return jsonify(
                    {"success": False, "error": "未配置 MODELSCOPE_TOKEN，无法调用大模型生成"}
                ), 400
            text = generate_content(client, model, prompt, gen_kind_effective)
            if not text:
                return jsonify(
                    {
                        "success": False,
                        "error": "模型未返回有效正文（接口 choices 或 content 为空，可能被策略拦截或异常），请换提示重试",
                    }
                ), 400
        else:
            text = (request.form.get("text") or "").strip()
            if "file" in request.files:
                uf = request.files["file"]
                if uf and uf.filename:
                    if sniff_office_kind(uf.filename):
                        return jsonify(
                            {
                                "success": False,
                                "error": "已上传 Word/Excel：请在「内容」中填写处理要求，系统将按办公文档补全流程处理（勿当作 .txt 读取）。",
                            }
                        ), 400
                    text = decode_text_file_bytes(uf.read()).strip()
            if not text:
                return jsonify({"success": False, "error": "请粘贴正文或上传 .txt，或改用 API 生成"}), 400
            gen_kind_effective = "article"

        force_local = source == "generate" and gen_kind_effective == "table"
        cleaned, method = clean_text(
            text,
            use_ai=use_ai,
            client=client,
            model=model,
            force_local=force_local,
        )

        ext = "pdf"
        mime = "application/pdf"
        payload: bytes
        if fmt == "docx":
            ext = "docx"
            mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            payload = write_docx_bytes(title, cleaned)
        elif fmt == "xlsx":
            ext = "xlsx"
            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            payload = write_xlsx_smart_bytes(title, cleaned)
        else:
            payload = write_pdf_bytes(title, cleaned)

        name = _text_clean_download_basename(raw_title, method, ext)
        return send_file(
            io.BytesIO(payload),
            mimetype=mime,
            as_attachment=True,
            download_name=name,
        )
    except RateLimitError as e:
        logger.warning("text-clean export rate limited: %s", e)
        return jsonify({"success": False, "error": _rate_limit_user_message(e)}), 429
    except APIError as e:
        logger.warning("text-clean export API error: %s", e)
        return jsonify({"success": False, "error": _openai_compatible_error_message(e)}), 502
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.exception("text-clean export")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/news/config')
def news_config():
    """获取必读资讯 / ModelScope 配置状态"""
    try:
        from utils.softunis_scraper import list_softunis_tag_options
        from utils.tencent_news_scraper import list_qq_channel_options

        config_status = news_summarizer.is_configured()
        return jsonify({
            'success': True,
            'config': config_status,
            'feeds': [
                {'key': 'softunis', 'label': '软盟资讯'},
                {'key': 'tencent', 'label': '腾讯新闻'},
            ],
            'softunis_tags': list_softunis_tag_options(),
            'qq_channels': list_qq_channel_options(),
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        })


@app.route("/api/news/pushplus-config", methods=["GET"])
def news_pushplus_config_get():
    if not _require_login():
        return _auth_required_json()
    with _news_pushplus_lock:
        cfg = _news_pushplus_load()
    safe = dict(cfg)
    token = (safe.get("token") or "").strip()
    safe["token_masked"] = (token[:4] + "****" + token[-4:]) if len(token) >= 10 else ""
    safe["token"] = token
    return jsonify({"success": True, "config": safe})


@app.route("/api/news/pushplus-config", methods=["POST"])
def news_pushplus_config_save():
    if not _require_login():
        return _auth_required_json()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"success": False, "error": "请提交 JSON"}), 400
    feed = (payload.get("feed") or "softunis").strip().lower()
    if feed not in ("softunis", "tencent"):
        feed = "softunis"
    softunis_tag = (payload.get("softunis_tag") or "ai").strip().lower() or "ai"
    qq_channel = (payload.get("qq_channel") or "tech").strip().lower() or "tech"
    try:
        limit = int(payload.get("limit") or 5)
    except (TypeError, ValueError):
        limit = 5
    if limit not in (1, 3, 5, 10):
        limit = 5
    use_ai = bool(payload.get("use_ai", True))
    enabled = bool(payload.get("enabled", False))
    token = (payload.get("token") or "").strip()
    push_time = (payload.get("push_time") or "08:30").strip()
    if not re.match(r"^\d{2}:\d{2}$", push_time):
        return jsonify({"success": False, "error": "推送时间格式应为 HH:MM（如 08:30）"}), 400
    hh, mm = push_time.split(":")
    if int(hh) > 23 or int(mm) > 59:
        return jsonify({"success": False, "error": "推送时间无效，请填写 00:00 到 23:59"}), 400
    if enabled and not token:
        return jsonify({"success": False, "error": "启用推送时请填写 PushPlus Token"}), 400
    with _news_pushplus_lock:
        cfg = _news_pushplus_load()
        cfg.update(
            {
                "enabled": enabled,
                "token": token,
                "feed": feed,
                "softunis_tag": softunis_tag,
                "qq_channel": qq_channel,
                "limit": limit,
                "use_ai": use_ai,
                "push_time": push_time,
            }
        )
        _news_pushplus_save(cfg)
    return jsonify({"success": True, "config": cfg})


@app.route("/api/news/pushplus-push-now", methods=["POST"])
def news_pushplus_push_now():
    if not _require_login():
        return _auth_required_json()
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    with _news_pushplus_lock:
        cfg = _news_pushplus_load()
        cfg["feed"] = (payload.get("feed") or cfg.get("feed") or "softunis").strip().lower()
        cfg["softunis_tag"] = (payload.get("softunis_tag") or cfg.get("softunis_tag") or "ai").strip().lower()
        cfg["qq_channel"] = (payload.get("qq_channel") or cfg.get("qq_channel") or "tech").strip().lower()
        try:
            cfg["limit"] = int(payload.get("limit") or cfg.get("limit") or 5)
        except (TypeError, ValueError):
            cfg["limit"] = 5
        cfg["use_ai"] = bool(payload.get("use_ai", cfg.get("use_ai", True)))
        token = (cfg.get("token") or "").strip()
    if not token:
        return jsonify({"success": False, "error": "请先在推送设置中配置 PushPlus Token"}), 400
    try:
        result = _pushplus_news_once(cfg)
    except Exception as e:
        logger.exception("PushPlus 立即推送失败")
        return jsonify({"success": False, "error": str(e)}), 500
    return jsonify(
        {
            "success": True,
            "message": "推送成功",
            "articles": len(result.get("articles") or []),
        }
    )


@app.route("/ai")
def ai_chat_page():
    """旧书签兼容：跳转首页「AI 助手」工具编排页签。"""
    return redirect(url_for("index") + "#ai-panel")


@app.route("/api/ai/config")
def ai_api_config():
    token_ok = bool(os.getenv("MODELSCOPE_TOKEN", "").strip())
    return jsonify({"configured": token_ok, "has_token": token_ok})


@app.route("/api/ai/images/generate", methods=["POST"])
def ai_images_generate():
    data = request.get_json(silent=True) or {}
    if not _require_login():
        return _auth_required_json()
    prompt = (data.get("prompt") or "").strip()
    model = (data.get("model") or "Qwen/Qwen-Image").strip()
    size = (data.get("size") or "").strip() or None
    try:
        n = int(data.get("n") or 1)
    except (TypeError, ValueError):
        n = 1
    n = max(1, min(4, n))
    if not prompt:
        return jsonify({"success": False, "error": "请输入图片描述"}), 400
    try:
        out = start_image_generation(prompt, model=model, size=size, n=n)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 503
    except requests.HTTPError as e:
        detail = ""
        if e.response is not None:
            try:
                detail = (e.response.text or "")[:800]
            except Exception:
                detail = ""
        logger.exception("ModelScope images/generations")
        return jsonify({"success": False, "error": str(e), "detail": detail}), 502

    task_id = out.get("task_id")
    if not task_id:
        return jsonify({"success": False, "error": "未返回 task_id", "raw": out}), 502
    return jsonify({"success": True, "task_id": task_id})


@app.route("/api/ai/images/task/<task_id>")
def ai_images_task(task_id):
    if not _require_login():
        return _auth_required_json()
    if not task_id or not str(task_id).strip():
        return jsonify({"success": False, "error": "无效的 task_id"}), 400
    try:
        data = get_image_task(str(task_id).strip())
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 503
    except requests.HTTPError as e:
        detail = ""
        if e.response is not None:
            try:
                detail = (e.response.text or "")[:800]
            except Exception:
                detail = ""
        logger.exception("ModelScope task poll")
        return jsonify({"success": False, "error": str(e), "detail": detail}), 502

    status = data.get("task_status") or data.get("taskStatus") or ""
    images = []
    err_msg = data.get("error") or data.get("message") or data.get("error_message")

    if status == "SUCCEED":
        urls = data.get("output_images") or data.get("outputImages") or []
        if isinstance(urls, str):
            urls = [urls]
        for u in urls:
            if not u:
                continue
            try:
                images.append(fetch_image_as_data_url(u))
            except Exception:
                logger.exception("fetch image url")
        if not images and urls:
            return jsonify(
                {
                    "success": True,
                    "task_status": status,
                    "images": [],
                    "error_message": err_msg or "图片下载失败",
                }
            )

    return jsonify(
        {
            "success": True,
            "task_status": status,
            "images": images,
            "error_message": err_msg,
        }
    )


@app.route("/api/ai/chat", methods=["POST"])
def ai_chat_api():
    data = request.get_json(silent=True) or {}
    if not _require_login():
        return _auth_required_json()
    messages = data.get("messages")
    model = (data.get("model") or os.getenv("MODELSCOPE_CHAT_MODEL") or "moonshotai/Kimi-K2.5").strip()
    if not isinstance(messages, list) or not messages:
        return jsonify({"success": False, "error": "messages 无效"}), 400
    for m in messages:
        if not isinstance(m, dict):
            return jsonify({"success": False, "error": "messages 格式错误"}), 400
        if (m.get("role") or "") not in ("user", "assistant", "system"):
            return jsonify({"success": False, "error": "不支持的 role"}), 400
    try:
        text = chat_completion(messages, model=model)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 503
    except APIError as e:
        detail = ""
        try:
            err = getattr(e, "body", None)
            if err is not None:
                detail = str(err)[:1200]
            elif getattr(e, "response", None) is not None:
                detail = (e.response.text or "")[:1200]
        except Exception:
            detail = str(e)
        logger.exception("ModelScope chat (OpenAI SDK)")
        return jsonify({"success": False, "error": str(e), "detail": detail}), 502

    return jsonify({"success": True, "content": text})


# ==================== AI 社区 ====================

@app.route("/api/community/categories")
def community_categories():
    return jsonify({"success": True, "categories": CATEGORIES})


@app.route("/api/community/posts")
def community_list_posts():
    if not _require_login():
        return _auth_required_json()
    category = request.args.get("category") or None
    post_type = request.args.get("post_type") or None
    keyword = request.args.get("keyword") or None
    try:
        page = int(request.args.get("page") or 1)
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(request.args.get("page_size") or 20)
    except (TypeError, ValueError):
        page_size = 20
    page_size = max(1, min(100, page_size))
    page = max(1, page)
    result = db_list_posts(
        category=category,
        post_type=post_type,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return jsonify({"success": True, **result})


@app.route("/api/community/posts/<int:post_id>")
def community_get_post(post_id):
    if not _require_login():
        return _auth_required_json()
    post = db_get_post(post_id)
    if not post:
        return jsonify({"success": False, "error": "帖子不存在"}), 404
    replies = db_list_replies(post_id)
    return jsonify({"success": True, "post": post, "replies": replies})


@app.route("/api/community/posts", methods=["POST"])
def community_create_post():
    if not _require_login():
        return _auth_required_json()
    uid = session.get("user_id")
    uname = session.get("user_name") or "匿名"
    title = (request.form.get("title") or "").strip()
    if not title:
        return jsonify({"success": False, "error": "标题不能为空"}), 400
    content = (request.form.get("content") or "").strip()
    category = (request.form.get("category") or "其他").strip()
    post_type = (request.form.get("post_type") or "question").strip()
    project_link = (request.form.get("project_link") or "").strip() or None

    attachment = request.files.get("attachment")
    attachment_name = None
    attachment_path = None
    if attachment and attachment.filename:
        import uuid as _uuid
        attachment_name = secure_filename(attachment.filename)
        ext = Path(attachment_name).suffix.lower()
        safe_name = f"community_{_uuid.uuid4().hex}{ext}"
        upload_dir = Path(app.config["UPLOAD_FOLDER"]) / "community_attachments"
        upload_dir.mkdir(parents=True, exist_ok=True)
        attachment_path = str(upload_dir / safe_name)
        attachment.save(attachment_path)

    try:
        pid = db_create_post(
            user_id=uid,
            username=uname,
            title=title,
            content=content,
            category=category,
            post_type=post_type,
            attachment_name=attachment_name,
            attachment_path=attachment_path,
            project_link=project_link,
        )
    except Exception as e:
        logger.exception("community create post")
        return jsonify({"success": False, "error": str(e)}), 500
    return jsonify({"success": True, "id": pid})


@app.route("/api/community/posts/<int:post_id>", methods=["DELETE"])
def community_delete_post(post_id):
    if not _require_login():
        return _auth_required_json()
    uid = session.get("user_id")
    ok = db_delete_post(post_id, uid)
    if not ok:
        return jsonify({"success": False, "error": "删除失败或无权限"}), 403
    return jsonify({"success": True})


@app.route("/api/community/posts/<int:post_id>/download")
def community_download_attachment(post_id):
    if not _require_login():
        return _auth_required_json()
    post = db_get_post(post_id)
    if not post:
        return jsonify({"success": False, "error": "帖子不存在"}), 404
    if not post.get("attachment_path"):
        return jsonify({"success": False, "error": "无附件"}), 404
    p = Path(post["attachment_path"])
    if not p.is_file():
        return jsonify({"success": False, "error": "附件文件不存在"}), 404
    name = post.get("attachment_name") or p.name
    return send_file(p, as_attachment=True, download_name=name)


@app.route("/api/community/posts/<int:post_id>/replies")
def community_list_replies(post_id):
    if not _require_login():
        return _auth_required_json()
    replies = db_list_replies(post_id)
    return jsonify({"success": True, "replies": replies})


@app.route("/api/community/posts/<int:post_id>/replies", methods=["POST"])
def community_create_reply(post_id):
    if not _require_login():
        return _auth_required_json()
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"success": False, "error": "回复内容不能为空"}), 400
    uid = session.get("user_id")
    uname = session.get("user_name") or "匿名"
    try:
        rid = db_create_reply(post_id, uid, uname, content)
    except Exception as e:
        logger.exception("community create reply")
        return jsonify({"success": False, "error": str(e)}), 500
    return jsonify({"success": True, "id": rid})


@app.route("/assets/<path:asset_path>")
def vue_assets(asset_path: str):
    dist_assets = _vue_dist_dir() / "assets"
    f = dist_assets / asset_path
    if not f.is_file():
        abort(404)
    return send_from_directory(str(dist_assets), asset_path)


@app.route("/<path:path>")
def vue_spa_fallback(path: str):
    blocked_prefixes = ("api/", "static/", "uploads/", "downloads/")
    if any(path.startswith(p) for p in blocked_prefixes):
        abort(404)
    dist = _vue_dist_dir()
    raw_file = dist / path
    if raw_file.is_file():
        return send_from_directory(str(dist), path)
    return _serve_vue_spa()


@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "接口不存在"}), 404
    return _serve_vue_spa(), 404

@app.errorhandler(500)
def internal_error(e):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "服务器内部错误"}), 500
    return _serve_vue_spa(), 500

def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


if __name__ == '__main__':
    # 本地运行：默认 127.0.0.1 + 调试模式（自动重载）；gunicorn/宝塔不走此分支
    # 局域网访问：.env 设置 FLASK_HOST=0.0.0.0；关闭调试：FLASK_DEBUG=0
    host = os.getenv("FLASK_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.getenv("FLASK_PORT", "5000"))
    _fd = os.getenv("FLASK_DEBUG", "").strip().lower()
    if _fd in ("0", "false", "no", "off"):
        debug = False
    elif _fd in ("1", "true", "yes", "on"):
        debug = True
    else:
        debug = True  # 未设置 FLASK_DEBUG 时默认开启，便于本地开发
    app.run(debug=debug, host=host, port=port, threaded=True, use_reloader=debug)