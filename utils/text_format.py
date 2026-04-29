"""
新闻等展示用文本：规范化空格、全角/半角标点、零宽字符与段落换行。
"""

from __future__ import annotations

import html as html_module
import re
import unicodedata
from typing import Optional

# 零宽与不可见字符（保留正常换行）
_ZERO_WIDTH = (
    "\u200b",
    "\u200c",
    "\u200d",
    "\ufeff",
    "\u2060",
    "\u00ad",
)


def normalize_display_text(
    s: Optional[str],
    *,
    multiline: bool = True,
    summary_output: bool = False,
) -> str:
    """
    用于正文/摘要：NFKC、去零宽、统一空白与段落。
    multiline=False 时压成单行（标题等）。
    summary_output=True：用于 AI 总结展示，少做行内空白压缩，避免数字、并列项与标点旁信息被挤没。
    """
    if not s:
        return ""
    t = unicodedata.normalize("NFKC", str(s))
    for z in _ZERO_WIDTH:
        t = t.replace(z, "")
    t = t.replace("\xa0", " ").replace("\u3000", " ")
    t = t.replace("\r\n", "\n").replace("\r", "\n")

    # 中文标点后的普通空格收紧（不换行）
    t = re.sub(r"([，。！？、；：])[ \t]+", r"\1", t)

    if not multiline:
        t = re.sub(r"[\n\r]+", " ", t)
        t = re.sub(r"[ \t]+", " ", t).strip()
        return t

    lines: list[str] = []
    for para in t.split("\n"):
        if summary_output:
            line = para.replace("\t", " ").strip()
        else:
            line = re.sub(r"[ \t]+", " ", para.strip())
        if line:
            lines.append(line)
    t = "\n".join(lines)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def sanitize_xml_compatible_text(s: Optional[str]) -> str:
    """
    去除 XML 1.0 非法字符（含 NUL），避免 python-docx / lxml、部分 PDF 库写入失败。
    保留 Tab(0x9)、换行(0xA)、回车(0xD)；剔除其余 C0 控制符与 U+FFFE/U+FFFF、孤立的 UTF-16 代理项。
    """
    if not s:
        return ""
    out: list[str] = []
    for ch in str(s):
        o = ord(ch)
        if o < 0x20:
            if o in (0x9, 0xA, 0xD):
                out.append(ch)
            continue
        if o in (0xFFFE, 0xFFFF):
            continue
        if 0xD800 <= o <= 0xDFFF:
            continue
        if o > 0x10FFFF:
            continue
        out.append(ch)
    return "".join(out)


def decode_text_file_bytes(raw: bytes) -> str:
    """
    解码用户上传的 .txt 等纯文本：去 UTF-8 BOM；识别 UTF-16 LE/BE；优先严格 UTF-8，失败则 GB18030。
    避免对 GBK 文件使用 errors=replace 产生大量 U+FFFD。
    """
    if not raw:
        return ""
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    if len(raw) >= 2 and raw.startswith(b"\xff\xfe"):
        return raw[2:].decode("utf-16le", errors="replace")
    if len(raw) >= 2 and raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16be", errors="replace")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("gb18030")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def truncate_preserving_readability(s: Optional[str], max_chars: int, *, ellipsis: str = "…") -> str:
    """
    在不超过 max_chars（含省略号）的前提下，尽量在句读、换行或空格处截断，减少半句话与关键尾信息被切断。
    """
    if not s or max_chars <= 0:
        return ""
    t = str(s).strip()
    if len(t) <= max_chars:
        return t
    ell = ellipsis or ""
    budget = max_chars - len(ell)
    if budget < 12:
        return (t[:max_chars]) if max_chars < len(t) else t
    head = t[:budget]
    win = min(320, len(head))
    tail = head[-win:]
    seps = (
        "\n\n",
        "\n",
        "。",
        "！",
        "？",
        "……",
        "；",
        ". ",
        "! ",
        "? ",
        "; ",
        "，",
        ", ",
        "、",
    )
    min_cut = max(48, int(budget * 0.52))
    best_cut = -1
    for sep in seps:
        i = tail.rfind(sep)
        if i < 0:
            continue
        cut = len(head) - win + i + len(sep)
        if min_cut <= cut <= len(head):
            best_cut = max(best_cut, cut)
    if best_cut > 0:
        return head[:best_cut].rstrip() + ell
    sp = tail.rfind(" ")
    if sp >= 0:
        cut = len(head) - win + sp
        min_sp = max(40, int(budget * 0.45))
        if min_sp <= cut <= len(head):
            return head[:cut].rstrip() + ell
    return head.rstrip() + ell


def normalize_title(s: Optional[str]) -> str:
    """标题：单行、无多余空白。"""
    return normalize_display_text(s, multiline=False)


def normalize_from_html_fragment(raw: Optional[str]) -> str:
    """
    将简单 HTML 片段转为展示用纯文本：块级换行 + 规范化。
    """
    if not raw:
        return ""
    t = str(raw)
    t = re.sub(r"(?is)<\s*br\s*/?\s*>", "\n", t)
    t = re.sub(r"(?is)</\s*p\s*>", "\n", t)
    t = re.sub(r"(?is)<\s*p[^>]*>", "", t)
    t = re.sub(r"(?is)</\s*(div|section|article|h[1-6])\s*>", "\n", t)
    t = re.sub(r"(?is)<\s*(div|section|article|h[1-6])[^>]*>", "", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html_module.unescape(t)
    return normalize_display_text(t, multiline=True)
