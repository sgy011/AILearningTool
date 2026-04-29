"""
使用 Aspose.Words 尝试弱化/移除评估版常见水印文案（页眉页脚、正文段落、字段）。

依赖：aspose-words（与项目其他 Aspose 用法一致）。商业使用请使用正式许可证；
本模块不能替代合法许可，仅作技术清理辅助。
"""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path
from typing import Any, List, Optional

from utils.aspose_docx_processor import ensure_aspose_installed

logger = logging.getLogger(__name__)

# 正文/页眉页脚中评估提示常见片段（小写比较）
_EVAL_MARKERS = (
    "evaluation only",
    "created with aspose",
    "created with an evaluation copy",
    "aspose pty ltd",
    "evaluation version",
    "temporary license",
    "free temporary license",
    "products.aspose.com",
)

_WATERMARK_RE = re.compile(
    r"(?is)"
    r"(created\s+with\s+an\s+evaluation\s+copy\s+of\s+aspose\.words.*?temporary-license/?)"
    r"|"
    r"(evaluation\s+only\.\s*created\s+with\s+aspose\.words\..*?aspose\s+pty\s+ltd\.?)"
    r"|"
    r"(created\s+with\s+aspose(?:\.words)?\.)"
    r"|"
    r"(evaluation\s+only)"
    r"|"
    r"(aspose\s+pty\s+ltd\.?)"
    r"|"
    r"(products\.aspose\.com/words/temporary-license/?)+"
)


def _para_has_images(aw: Any, para: Any) -> bool:
    """段落内是否包含图片/形状，若有则不要整段删除。"""
    try:
        # ShapeType.IMAGE 的枚举在 aw.drawing.ShapeType
        shapes = para.get_child_nodes(aw.NodeType.SHAPE, True)
        if shapes and shapes.count > 0:
            return True
    except Exception:
        pass
    return False


def _strip_watermark_text_in_paragraph(aw: Any, para: Any) -> bool:
    """
    仅删除段落中匹配水印的文本（Run），保留图片等其它节点。
    返回：是否做过修改
    """
    changed = False
    try:
        runs = getattr(para, "runs", None)
        if runs is None:
            return False
        for i in range(runs.count - 1, -1, -1):
            r = runs[i]
            try:
                txt = r.text or ""
            except Exception:
                continue
            if not txt:
                continue
            new_txt = _WATERMARK_RE.sub("", txt)
            if new_txt != txt:
                changed = True
                r.text = new_txt
                # 若 Run 被清空且段落有图片，保留空 Run 也无妨；否则可移除
                if not new_txt.strip() and not _para_has_images(aw, para):
                    try:
                        r.remove()
                    except Exception:
                        pass
    except Exception as e:
        logger.debug("Run 水印清理失败: %s", e)
    return changed


def _text_looks_like_aspose_watermark(text: str) -> bool:
    """是否像 Aspose 评估水印文案（页眉/页脚/正文统一规则）。"""
    t = (text or "").lower()
    if not t.strip():
        return False
    if "aspose" in t or "evaluation" in t:
        return True
    if "temporary license" in t or "temporary-license" in t:
        return True
    if "products.aspose.com" in t:
        return True
    if "hyperlink" in t and ("aspose" in t or "temporary" in t):
        return True
    if any(m in t for m in _EVAL_MARKERS):
        return True
    # 正则命中（覆盖你提供的完整长句）
    return bool(_WATERMARK_RE.search(text or ""))


def _remove_fields_with_keywords(para: Any, keywords: tuple[str, ...]) -> bool:
    """若段落内字段代码含关键词则移除整段，返回是否移除。"""
    try:
        rng = para.range
        fields = getattr(rng, "fields", None)
        if fields is None:
            return False
        for field in fields:
            try:
                code = field.get_field_code().lower()
            except Exception:
                code = ""
            if any(k in code for k in keywords):
                try:
                    para.remove()
                except Exception:
                    pass
                return True
    except Exception as e:
        logger.debug("字段扫描跳过: %s", e)
    return False


