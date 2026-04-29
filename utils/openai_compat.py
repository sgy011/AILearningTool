"""
统一管理 OpenAI 兼容 API 的 base_url / api_key 选择。

支持两种入口：
- modelscope（默认）：https://api-inference.modelscope.cn/v1，使用 MODELSCOPE_TOKEN
- moonshot：Kimi 官方 https://api.moonshot.cn/v1，使用 MOONSHOT_API_KEY
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class OpenAICompatConfig:
    provider: str
    base_url: str
    api_key: str


def get_default_chat_model(*, provider: Optional[str] = None) -> str:
    """
    provider=moonshot 时默认使用 Kimi 官方模型名；provider=modelscope 时使用魔塔侧模型名。
    """
    p = (provider or os.getenv("AI_API_PROVIDER") or "modelscope").strip().lower()
    if p in ("moonshot", "kimi", "moonshotai"):
        return (os.getenv("MOONSHOT_CHAT_MODEL") or "kimi-k2.5").strip()
    return (os.getenv("MODELSCOPE_CHAT_MODEL") or "moonshotai/Kimi-K2.5").strip()


def get_default_clean_model(*, provider: Optional[str] = None) -> str:
    """
    文档文稿处理默认模型：
    - moonshot: kimi-k2.5
    - modelscope: moonshotai/Kimi-K2.5
    可被 AI_CLEAN_MODEL 覆盖。
    """
    p = (provider or os.getenv("AI_API_PROVIDER") or "modelscope").strip().lower()
    if p in ("moonshot", "kimi", "moonshotai"):
        return "kimi-k2.5"
    return "moonshotai/Kimi-K2.5"


def _normalize_v1_base_url(raw: str, *, default: str) -> str:
    t = (raw or "").strip().rstrip("/")
    if not t:
        t = default.rstrip("/")
    if t.endswith("/v1"):
        return t
    return t + "/v1"


def get_openai_compat_config(*, override_provider: Optional[str] = None) -> OpenAICompatConfig:
    """
    返回当前配置的 OpenAI 兼容 API 连接信息。

    环境变量：
    - AI_API_PROVIDER: modelscope | moonshot（默认 modelscope）
    - MODELSCOPE_TOKEN / MODELSCOPE_BASE_URL
    - MOONSHOT_API_KEY / MOONSHOT_BASE_URL
    """
    provider = (override_provider or os.getenv("AI_API_PROVIDER") or "modelscope").strip().lower()
    if provider in ("moonshot", "kimi", "moonshotai"):
        api_key = (os.getenv("MOONSHOT_API_KEY") or "").strip()
        base_url = _normalize_v1_base_url(
            os.getenv("MOONSHOT_BASE_URL") or "https://api.moonshot.cn",
            default="https://api.moonshot.cn",
        )
        return OpenAICompatConfig(provider="moonshot", base_url=base_url, api_key=api_key)

    api_key = (os.getenv("MODELSCOPE_TOKEN") or "").strip()
    base_url = _normalize_v1_base_url(
        os.getenv("MODELSCOPE_BASE_URL") or "https://api-inference.modelscope.cn",
        default="https://api-inference.modelscope.cn",
    )
    return OpenAICompatConfig(provider="modelscope", base_url=base_url, api_key=api_key)

