from __future__ import annotations

import io
from typing import List, Tuple

from utils.aspose_docx_processor import ensure_aspose_installed


def merge_docs_aspose(
    files: List[Tuple[str, bytes]],
    *,
    insert_page_break: bool = True,
) -> bytes:
    """
    使用 Aspose.Words 合并多个文档，保留原始格式与表格结构。

    files: [(filename, bytes)] 按顺序合并
    返回：合并后的 docx bytes
    """
    ensure_aspose_installed()
    import aspose.words as aw  # type: ignore

    if not files:
        raise RuntimeError("未提供要合并的文件")
    first_name, first_bytes = files[0]
    doc = aw.Document(io.BytesIO(first_bytes))
    builder = aw.DocumentBuilder(doc)

    for fname, data in files[1:]:
        other = aw.Document(io.BytesIO(data))
        if insert_page_break:
            builder.move_to_document_end()
            builder.insert_break(aw.BreakType.PAGE_BREAK)
        doc.append_document(other, aw.ImportFormatMode.KEEP_SOURCE_FORMATTING)

    out = io.BytesIO()
    doc.save(out, aw.SaveFormat.DOCX)
    return out.getvalue()


def convert_doc_aspose(doc_bytes: bytes, *, out_format: str) -> bytes:
    ensure_aspose_installed()
    import aspose.words as aw  # type: ignore

    fmt = (out_format or "docx").strip().lower()
    doc = aw.Document(io.BytesIO(doc_bytes))
    out = io.BytesIO()
    if fmt == "pdf":
        doc.save(out, aw.SaveFormat.PDF)
    else:
        doc.save(out, aw.SaveFormat.DOCX)
    return out.getvalue()

