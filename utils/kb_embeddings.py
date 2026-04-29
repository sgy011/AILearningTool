from __future__ import annotations

import os
import time
from typing import List

from openai import OpenAI
from openai import BadRequestError, RateLimitError

from utils.openai_compat import get_openai_compat_config


def build_modelscope_embed_client() -> OpenAI:
    cfg = get_openai_compat_config(override_provider="modelscope")
    if not cfg.api_key:
        raise RuntimeError("未配置 MODELSCOPE_TOKEN，无法进行知识库向量化")
    return OpenAI(api_key=cfg.api_key, base_url=cfg.base_url, max_retries=0)


def get_embed_model() -> str:
    """
    ModelScope 的 embeddings 模型名与 OpenAI 不同，不能默认使用 text-embedding-3-small。
    必须由环境变量显式指定。
    """
    m = (os.getenv("KB_EMBED_MODEL") or os.getenv("MODELSCOPE_EMBED_MODEL") or "").strip()
    if not m:
        raise RuntimeError(
            "未配置知识库 embedding 模型。请在 .env 设置 KB_EMBED_MODEL（或 MODELSCOPE_EMBED_MODEL），"
            "填入 ModelScope 支持的 embeddings 模型 id。"
        )
    return m


def embed_texts(client: OpenAI, texts: List[str], *, model: str) -> List[List[float]]:
    if not texts:
        return []

    # 分批 + 429 退避重试，降低频控概率
    batch_size = int(os.getenv("KB_EMBED_BATCH_SIZE") or 32)
    batch_size = max(1, min(128, batch_size))
    max_retries = int(os.getenv("KB_EMBED_MAX_RETRIES") or 4)
    max_retries = max(0, min(8, max_retries))

    out: List[List[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        attempt = 0
        while True:
            try:
                resp = client.embeddings.create(model=model, input=batch)
                out.extend([d.embedding for d in resp.data])
                break
            except BadRequestError as e:
                # 典型：Invalid model id
                raise RuntimeError(f"Embeddings 请求失败（BadRequest）：{e}") from e
            except RateLimitError as e:
                attempt += 1
                if attempt > max_retries:
                    raise RuntimeError(f"Embeddings 触发限流（429），重试次数已用尽：{e}") from e
                # 1.2, 2.4, 4.8, 9.6...
                time.sleep(1.2 * (2 ** (attempt - 1)))
    return out

