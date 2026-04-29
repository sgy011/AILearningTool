from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from utils.text_format import normalize_display_text, sanitize_xml_compatible_text


@dataclass(frozen=True)
class FixResult:
    text: str
    actions: List[str]


_RE_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_RE_PAGE_NUM = re.compile(r"^\s*(第?\s*\d+\s*页|Page\s*\d+)\s*$", re.IGNORECASE)


def fix_text(text: str) -> FixResult:
    actions: List[str] = []
    t = sanitize_xml_compatible_text(text or "")
    if t != (text or ""):
        actions.append("sanitize_xml")

    # 统一换行/空白
    t2 = normalize_display_text(t, multiline=True)
    if t2 != t:
        actions.append("normalize_display")
    t = t2

    # 去疑似页码行
    lines = []
    dropped = 0
    for line in t.split("\n"):
        if _RE_PAGE_NUM.match(line):
            dropped += 1
            continue
        lines.append(line)
    if dropped:
        actions.append(f"drop_page_numbers:{dropped}")
    t = "\n".join(lines).strip()

    # 压缩行内多空格（保留换行）
    t2 = _RE_MULTI_SPACE.sub(" ", t)
    if t2 != t:
        actions.append("collapse_spaces")
    t = t2

    return FixResult(text=t.strip(), actions=actions)

