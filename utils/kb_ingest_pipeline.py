from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from utils.aspose_docx_processor import ensure_aspose_installed
from utils.kb_doc_assessor import AssessResult, assess_file
from utils.kb_doc_fixer import FixResult, fix_text
from utils.text_format import truncate_preserving_readability

# 默认入库：课程文档 + 本站 API / MCP 说明（可分桶检索）
DEFAULT_KB_ROOTS: Tuple[str, ...] = ("zsk/AI", "zsk/API_MCP")

_TEXT_EXTS = frozenset(
    {
        ".txt",
        ".md",
        ".markdown",
        ".json",
        ".jsonl",
        ".yaml",
        ".yml",
        ".http",
        ".graphql",
        ".ts",
        ".js",
        ".mjs",
        ".cjs",
        ".py",
        ".sh",
        ".csv",
    }
)


@dataclass(frozen=True)
class IngestFileRow:
    source_path: str
    ext: str
    status: str  # processable|needs_fix|rejected
    tags: List[str]
    fix_actions: List[str]
    text_chars: int
    text_hash: str
    elapsed_ms: int
    ts: int


def _extract_docx_text_aspose(path: Path) -> str:
    # 知识库入库：优先 Aspose（更稳），若当前环境未装则回退 python-docx 抽取文本。
    try:
        ensure_aspose_installed()
        import aspose.words as aw  # type: ignore

        doc = aw.Document(str(path))
        t = doc.get_text() or ""
        t = t.replace("\r", "").replace("\x07", " ")
        return t.strip()
    except Exception:
        from utils.office_extract import extract_docx_text  # noqa: PLC0415

        raw = path.read_bytes()
        return extract_docx_text(raw)


def scan_ai_folder(root: Path) -> List[Path]:
    root = Path(root)
    if not root.exists():
        return []
    files: List[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.name.startswith("~$"):
            continue
        files.append(p)
    return files


def kb_bucket_for_path(path: Path, project_root: Path) -> str:
    """向量库分桶：api_mcp 与 ai_course，供问答时按意图过滤。"""
    try:
        rel = path.resolve().relative_to(project_root.resolve())
    except ValueError:
        rel = path
    for part in Path(rel).parts:
        if part.lower() == "api_mcp":
            return "api_mcp"
    return "ai_course"


def chunk_stable_id(path: Path, text_hash: str, chunk_index: int) -> str:
    sig = hashlib.md5(str(path.resolve()).encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
    return f"{sig}:{text_hash}:{chunk_index}"


def assess_and_fix_one(path: Path) -> Tuple[AssessResult, FixResult]:
    ext = path.suffix.lower()
    if ext == ".docx":
        raw = _extract_docx_text_aspose(path)
    elif ext in _TEXT_EXTS:
        raw = path.read_text(encoding="utf-8", errors="replace")
    else:
        raw = ""
    assessed = assess_file(path, extracted_text=raw)
    fixed = fix_text(assessed.text)
    return assessed, fixed


def chunk_text(text: str, *, max_chars: int = 1100, overlap: int = 160) -> List[str]:
    """
    简单分块：优先按段落分割，段落过长则再按可读性截断。
    """
    t = (text or "").strip()
    if not t:
        return []
    paras = [p.strip() for p in t.split("\n\n") if p.strip()] or [t]
    chunks: List[str] = []
    buf: List[str] = []
    cur = 0
    for p in paras:
        if len(p) > max_chars:
            # flush buffer
            if buf:
                chunks.append("\n\n".join(buf).strip())
                buf, cur = [], 0
            # split long para (保证每轮都前进，避免死循环/爆内存)
            step = max(1, int(max_chars) - max(0, int(overlap)))
            s = p.strip()
            pos = 0
            n = len(s)
            while pos < n:
                window = s[pos : pos + max_chars]
                if len(window) <= max_chars:
                    head = window
                else:
                    head = truncate_preserving_readability(window, max_chars)
                    # 兜底：若截断函数返回空/不前进，强制切片推进
                    if not head:
                        head = window[:max_chars]
                chunks.append(head.strip())
                if pos + max_chars >= n:
                    break
                pos += step
            continue
        if cur + len(p) + 2 > max_chars and buf:
            chunks.append("\n\n".join(buf).strip())
            buf = [p]
            cur = len(p)
        else:
            buf.append(p)
            cur += len(p) + 2
    if buf:
        chunks.append("\n\n".join(buf).strip())

    # 注意：不要在这里把“上一块尾巴”再拼接进下一块，否则会导致文本膨胀并触发内存问题。
    return chunks


def write_ingest_report_jsonl(rows: List[IngestFileRow], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r.__dict__, ensure_ascii=False) + "\n")


def assess_folder_and_write_report(
    *,
    root: Path,
    report_path: Path,
) -> Dict[str, int]:
    files = scan_ai_folder(root)
    rows: List[IngestFileRow] = []
    counts = {"total": 0, "processable": 0, "needs_fix": 0, "rejected": 0}
    for p in files:
        t0 = time.time()
        counts["total"] += 1
        ext = p.suffix.lower().lstrip(".")
        fix_actions: List[str] = []
        tags: List[str] = []
        status = "rejected"
        text_hash = ""
        text_chars = 0
        try:
            assessed, fixed = assess_and_fix_one(p)
            status = assessed.status
            tags = assessed.tags
            fix_actions = fixed.actions
            text_hash = assessed.text_hash
            text_chars = len(fixed.text or "")
        except Exception as e:
            status = "rejected"
            tags = ["exception"]
            fix_actions = [str(e)]
        counts[status] = counts.get(status, 0) + 1
        rows.append(
            IngestFileRow(
                source_path=str(p),
                ext=ext,
                status=status,
                tags=tags,
                fix_actions=fix_actions,
                text_chars=text_chars,
                text_hash=text_hash,
                elapsed_ms=int((time.time() - t0) * 1000),
                ts=int(time.time()),
            )
        )
    write_ingest_report_jsonl(rows, report_path)
    return counts


def assess_roots_and_write_report(
    *,
    roots: List[Path],
    report_path: Path,
) -> Dict[str, int]:
    """多目录扫描并写入同一份 ingest_report（每文件一行）。"""
    rows: List[IngestFileRow] = []
    counts = {"total": 0, "processable": 0, "needs_fix": 0, "rejected": 0}
    for root in roots:
        for p in scan_ai_folder(root):
            t0 = time.time()
            counts["total"] += 1
            ext = p.suffix.lower().lstrip(".")
            fix_actions: List[str] = []
            tags: List[str] = []
            status = "rejected"
            text_hash = ""
            text_chars = 0
            try:
                assessed, fixed = assess_and_fix_one(p)
                status = assessed.status
                tags = assessed.tags
                fix_actions = fixed.actions
                text_hash = assessed.text_hash
                text_chars = len(fixed.text or "")
            except Exception as e:
                status = "rejected"
                tags = ["exception"]
                fix_actions = [str(e)]
            counts[status] = counts.get(status, 0) + 1
            rows.append(
                IngestFileRow(
                    source_path=str(p),
                    ext=ext,
                    status=status,
                    tags=tags,
                    fix_actions=fix_actions,
                    text_chars=text_chars,
                    text_hash=text_hash,
                    elapsed_ms=int((time.time() - t0) * 1000),
                    ts=int(time.time()),
                )
            )
    write_ingest_report_jsonl(rows, report_path)
    return counts

