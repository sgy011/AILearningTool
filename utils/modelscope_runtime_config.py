"""
ModelScope 运行时配置：instance/modelscope_runtime.json 覆盖 os.environ（在 load_dotenv 之后应用）。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)

# 运行时覆盖的环境变量白名单
_KEYS = (
    "AI_API_PROVIDER",
    "MODELSCOPE_TOKEN",
    "MODELSCOPE_BASE_URL",
    "MODELSCOPE_CHAT_MODEL",
    "MOONSHOT_CHAT_MODEL",
    "MOONSHOT_API_KEY",
    "MOONSHOT_BASE_URL",
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTANCE_DIR = os.path.join(PROJECT_ROOT, "instance")
RUNTIME_FILE = os.path.join(INSTANCE_DIR, "modelscope_runtime.json")


def _ensure_instance() -> None:
    os.makedirs(INSTANCE_DIR, exist_ok=True)


def _read_file() -> Dict[str, str]:
    if not os.path.isfile(RUNTIME_FILE):
        return {}
    try:
        with open(RUNTIME_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return {}
        return {k: str(v).strip() for k, v in raw.items() if k in _KEYS and str(v).strip()}
    except Exception as e:
        logger.warning("读取 ModelScope 运行时配置失败：%s", e)
        return {}


def _write_file(data: Dict[str, str]) -> None:
    _ensure_instance()
    out = {k: data[k] for k in _KEYS if data.get(k)}
    with open(RUNTIME_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


def apply_file_to_environ() -> None:
    for k, v in _read_file().items():
        if v:
            os.environ[k] = v


def load_and_apply_runtime_modelscope() -> None:
    """在 load_dotenv() 之后调用。"""
    apply_file_to_environ()


def get_public_settings() -> Dict[str, Any]:
    provider = (os.getenv("AI_API_PROVIDER") or "modelscope").strip().lower()
    ms_token = (os.getenv("MODELSCOPE_TOKEN") or "").strip()
    ms_base = (os.getenv("MODELSCOPE_BASE_URL") or "").strip() or "https://api-inference.modelscope.cn/v1"
    chat_model = (os.getenv("MODELSCOPE_CHAT_MODEL") or "").strip() or "moonshotai/Kimi-K2.5"
    moon_chat_model = (os.getenv("MOONSHOT_CHAT_MODEL") or "").strip() or "kimi-k2.5"
    moon_key = (os.getenv("MOONSHOT_API_KEY") or "").strip()
    moon_base = (os.getenv("MOONSHOT_BASE_URL") or "").strip() or "https://api.moonshot.cn/v1"

    def _preview(s: str) -> str:
        if len(s) > 8:
            return s[:4] + "…" + s[-4:]
        if s:
            return "（已配置）"
        return ""

    return {
        "provider": provider,
        "token_set": bool(ms_token),
        "token_preview": _preview(ms_token),
        "base_url": ms_base,
        "chat_model": chat_model,
        "moonshot_chat_model": moon_chat_model,
        "moonshot_key_set": bool(moon_key),
        "moonshot_key_preview": _preview(moon_key),
        "moonshot_base_url": moon_base,
    }


def apply_runtime_payload(payload: dict) -> None:
    """
    根据前端提交更新运行时文件与 os.environ。

    - clear_token: True 时删除 Token。
    - token: 非空字符串时更新 Token；未传该键或空串表示不改 Token（除非 clear_token）。
    - base_url / chat_model: 键存在时，非空则写入，空串则删除运行时覆盖项。
    """
    data = _read_file()
    for k in _KEYS:
        ev = (os.getenv(k) or "").strip()
        if ev and k not in data:
            data[k] = ev

    # provider（AI_API_PROVIDER）
    if "provider" in payload:
        pv = (payload.get("provider") or "").strip().lower()
        if pv:
            data["AI_API_PROVIDER"] = pv
            os.environ["AI_API_PROVIDER"] = pv
        else:
            data.pop("AI_API_PROVIDER", None)
            os.environ.pop("AI_API_PROVIDER", None)

    clear_token = payload.get("clear_token") in (True, "true", 1, "1", "yes", "on")
    if clear_token:
        data.pop("MODELSCOPE_TOKEN", None)
        os.environ.pop("MODELSCOPE_TOKEN", None)
    elif "token" in payload:
        t = (payload.get("token") or "").strip()
        if t:
            data["MODELSCOPE_TOKEN"] = t
            os.environ["MODELSCOPE_TOKEN"] = t

    clear_moon = payload.get("clear_moonshot_key") in (True, "true", 1, "1", "yes", "on")
    if clear_moon:
        data.pop("MOONSHOT_API_KEY", None)
        os.environ.pop("MOONSHOT_API_KEY", None)
    elif "moonshot_api_key" in payload:
        mk = (payload.get("moonshot_api_key") or "").strip()
        if mk:
            data["MOONSHOT_API_KEY"] = mk
            os.environ["MOONSHOT_API_KEY"] = mk

    for key_json, env_key in (
        ("base_url", "MODELSCOPE_BASE_URL"),
        ("moonshot_base_url", "MOONSHOT_BASE_URL"),
        ("chat_model", "MODELSCOPE_CHAT_MODEL"),
        ("moonshot_chat_model", "MOONSHOT_CHAT_MODEL"),
    ):
        if key_json not in payload:
            continue
        v = (payload.get(key_json) or "").strip()
        if v:
            data[env_key] = v
            os.environ[env_key] = v
        else:
            data.pop(env_key, None)
            os.environ.pop(env_key, None)

    _write_file(data)
