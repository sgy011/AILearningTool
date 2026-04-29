"""
ModelScope 推理：文生图（异步任务）与对话（chat completions）。
Token 仅由服务端读取环境变量，勿写入前端。

Base URL 须指向 OpenAI 兼容前缀 …/v1；若只填域名未带 /v1，会自动补全。
文生图 POST 与官方示例一致：JSON UTF-8 正文 + X-ModelScope-Async-Mode。
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, Dict, List, Optional, Union

import requests
from openai import OpenAI

from utils.text_format import normalize_display_text
from utils.openai_compat import get_default_chat_model, get_openai_compat_config

logger = logging.getLogger(__name__)

DEFAULT_BASE = "https://api-inference.modelscope.cn/v1"


def normalize_modelscope_base_url(override: Optional[str] = None) -> str:
    """
    与 OpenAI 兼容接口一致，base 必须为 …/v1。
    常见错误：仅配置 https://api-inference.modelscope.cn 导致请求发到 /chat/completions 而非 /v1/chat/completions。
    """
    raw = (override or os.getenv("MODELSCOPE_BASE_URL") or DEFAULT_BASE).strip().rstrip("/")
    if not raw:
        return DEFAULT_BASE
    if raw.endswith("/v1"):
        return raw
    if "api-inference.modelscope.cn" in raw and "/v1" not in raw:
        return raw + "/v1"
    return raw


def _api_base() -> str:
    return normalize_modelscope_base_url()


def _headers_json() -> Dict[str, str]:
    token = os.getenv("MODELSCOPE_TOKEN", "").strip()
    if not token:
        raise ValueError("未配置 MODELSCOPE_TOKEN")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def start_image_generation(
    prompt: str,
    model: str = "Qwen/Qwen-Image",
    size: Optional[str] = None,
    n: int = 1,
) -> Dict[str, Any]:
    """提交异步文生图任务，返回含 task_id 的 JSON。与官方示例一致使用 UTF-8 JSON body。"""
    url = f"{_api_base()}/images/generations"
    body: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
    }
    if n and n > 1:
        body["n"] = n

    # 官方最小示例仅 model + prompt；任意 size 易触发 400。默认不传尺寸。
    env_size = (os.getenv("MODELSCOPE_IMAGE_SIZE") or "").strip()
    use_ui = os.getenv("MODELSCOPE_IMAGE_USE_UI_SIZE", "").lower() in ("1", "true", "yes")
    if env_size:
        body["size"] = env_size
    elif use_ui and size:
        mapped = _map_image_size_for_api(size)
        if mapped:
            body["size"] = mapped

    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    r = requests.post(
        url,
        headers={**_headers_json(), "X-ModelScope-Async-Mode": "true"},
        data=payload,
        timeout=120,
    )
    r.raise_for_status()
    return r.json()


def _map_image_size_for_api(size: str) -> Optional[str]:
    """部分接口使用 1024*1024 而非 x；若仍 400 可unset MODELSCOPE_IMAGE_* 并依赖仅 model+prompt。"""
    s = (size or "").strip().lower().replace(" ", "")
    if not s:
        return None
    if "*" in s:
        return s
    if "x" in s:
        return s.replace("x", "*")
    return s


def get_image_task(task_id: str) -> Dict[str, Any]:
    """查询文生图任务状态。"""
    url = f"{_api_base()}/tasks/{task_id}"
    r = requests.get(
        url,
        headers={
            **_headers_json(),
            "X-ModelScope-Task-Type": "image_generation",
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def fetch_image_as_data_url(image_url: str) -> str:
    """拉取图片 URL，返回 data:image/...;base64,..."""
    r = requests.get(image_url, timeout=120)
    r.raise_for_status()
    ctype = r.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
    if not ctype.startswith("image/"):
        ctype = "image/jpeg"
    b64 = base64.standard_b64encode(r.content).decode("ascii")
    return f"data:{ctype};base64,{b64}"


def _normalize_chat_messages(
    messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """保证 content 为字符串（纯文本对话）；多模态可传 list 结构。"""
    out: List[Dict[str, Any]] = []
    for m in messages:
        role = m.get("role") or "user"
        content: Union[str, List[Any], None] = m.get("content")
        if isinstance(content, list):
            out.append({"role": role, "content": content})
        else:
            out.append({"role": role, "content": str(content or "")})
    return out


def _chat_client() -> OpenAI:
    cfg = get_openai_compat_config()
    if not cfg.api_key:
        if cfg.provider == "moonshot":
            raise ValueError("未配置 MOONSHOT_API_KEY")
        raise ValueError("未配置 MODELSCOPE_TOKEN")
    return OpenAI(base_url=cfg.base_url, api_key=cfg.api_key)


def chat_completion(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    temperature: float = 0.7,
    *,
    normalize_output: bool = True,
) -> str:
    """
    OpenAI 兼容对话（与每日必读资讯相同：OpenAI SDK + ModelScope base_url）。
    默认模型：环境变量 MODELSCOPE_CHAT_MODEL，否则 moonshotai/Kimi-K2.5。
    normalize_output=False：不经过 normalize_display_text，便于解析 JSON 等结构化输出。
    """
    model = (model or get_default_chat_model()).strip()
    msgs = _normalize_chat_messages(messages)
    client = _chat_client()
    response = client.chat.completions.create(
        model=model,
        messages=msgs,
        temperature=temperature,
        timeout=120.0,
    )
    choice = (response.choices or [None])[0]
    if choice is None:
        return ""
    msg = choice.message
    raw = (msg.content or "") if msg else ""
    text = raw.strip() if isinstance(raw, str) else str(raw).strip()
    if not normalize_output:
        return text
    # 与新闻/文稿展示一致：NFKC、去零宽、收紧中英文标点旁空格、段落空白
    return normalize_display_text(text, multiline=True)
