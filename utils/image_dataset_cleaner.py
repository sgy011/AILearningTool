"""
图片数据集清洗：下载结果过滤、去重、Qwen 多模态一致性/敏感过滤、输出 report。
支持并发下载和并发 AI 清洗以加速处理。
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from PIL import Image

from utils.mm_clean_qwen import build_modelscope_mm_client, qwen_mm_clean_one

logger = logging.getLogger(__name__)


# 默认并发数（可通过环境变量覆盖）
DOWNLOAD_CONCURRENCY = int(os.getenv("DATASET_DOWNLOAD_CONCURRENCY", "8"))
CLEAN_CONCURRENCY = int(os.getenv("DATASET_CLEAN_CONCURRENCY", "4"))


@dataclass
class CleanConfig:
    query: str
    count: int
    mm_model: str = ""
    min_width: int = 256
    min_height: int = 256
    dedup_md5: bool = True
    dedup_dhash: bool = True
    dhash_threshold: int = 6
    enable_nsfw: bool = True
    enable_match_query: bool = True


def _md5_bytes(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def _dhash(img: Image.Image, *, size: int = 8) -> int:
    # grayscale resize to (size+1, size)
    g = img.convert("L").resize((size + 1, size))
    pixels = list(g.getdata())
    rows = [pixels[i * (size + 1) : (i + 1) * (size + 1)] for i in range(size)]
    bits = 0
    for r in rows:
        for i in range(size):
            bits = (bits << 1) | (1 if r[i] > r[i + 1] else 0)
    return bits


def _hamming(a: int, b: int) -> int:
    x = a ^ b
    # Python < 3.8 没有 int.bit_count
    try:
        return x.bit_count()  # type: ignore[attr-defined]
    except Exception:
        n = 0
        while x:
            x &= x - 1
            n += 1
        return n


def download_image(url: str, *, timeout: int = 30) -> Tuple[Optional[bytes], str]:
    try:
        r = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": "https://image.baidu.com/",
            },
        )
        if r.status_code != 200:
            return None, f"http_{r.status_code}"
        if not r.content:
            return None, "empty"
        return r.content, ""
    except Exception as e:
        return None, f"download_error:{e.__class__.__name__}"


def batch_download_images(
    urls: List[str],
    *,
    max_workers: int = DOWNLOAD_CONCURRENCY,
    timeout: int = 30,
) -> List[Tuple[int, str, Optional[bytes], str]]:
    """
    并发下载多张图片，返回 [(index, url, bytes|None, error), ...]。
    保持原始顺序的 index，方便后续按顺序处理。
    """
    results: List[Tuple[int, str, Optional[bytes], str]] = []

    def _fetch(idx_url: Tuple[int, str]) -> Tuple[int, str, Optional[bytes], str]:
        idx, url = idx_url
        b, err = download_image(url, timeout=timeout)
        return (idx, url, b, err)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_fetch, (i, u)): (i, u)
            for i, u in enumerate(urls)
        }
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                idx, url = futures[future]
                results.append((idx, url, None, f"thread_error:{e.__class__.__name__}"))

    # 按 index 排序恢复顺序
    results.sort(key=lambda x: x[0])
    logger.info("batch_download: requested=%d, completed=%d", len(urls), len(results))
    return results


def _decode_image(b: bytes) -> Tuple[Optional[Image.Image], str]:
    try:
        im = Image.open(io.BytesIO(b))
        im.load()
        return im, ""
    except Exception as e:
        return None, f"decode_error:{e.__class__.__name__}"


def _qwen_mm_clean_one_wrapped(args: Tuple) -> Dict[str, Any]:
    """包装 qwen_mm_clean_one 用于线程池调用"""
    client, query, image_bytes = args
    try:
        return qwen_mm_clean_one(client, query=query, image_bytes=image_bytes)
    except Exception as e:
        return {"_error": str(e)}


def clean_images(
    urls: List[str],
    out_dir: Path,
    *,
    cfg: CleanConfig,
    progress_callback = None,  # 可选回调: (stage, current, total) -> None
) -> Tuple[List[Dict[str, Any]], List[Path]]:
    """
    下载 + 清洗，返回 (report_rows, kept_image_paths)。
    
    优化：
    - 使用 ThreadPoolExecutor 并发下载图片（默认8线程）
    - 使用 ThreadPoolExecutor 并发调用 Qwen 多模态 API（默认4线程）
    
    progress_callback(stage, current, total): 
      stage: 'downloading' | 'filtering' | 'ai_cleaning' | 'saving' | 'done'
      当 stage='done' 时, current=kept_count
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    report: List[Dict[str, Any]] = []
    kept: List[Path] = []
    seen_md5: set[str] = set()
    seen_hashes: List[int] = []

    client = None
    if cfg.enable_nsfw or cfg.enable_match_query:
        client = build_modelscope_mm_client()

    # ===== 阶段1：并发下载所有图片 =====
    logger.info("clean_images: 开始并发下载 %d 张图片 (workers=%d)...", len(urls), DOWNLOAD_CONCURRENCY)
    if progress_callback:
        progress_callback("downloading", 0, len(urls))
    download_results = batch_download_images(urls)
    if progress_callback:
        progress_callback("downloading", len(download_results), len(urls))

    # ===== 阶段2：本地过滤（MD5/尺寸/dHash）+ 收集需要AI清洗的图片 =====
    need_ai_clean: List[Tuple[int, Dict[str, Any], bytes]] = []  # (原始idx, row, image_bytes)
    filtered_count = 0
    
    for idx, url, b, derr in download_results:
        row: Dict[str, Any] = {
            "index": idx + 1,
            "url": url,
            "kept": False,
            "reason": "",
        }
        
        if not b:
            row["reason"] = derr or "download_failed"
            report.append(row)
            continue
        
        row["bytes"] = len(b)
        md5 = _md5_bytes(b)
        row["md5"] = md5
        
        if cfg.dedup_md5 and md5 in seen_md5:
            row["reason"] = "dedup_md5"
            report.append(row)
            continue

        im, ierr = _decode_image(b)
        if not im:
            row["reason"] = ierr
            report.append(row)
            continue
            
        w, h = im.size
        row["width"], row["height"] = w, h
        if w < cfg.min_width or h < cfg.min_height:
            row["reason"] = "too_small"
            report.append(row)
            continue

        if cfg.dedup_dhash:
            dh = _dhash(im)
            dup = any(_hamming(dh, x) <= cfg.dhash_threshold for x in seen_hashes)
            if dup:
                row["reason"] = "dedup_phash"
                report.append(row)
                continue
            seen_hashes.append(dh)

        # 通过本地过滤，收集起来等待 AI 清洗
        need_ai_clean.append((len(report), row, b))
        filtered_count += 1
        if progress_callback and filtered_count % max(1, len(download_results) // 10) == 0:
            progress_callback("filtering", filtered_count, len(download_results))

    logger.info("clean_images: 本地过滤完成，%d/%d 张通过，进入 AI 清洗阶段...", len(need_ai_clean), len(urls))
    if progress_callback:
        progress_callback("filtering", len(need_ai_clean), len(urls))
    
    # ===== 阶段3：并发 AI 清洗（Qwen 多模态） =====
    ai_results: Dict[int, Optional[Dict[str, Any]]] = {}  # report_idx -> mm_result
    
    if client and need_ai_clean:
        if progress_callback:
            progress_callback("ai_cleaning", 0, len(need_ai_clean))
        
        def _ai_task(args):
            """单个 AI 清洗任务"""
            report_idx, _, img_bytes = args
            try:
                return (
                    report_idx,
                    qwen_mm_clean_one(
                        client,
                        query=cfg.query,
                        image_bytes=img_bytes,
                        model=(cfg.mm_model or None) or None,
                    ),
                )
            except Exception as e:
                return (report_idx, {"_error": str(e)})
        
        with ThreadPoolExecutor(max_workers=CLEAN_CONCURRENCY) as executor:
            futures = {executor.submit(_ai_task, item): item for item in need_ai_clean}
            completed = 0
            total = len(futures)
            for future in as_completed(futures):
                completed += 1
                try:
                    report_idx, mm_result = future.result()
                    ai_results[report_idx] = mm_result
                except Exception as e:
                    report_idx = futures[future][0]
                    ai_results[report_idx] = {"_error": str(e)}
                
                # 进度回调
                if completed % max(1, total // 10) == 0 or completed == total:
                    logger.info("AI 清洗进度: %d/%d (%.0f%%)", completed, total, completed / total * 100)
                    if progress_callback:
                        progress_callback("ai_cleaning", completed, total)

    # ===== 阶段4：合并结果并保存图片 =====
    if progress_callback:
        progress_callback("saving", 0, len(need_ai_clean))
    
    for report_idx, row, b in need_ai_clean:
        # 查找 AI 清洗结果
        mm = ai_results.get(report_idx)
        
        if mm:
            row["mm"] = mm
            # safety filter
            safety = mm.get("safety") if isinstance(mm, dict) else None
            if cfg.enable_nsfw and isinstance(safety, dict) and safety.get("blocked") is True:
                row["reason"] = "blocked_safety"
                report.append(row)
                continue
            # match filter
            mq = mm.get("match_query") if isinstance(mm, dict) else None
            if cfg.enable_match_query and isinstance(mq, dict) and mq.get("ok") is False:
                row["reason"] = "mismatch_query"
                report.append(row)
                continue

        # keep
        seen_md5.add(row.get("md5", ""))
        ext = ".jpg"
        fname = f"{len(kept)+1:06d}.jpg"
        out_path = out_dir / fname
        
        # 重新解码图片保存
        im, _ = _decode_image(b)
        if im:
            try:
                im_rgb = im.convert("RGB")
                im_rgb.save(out_path, format="JPEG", quality=92, optimize=True)
            except Exception:
                out_path.write_bytes(b)
        else:
            out_path.write_bytes(b)
            
        row["kept"] = True
        row["path"] = out_path.name
        row["reason"] = "ok"
        kept.append(out_path)
        report.append(row)
        
        if len(kept) >= cfg.count:
            break

    # 对 report 按 index 排序
    report.sort(key=lambda r: r.get("index", 0))
    
    # 完成
    if progress_callback:
        progress_callback("done", len(kept), len(kept))
    
    return report, kept


def write_report_jsonl(rows: List[Dict[str, Any]], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

