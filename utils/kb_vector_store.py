from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class KBHit:
    id: str
    text: str
    score: float
    metadata: Dict[str, Any]


def _kb_dir() -> Path:
    root = Path(__file__).resolve().parent.parent
    return (root / "instance" / "kb_chroma").resolve()


def _require_chromadb():
    # 必须在 import chromadb 之前关闭遥测。
    # 否则在部分 Python 版本/依赖组合下会 import posthog 并触发
    # TypeError: 'type' object is not subscriptable（常见于 Python<3.9）。
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    os.environ.setdefault("CHROMA_TELEMETRY", "false")
    os.environ.setdefault("CHROMA_ANONYMIZED_TELEMETRY", "false")
    os.environ.setdefault("POSTHOG_DISABLED", "1")
    try:
        import chromadb  # type: ignore

        return chromadb
    except ImportError as e:
        raise RuntimeError("未安装 chromadb，请执行：pip install chromadb") from e


def get_or_create_collection(*, name: str = "ai_courses") -> Any:
    chromadb = _require_chromadb()
    d = _kb_dir()
    d.mkdir(parents=True, exist_ok=True)
    # 禁用 Chroma 遥测，避免在部分 Python 版本下引入 posthog 导致类型注解不兼容错误
    try:
        from chromadb.config import Settings  # type: ignore

        settings = Settings(anonymized_telemetry=False)
        client = chromadb.PersistentClient(path=str(d), settings=settings)
    except Exception:
        # 兼容旧版本 chromadb：若不支持 settings 参数则退回默认构造
        client = chromadb.PersistentClient(path=str(d))
    return client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


def upsert_texts(
    collection: Any,
    *,
    ids: List[str],
    texts: List[str],
    metadatas: List[Dict[str, Any]],
    embeddings: List[List[float]],
) -> None:
    if not ids:
        return
    collection.upsert(ids=ids, documents=texts, metadatas=metadatas, embeddings=embeddings)


def query(
    collection: Any,
    *,
    query_embedding: List[float],
    top_k: int = 6,
    where: Optional[Dict[str, Any]] = None,
) -> List[KBHit]:
    kwargs: Dict[str, Any] = {
        "query_embeddings": [query_embedding],
        "n_results": int(top_k),
    }
    if where:
        kwargs["where"] = where
    res = collection.query(**kwargs)
    # Chroma returns lists-of-lists
    ids = (res.get("ids") or [[]])[0]
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    out: List[KBHit] = []
    for i in range(len(ids)):
        dist = float(dists[i]) if i < len(dists) else 0.0
        # cosine distance -> score
        score = 1.0 - dist
        out.append(
            KBHit(
                id=str(ids[i]),
                text=str(docs[i] or ""),
                score=score,
                metadata=dict(metas[i] or {}),
            )
        )
    return out

