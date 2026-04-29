"""
Qwen3.5 多模态清洗：给图片生成描述，并判断与查询词是否匹配、是否含敏感内容。

调用采用 OpenAI 兼容 Chat Completions（ModelScope base_url）。
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, Dict, Optional

from openai import OpenAI

from utils.modelscope_ai import normalize_modelscope_base_url

logger = logging.getLogger(__name__)


DEFAULT_MODEL = os.getenv("DATASET_QWEN_MODEL", "Qwen/Qwen3.5-397B-A17B").strip()
SUPPORTED_MM_MODELS = (
    "Qwen/Qwen3.5-397B-A17B",
    "Qwen/Qwen3-VL-8B-Instruct",
    "Qwen/Qwen3-VL-235B-A22B-Instruct",
)


def _image_bytes_to_data_url(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    t = (text or "").strip()
    if not t:
        return None
    # 去掉可能的代码围栏
    if t.startswith("```"):
        t = t.split("```", 2)[1] if "```" in t else t
        t = t.strip().strip("json").strip()
    # 尝试截取首个 {..}
    start = t.find("{")
    end = t.rfind("}")
    if start >= 0 and end > start:
        t2 = t[start : end + 1]
    else:
        t2 = t
    try:
        obj = json.loads(t2)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def build_modelscope_mm_client() -> OpenAI:
    token = (os.getenv("MODELSCOPE_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("未配置 MODELSCOPE_TOKEN（图片清洗固定走 ModelScope 多模态 Qwen3.5）")
    base_url = normalize_modelscope_base_url()
    return OpenAI(base_url=base_url, api_key=token, timeout=float(os.getenv("AI_CLEAN_OPENAI_TIMEOUT", "180")))


def qwen_mm_clean_one(
    client: OpenAI,
    *,
    query: str,
    image_bytes: bytes,
    image_mime: str = "image/jpeg",
    model: Optional[str] = None,
    max_tokens: int = 768,
    _retries: int = 2,
) -> Dict[str, Any]:
    """
    返回结构化判定：
      - caption: str
      - match_query: { ok: bool, confidence: 0-1, reason: str }
      - safety: { blocked: bool, categories: [..], reason: str }
    """
    import time as _time

    q = (query or "").strip()
    model = (model or DEFAULT_MODEL).strip()
    data_url = _image_bytes_to_data_url(image_bytes, image_mime)

    system = (
        "你是多模态数据清洗助手。请基于图像内容输出严格 JSON（不要额外文本）。\n"
        "字段：\n"
        "- caption: 用中文一句话描述图像主要内容。\n"
        "- match_query: {ok: 图像是否与查询词语义一致, confidence: 0~1, reason: 简短原因}\n"
        "- safety: {blocked: 是否包含不适合训练的敏感内容, categories: 敏感类别数组, reason: 简短原因}\n"
        "敏感类别包括但不限于：porn, violence, terrorism, politics, hate, illegal, self_harm, minors。\n"
        "只输出 JSON。"
    )
    user = [
        {"type": "text", "text": f"查询词：{q or '（无）'}"},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]

    last_raw = ""
    for attempt in range(1, _retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.2,
                max_tokens=max_tokens,
            )
            choice = (resp.choices or [None])[0]
            raw = ""
            if choice and choice.message and choice.message.content is not None:
                raw = str(choice.message.content).strip()
            last_raw = raw
            obj = _extract_json(raw) or {}
            if obj:
                return obj
            # 空 JSON，重试
            logger.warning("mm clean: empty json (attempt %d/%d), raw=%r", attempt, _retries, raw[:200])
            if attempt < _retries:
                _time.sleep(1)
        except Exception as e:
            err_str = str(e)
            # 400 Bad Request 通常无法通过重试解决，直接跳过
            if "400" in err_str or "Bad Request" in err_str:
                logger.warning("mm clean: 400 Bad Request, skipping retries: %s", err_str[:200])
                return {
                    "caption": "",
                    "match_query": {"ok": False, "confidence": 0.0, "reason": "API请求失败(400)"},
                    "safety": {"blocked": False, "categories": [], "reason": ""},
                    "_error": err_str[:200],
                }
            logger.warning("mm clean: API error (attempt %d/%d): %s", attempt, _retries, err_str[:200])
            if attempt < _retries:
                _time.sleep(2)
            else:
                return {
                    "caption": "",
                    "match_query": {"ok": False, "confidence": 0.0, "reason": f"API调用失败: {e.__class__.__name__}"},
                    "safety": {"blocked": False, "categories": [], "reason": ""},
                    "_error": err_str[:200],
                }

    # 所有重试都返回空JSON时，返回宽容结果（不过滤该图片）
    logger.warning("mm clean: all %d attempts returned empty json for query=%r", _retries, q)
    return {
        "caption": "",
        "match_query": {"ok": True, "confidence": 0.5, "reason": "模型多次未返回可解析JSON，默认放行"},
        "safety": {"blocked": False, "categories": [], "reason": ""},
        "_raw": last_raw[:200],
    }

