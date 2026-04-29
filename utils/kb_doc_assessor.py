from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from utils.text_format import normalize_display_text, sanitize_xml_compatible_text


@dataclass(frozen=True)
class AssessResult:
    status: str  # processable | needs_fix | rejected
    tags: List[str]
    text: str
    text_hash: str


_AI_TOPIC_KEYWORDS = (
    "人工智能",
    "机器学习",
    "深度学习",
    "神经网络",
    "监督学习",
    "无监督学习",
    "强化学习",
    "分类",
    "回归",
    "聚类",
    "损失函数",
    "梯度下降",
    "反向传播",
    "优化器",
    "卷积",
    "RNN",
    "LSTM",
    "Transformer",
    "注意力机制",
    "NLP",
    "计算机视觉",
    "CV",
    "PyTorch",
    "TensorFlow",
    "sklearn",
    "数据集",
)


def _md5_text(t: str) -> str:
    return hashlib.md5((t or "").encode("utf-8"), usedforsecurity=False).hexdigest()  # type: ignore[call-arg]


def _garbage_ratio(t: str) -> float:
    if not t:
        return 1.0
    # 粗略判定乱码：大量不可打印符、替换符、或异常符号比例
    bad = 0
    total = 0
    for ch in t:
        total += 1
        o = ord(ch)
        if ch == "\ufffd":
            bad += 1
        elif o < 0x20 and ch not in ("\n", "\t", "\r"):
            bad += 1
        elif 0xD800 <= o <= 0xDFFF:
            bad += 1
    return bad / max(1, total)


def _looks_ai_related(t: str) -> bool:
    low = (t or "").lower()
    hit = 0
    for kw in _AI_TOPIC_KEYWORDS:
        if kw.lower() in low:
            hit += 1
            if hit >= 2:
                return True
    return False


def assess_text(text: str) -> Tuple[str, List[str], str]:
    tags: List[str] = []
    raw = sanitize_xml_compatible_text(text or "")
    cleaned = normalize_display_text(raw, multiline=True)
    if not cleaned.strip():
        return "rejected", ["empty"], ""

    if len(cleaned) < 120:
        tags.append("too_short")
    gr = _garbage_ratio(cleaned)
    if gr >= 0.08:
        tags.append("garbled")
    if not _looks_ai_related(cleaned):
        tags.append("topic_uncertain")

    if "garbled" in tags:
        return "needs_fix", tags, cleaned
    if "too_short" in tags:
        return "needs_fix", tags, cleaned
    return "processable", tags, cleaned


def assess_file(path: Path, *, extracted_text: str) -> AssessResult:
    status, tags, cleaned = assess_text(extracted_text)
    return AssessResult(status=status, tags=tags, text=cleaned, text_hash=_md5_text(cleaned))