def _strip_watermarks_in_document(doc: Any, aw: Any) -> None:
    """
    就地处理 doc：删除页眉/页脚/正文（含表格单元格、文本框等子层）
    中「文本或字段」含 Aspose / evaluation 等评估提示的段落。
    """
    kw_fields = ("aspose", "temporary-license", "products.aspose")
    paras = list(doc.get_child_nodes(aw.NodeType.PARAGRAPH, True))
    for para in reversed(paras):
        try:
            txt = para.get_text()
            if _text_looks_like_aspose_watermark(txt):
                # 段落里有图片/形状：只删除水印文本，不删段落
                if _para_has_images(aw, para):
                    _strip_watermark_text_in_paragraph(aw, para)
                else:
                    # 先尝试只删文本（更安全），若删完为空再删段落
                    changed = _strip_watermark_text_in_paragraph(aw, para)
                    new_txt = (para.get_text() or "").strip()
                    if not new_txt or (not changed and _text_looks_like_aspose_watermark(new_txt)):
                        para.remove()
                continue
            _remove_fields_with_keywords(para, kw_fields)
        except Exception as e:
            logger.debug("水印段落处理跳过: %s", e)


def remove_evaluation_watermark(docx_path: str, output_path: Optional[str] = None) -> str:
    """
    尝试移除 Aspose 评估水印：删除页眉/页脚/正文中含 Aspose、evaluation、临时许可链接等字样的段落，
    以及字段代码中含相关关键词的段落。

    :param docx_path: 输入 .docx 路径
    :param output_path: 输出路径；默认在同目录生成 ``*_clean.docx``
    """
    ensure_aspose_installed()
    import aspose.words as aw  # type: ignore

    docx_path = str(Path(docx_path))
    if output_path is None:
        p = Path(docx_path)
        output_path = str(p.with_name(p.stem + "_clean.docx"))
    else:
        output_path = str(Path(output_path))

    doc = aw.Document(docx_path)
    _strip_watermarks_in_document(doc, aw)
    doc.save(output_path)
    logger.info("水印清理已保存: %s", output_path)
    return output_path


def remove_evaluation_watermark_bytes(docx_bytes: bytes) -> bytes:
    """内存中处理 .docx，返回清理后的字节。"""
    ensure_aspose_installed()
    import aspose.words as aw  # type: ignore

    doc = aw.Document(io.BytesIO(docx_bytes))
    _strip_watermarks_in_document(doc, aw)
    out = io.BytesIO()
    doc.save(out, aw.SaveFormat.DOCX)
    return out.getvalue()


def insert_rebuilt_table(builder: Any, table_lines: List[str]) -> None:
    """使用 DocumentBuilder 在光标处插入由管道行解析出的表格。"""
    if not table_lines:
        return
    first_line = table_lines[0]
    cols = len([c for c in first_line.split("|") if c.strip()])
    if cols == 0:
        return

    builder.start_table()
    for line in table_lines:
        cells = [c.strip() for c in line.split("|") if c.strip()]
        while len(cells) < cols:
            cells.append("")
        cells = cells[:cols]
        for cell_text in cells:
            builder.insert_cell()
            builder.write(cell_text)
        builder.end_row()
    builder.end_table()
    builder.writeln()


def clean_and_rebuild_tables(docx_path: str, output_path: str) -> str:
    """
    先按 :func:`remove_evaluation_watermark` 清理水印，再尝试将「管道状」连续段落重建为表格。

    表格检测规则较启发式（含 ``|``、分隔线或特定关键词），可能误匹配；请按需调用。
    """
    ensure_aspose_installed()
    import aspose.words as aw  # type: ignore

    docx_path = str(Path(docx_path))
    output_path = str(Path(output_path))

    clean_path = remove_evaluation_watermark(docx_path)
    doc = aw.Document(clean_path)
    builder = aw.DocumentBuilder(doc)

    paragraphs = list(doc.get_child_nodes(aw.NodeType.PARAGRAPH, True))
    i = 0
    while i < len(paragraphs):
        para = paragraphs[i]
        text = para.get_text().strip()
        looks_table = "|" in text and (
            "---" in text or "文档 ID" in text or "目标网站" in text
        )
        if not looks_table:
            i += 1
            continue

        j = i
        table_lines: List[str] = []
        while j < len(paragraphs) and "|" in paragraphs[j].get_text():
            line_text = paragraphs[j].get_text().strip()
            if "---" not in line_text:
                table_lines.append(line_text)
            j += 1

        if len(table_lines) < 2:
            i += 1
            continue

        nodes = [paragraphs[k] for k in range(i, j)]
        builder.move_to(nodes[0])
        insert_rebuilt_table(builder, table_lines)
        for node in reversed(nodes):
            node.remove()

        paragraphs = list(doc.get_child_nodes(aw.NodeType.PARAGRAPH, True))
        i = 0
        continue

    doc.save(output_path)
    logger.info("表格重建已保存: %s", output_path)
    return output_path
