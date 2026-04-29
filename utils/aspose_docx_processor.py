"""
使用 Aspose.Words 做 .docx 结构化抽取与回写，保持标题/正文/表格等版式不因整文档重建而丢失。

依赖：pip install aspose-words（商业组件，需自行配置许可证）。

文档文稿上传补全（generate_file_fill + docx_bytes）仅走本模块，不再使用 python-docx 抽取或重建。
保存前对输出字节调用 ``utils.aspose_watermark_remover.remove_evaluation_watermark_bytes``，弱化评估版常见水印。
"""

from __future__ import annotations

import io
import logging
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


def ensure_aspose_installed() -> None:
    """未安装 aspose-words 时抛出 ImportError，并附带当前解释器与安装命令（避免多 Python 环境装错）。"""
    try:
        import aspose.words as aw  # type: ignore  # noqa: F401
    except ImportError as e:
        py = sys.executable
        raise ImportError(
            "文档文稿 .docx 需要 Aspose.Words，但当前运行服务的 Python 里未找到 aspose 模块。\n"
            f"当前解释器：{py}\n"
            "请用**同一解释器**安装（勿单独用 pip 若它指向别的环境）：\n"
            f'  "{py}" -m pip install aspose-words\n'
            "若已在别处安装过，多半是装到了别的 Python/conda/venv；请用上面命令对当前解释器再装一次。\n"
            "商业许可需自行配置。"
        ) from e


def docx_has_processable_blocks(docx_bytes: bytes) -> bool:
    """主故事区是否存在至少一个可结构化处理的段落或表格块。"""
    ensure_aspose_installed()
    proc = AsposeDocxProcessor()
    doc = proc.load_document_bytes(docx_bytes)
    _, n = proc.extract_structured_text(doc)
    return n > 0


def plain_text_preview_from_docx_bytes(docx_bytes: bytes, max_chars: int = 120000) -> str:
    """用于 API 预览的纯文本（不经 python-docx）。"""
    ensure_aspose_installed()
    proc = AsposeDocxProcessor()
    doc = proc.load_document_bytes(docx_bytes)
    t = doc.get_text()
    t = t.replace("\r", "").replace("\x07", " ")
    if len(t) > max_chars:
        t = t[:max_chars] + "\n…"
    return t.strip()


def _try_import_aw() -> Any:
    import aspose.words as aw  # type: ignore

    return aw


class AsposeDocxProcessor:
    """使用 Aspose.Words 实现高保真 Word 结构化编辑（段落 + 表格分块）。"""

    def __init__(self) -> None:
        self._aw = _try_import_aw()

    def load_document_bytes(self, docx_bytes: bytes) -> Any:
        aw = self._aw
        stream = io.BytesIO(docx_bytes)
        return aw.Document(stream)

    def docx_to_html_with_inline_css(self, docx_path: str) -> str:
        """将 Word 转为带内联 CSS 的 HTML（可选：AI 直接改 HTML 再 load）。"""
        aw = self._aw
        doc = aw.Document(docx_path)
        save_options = aw.saving.HtmlSaveOptions()
        save_options.css_style_sheet_type = aw.saving.CssStyleSheetType.INLINE
        save_options.export_roundtrip_information = True
        if hasattr(save_options, "export_fonts_as_base64"):
            save_options.export_fonts_as_base64 = True
        tmp = Path(docx_path).with_suffix(".temp_inline.html")
        try:
            doc.save(str(tmp), save_options)
            return tmp.read_text(encoding="utf-8")
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    def html_to_docx_bytes(self, html_content: str) -> bytes:
        """从 HTML 字符串生成 .docx（依赖 Aspose 解析 HTML）。"""
        aw = self._aw
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", encoding="utf-8", delete=False
        ) as f:
            f.write(html_content)
            hpath = f.name
        try:
            doc = aw.Document(hpath)
            bio = io.BytesIO()
            doc.save(bio, aw.SaveFormat.DOCX)
            return bio.getvalue()
        finally:
            Path(hpath).unlink(missing_ok=True)

    def _iter_body_paragraphs_and_tables(self, doc: Any) -> List[Tuple[str, Any]]:
        """主故事区 body 下直接子节点：段落（非单元格内）与表格，顺序与 Word 一致。"""
        aw = self._aw
        blocks: List[Tuple[str, Any]] = []
        body = doc.first_section.body
        for node in body.get_child_nodes(aw.NodeType.ANY, False):
            if node.node_type == aw.NodeType.PARAGRAPH:
                para = node.as_paragraph()
                if not para.is_in_cell:
                    t = para.get_text().replace("\r", "").strip()
                    if t:
                        blocks.append(("para", para))
                    else:
                        blocks.append(("para", para))
            elif node.node_type == aw.NodeType.TABLE:
                blocks.append(("table", node.as_table()))
        return blocks

    def extract_structured_text(self, doc: Any) -> Tuple[str, int]:
        """
        提取带 [PARA] / [TABLE] 标记的正文；返回 (文本, 块数量)。
        表格转为 Markdown 管道表，便于模型保持行列。
        """
        blocks = self._iter_body_paragraphs_and_tables(doc)
        lines: List[str] = []
        for kind, obj in blocks:
            if kind == "para":
                para = obj
                style = para.paragraph_format.style_name
                text = (
                    para.get_text()
                    .replace("\r", "")
                    .replace("\x07", "")
                    .rstrip("\n\r\x0c")
                )
                lines.append(f"[PARA style={style}]")
                lines.append(text)
                lines.append("[/PARA]")
            else:
                lines.append(self._extract_table_markdown(obj))
        return "\n".join(lines), len(blocks)

    def _extract_table_markdown(self, table: Any) -> str:
        aw = self._aw
        # 防御：有时上层可能传入 Node（而非 Table）
        try:
            if hasattr(table, "as_table"):
                t2 = table.as_table()
                if t2 is not None:
                    table = t2
        except Exception:
            pass
        rows_out: List[str] = []
        for row_node in table.rows:
            row = row_node
            try:
                if hasattr(row_node, "as_row"):
                    r2 = row_node.as_row()
                    if r2 is not None:
                        row = r2
            except Exception:
                pass
            cells: List[str] = []
            for cell_node in row.cells:
                cell = cell_node
                try:
                    if hasattr(cell_node, "as_cell"):
                        c2 = cell_node.as_cell()
                        if c2 is not None:
                            cell = c2
                except Exception:
                    pass
                raw = (
                    cell.get_text()
                    .replace("\x07", "")
                    .replace("\r", "")
                    .strip()
                )
                raw = raw.replace("\n", "<br/>")
                cells.append(raw)
            rows_out.append("| " + " | ".join(cells) + " |")
        if not rows_out:
            return "[TABLE]\n[/TABLE]"
        try:
            col_count = len(table.rows[0].cells)
        except Exception:
            # 兜底：用首行输出列数估算
            col_count = max(1, rows_out[0].count("|") - 1)
        sep = "| " + " | ".join(["---"] * col_count) + " |"
        body = [rows_out[0], sep] + rows_out[1:]
        return "[TABLE]\n" + "\n".join(body) + "\n[/TABLE]"

    def block_structure_summary(self, doc: Any) -> str:
        """人类可读的块序号与类型，用于提示模型勿拆块。"""
        blocks = self._iter_body_paragraphs_and_tables(doc)
        parts: List[str] = []
        for i, (k, _) in enumerate(blocks, 1):
            label = "段落[PARA]" if k == "para" else "表格[TABLE]"
            parts.append(f"{i}:{label}")
        return "；".join(parts)

    def apply_structured_edits(self, doc: Any, edited: str) -> None:
        """将模型输出的结构化文本按块顺序写回文档（段落替换文字、表格按格写入）。

        当模型输出块数与文档不一致时，尝试容错对齐：
        - 模型多出 para 块：将相邻的 para 合并回对应位置
        - 模型少 para 块：用原文内容补齐缺失位置
        - 类型不匹配或差距过大仍抛异常
        """
        segments = _parse_structured_response(edited)
        blocks = self._iter_body_paragraphs_and_tables(doc)
        if len(segments) != len(blocks):
            segments = _try_align_segments(segments, blocks)
            if len(segments) != len(blocks):
                raise RuntimeError(
                    f"Aspose 结构化回写：块数量不一致（文档 {len(blocks)}，模型输出 {len(segments)}）。"
                    "必须保留与输入相同数量的 [PARA]/[TABLE] 块，勿拆分、合并或新增块。"
                )
        aw = self._aw
        for idx, ((sk, sdata), (bk, bobj)) in enumerate(zip(segments, blocks), 1):
            if sk != bk:
                raise RuntimeError(
                    f"Aspose 结构化回写：第 {idx} 块类型不一致（期望 {bk}，得到 {sk}），请保持段落/表格顺序与输入一致。"
                )
            if sk == "para":
                body = str(sdata)
                if not _replace_paragraph_with_markdown_table(aw, bobj, body):
                    _set_paragraph_text_keep_doc(aw, bobj, body)
            else:
                _apply_markdown_table_to_aw_table(aw, bobj, sdata)

    def save_document_bytes(self, doc: Any) -> bytes:
        aw = self._aw
        bio = io.BytesIO()
        doc.save(bio, aw.SaveFormat.DOCX)
        return bio.getvalue()


def generate_aspose_aware_prompt(
    structured_content: str,
    user_request: str,
    *,
    expected_blocks: int,
    structure_summary: str,
) -> Tuple[str, str]:
    """生成 Aspose 结构化编辑专用 system / user 消息（强调块数与类型不可变）。"""
    system_prompt = f"""你是 Word 文档编辑专家。收到内容是从 Word 通过 Aspose 抽取的**结构化标记文本**。

格式说明：
- [PARA style=样式名] … [/PARA]：**一个块 = 一对标记**，对应主故事区的一个段落；只改中间正文，勿改样式名行与结束标记。**禁止**把同一段落拆成多个 [PARA]…[/PARA]。
- 若某块内是 **Markdown 管道表**（多行以 `|` 开头，含 `| --- |` 分隔行），**每一表行必须单独一行**，不要压成一行；否则 Word 无法排成表格。
- [TABLE] … [/TABLE]：一个表格 = 一个块。Markdown 管道表（含 | --- | 分隔行），必须保持**列数与行数**与输入一致，勿合并/拆分单元格，勿删表头行。
- 单元格内换行在抽取中为 <br/>，输出时请保留在单元格文本中。

硬性规则（违反将导致无法写回文档）：
1. 输出中的块总数必须**恰好为 {expected_blocks}**，与输入一致；块顺序与类型必须与下述「块结构」一致：{structure_summary}
2. 仅允许在每个块**内部**改字；**不得**增加块、删除块、拆分 [PARA]、合并相邻块。
3. 表格每行必须以 | 开头；列数与第一行一致。
4. 不要输出解释、代码围栏或「以下是修改后」等套话。
5. **图片处理规则**：文档中的图片/图表等元素在抽取文本中通常不可见。**默认不要因为“你看到了图片”而新增任何图片描述、解读或扩写**，只按用户明确要求编辑文字/表格并保持结构不变。只有当用户在编辑要求中明确提出“根据图片内容回答/提取信息/生成图注”等，才允许在对应段落中补充说明（但不得删除图片所在段落/结构）。
6. 直接输出编辑后的**完整**结构化文本。"""

    user_prompt = f"""【编辑要求】
{user_request}

【块结构 — 共 {expected_blocks} 个块；你的输出也必须恰好 {expected_blocks} 个块】
{structure_summary}

【待编辑结构化正文】
{structured_content}

请直接返回编辑后的完整内容（含全部 [PARA]…[/PARA] 与 [TABLE]…[/TABLE]），块数量与顺序与上文一致："""
    return system_prompt, user_prompt


def generate_aspose_retry_prompt(
    structured_content: str,
    user_request: str,
    *,
    expected_blocks: int,
    structure_summary: str,
    previous_segment_count: int,
) -> Tuple[str, str]:
    """块数/类型校验失败后，带纠错说明再调一次大模型。"""
    extra = (
        f"\n\n【纠错】你上次的输出解析为 {previous_segment_count} 个块，本任务要求**恰好 {expected_blocks} 个块**。"
        "常见错误：把若干行正文拆成多个 [PARA]…[/PARA]。请**只**修改各块内部文字，块的数量、顺序、类型（段落/表格）必须与「块结构」一致，禁止新增或拆分块。\n"
    )
    return generate_aspose_aware_prompt(
        structured_content,
        user_request + extra,
        expected_blocks=expected_blocks,
        structure_summary=structure_summary,
    )


def _parse_structured_response(text: str) -> List[Tuple[str, Union[str, List[List[str]]]]]:
    """解析模型输出为 [('para', str) | ('table', rows)] 列表。"""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z0-9]*\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw)
    lines = raw.replace("\r\n", "\n").split("\n")
    segments: List[Tuple[str, Union[str, List[List[str]]]]] = []
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("[PARA"):
            i += 1
            buf: List[str] = []
            while i < len(lines) and lines[i].strip() != "[/PARA]":
                buf.append(lines[i])
                i += 1
            if i >= len(lines) and "[/PARA]" not in text:
                raise RuntimeError("结构化解析：缺少 [/PARA] 结束标记")
            body = "\n".join(buf).replace("\r", "")
            segments.append(("para", body))
            i += 1
            continue
        if s == "[TABLE]":
            i += 1
            buf = []
            while i < len(lines) and lines[i].strip() != "[/TABLE]":
                buf.append(lines[i])
                i += 1
            md = "\n".join(buf)
            segments.append(("table", _markdown_pipe_to_rows(md)))
            i += 1
            continue
        if s and not s.startswith("```"):
            logger.debug("结构化解析跳过非块行: %s", s[:80])
        i += 1
    return segments


def _try_align_segments(
    segments: List[Tuple[str, Union[str, List[List[str]]]]],
    blocks: List[Tuple[str, Any]],
) -> List[Tuple[str, Union[str, List[List[str]]]]]:
    """当模型输出块数与文档不一致时，尝试容错对齐。

    策略 1 — 模型多出 para 块（最常见：把一个段落拆成多个 [PARA]）：
        找到类型序列与文档一致的合并点，将相邻多余 para 合并到前一个 para。
    策略 2 — 模型少 para 块：
        按文档块顺序，在缺失位置插入原文内容作为占位。
    差距过大（>3）或 table 数量不匹配时不做对齐，返回原 segments。
    """
    n_doc = len(blocks)
    n_seg = len(segments)
    diff = n_seg - n_doc

    if abs(diff) == 0 or abs(diff) > 3:
        return segments

    doc_types = [bk for bk, _ in blocks]
    seg_types = [sk for sk, _ in segments]

    # table 数量必须一致，否则无法对齐
    if seg_types.count("table") != doc_types.count("table"):
        return segments

    if diff > 0:
        # 策略 1：模型多出 para 块，尝试合并相邻 para
        aligned = _merge_extra_paras(segments, doc_types)
        if len(aligned) == n_doc:
            logger.info(
                "Aspose 容错对齐：合并多余 para 块（%d → %d）", n_seg, n_doc
            )
            return aligned
    else:
        # 策略 2：模型少 para 块，用原文补齐
        aligned = _fill_missing_paras(segments, blocks)
        if len(aligned) == n_doc:
            logger.info(
                "Aspose 容错对齐：补齐缺失 para 块（%d → %d）", n_seg, n_doc
            )
            return aligned

    return segments


def _merge_extra_paras(
    segments: List[Tuple[str, Union[str, List[List[str]]]]],
    doc_types: List[str],
) -> List[Tuple[str, Union[str, List[List[str]]]]]:
    """将多余的相邻 para 块合并，使块数与文档一致。

    贪心策略：从左到右扫描，当当前位置类型与文档不匹配但下一位置可以匹配时，
    将当前 seg 与下一个 seg（都是 para）合并。
    """
    result: List[Tuple[str, Union[str, List[List[str]]]]] = []
    i = 0  # segments index
    j = 0  # doc_types index
    while i < len(segments) and j < len(doc_types):
        sk, sdata = segments[i]
        expected = doc_types[j]
        if sk == expected:
            result.append(segments[i])
            i += 1
            j += 1
        elif sk == "para" and expected == "para" and i + 1 < len(segments):
            # 当前是 para，文档也期望 para，但后面可能需要合并
            # 检查是否需要与下一个 para 合并
            next_sk = segments[i + 1][0]
            # 合并当前与下一个 para，使后续对齐
            merged_text = str(sdata) + "\n" + str(segments[i + 1][1])
            result.append(("para", merged_text))
            i += 2
            j += 1
        elif sk == "para" and expected == "para":
            result.append(segments[i])
            i += 1
            j += 1
        else:
            # 无法对齐，放弃
            return segments

    # 剩余 segments 尝试合并到最后一个 para
    if i < len(segments) and result and result[-1][0] == "para":
        last_key, last_val = result[-1]
        remaining = "\n".join(str(s[1]) for s in segments[i:] if s[0] == "para")
        if remaining:
            result[-1] = ("para", str(last_val) + "\n" + remaining)
        i = len(segments)

    if i != len(segments) or j != len(doc_types):
        return segments

    return result


def _fill_missing_paras(
    segments: List[Tuple[str, Union[str, List[List[str]]]]],
    blocks: List[Tuple[str, Any]],
) -> List[Tuple[str, Union[str, List[List[str]]]]]:
    """当模型少输出 para 块时，用文档原文内容补齐缺失位置。"""
    result: List[Tuple[str, Union[str, List[List[str]]]]] = []
    si = 0  # segments index
    bi = 0  # blocks index
    while bi < len(blocks) and si < len(segments):
        bk, bobj = blocks[bi]
        sk, sdata = segments[si]
        if sk == bk:
            result.append(segments[si])
            si += 1
            bi += 1
        elif bk == "para" and sk != "para":
            # 文档期望 para 但模型给了其他类型，用原文填充
            aw = _try_import_aw()
            orig_text = (
                bobj.get_text()
                .replace("\r", "")
                .replace("\x07", "")
                .strip()
            )
            result.append(("para", orig_text))
            bi += 1
        else:
            # 无法对齐
            return segments

    # 补齐尾部缺失的 para 块
    while bi < len(blocks):
        bk, bobj = blocks[bi]
        if bk == "para":
            orig_text = (
                bobj.get_text()
                .replace("\r", "")
                .replace("\x07", "")
                .strip()
            )
            result.append(("para", orig_text))
        else:
            return segments  # 缺 table 无法补齐
        bi += 1

    return result


def _normalize_para_text(t: str) -> str:
    return (t or "").replace("\r", "").strip()


def _segments_equivalent(
    a: List[Tuple[str, Union[str, List[List[str]]]]],
    b: List[Tuple[str, Union[str, List[List[str]]]]],
) -> bool:
    if len(a) != len(b):
        return False
    for (ak, av), (bk, bv) in zip(a, b):
        if ak != bk:
            return False
        if ak == "para":
            if _normalize_para_text(str(av)) != _normalize_para_text(str(bv)):
                return False
        else:
            if _normalize_table_rows(av) != _normalize_table_rows(bv):  # type: ignore[arg-type]
                return False
    return True


def _segments_to_plain_text(segments: List[Tuple[str, Union[str, List[List[str]]]]]) -> str:
    parts: List[str] = []
    for k, v in segments:
        if k == "para":
            t = (str(v) or "").strip()
            if t:
                parts.append(t)
        else:
            rows: List[List[str]] = v  # type: ignore[assignment]
            for r in rows:
                line = " | ".join((c or "").strip() for c in r).strip()
                if line:
                    parts.append(line)
    return "\n".join(parts).strip()


def _extract_question_lines(text: str) -> List[str]:
    out: List[str] = []
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.endswith("？") or s.endswith("?"):
            out.append(s)
    return out


def _looks_incomplete_after_fill(original_text: str, filled_text: str) -> bool:
    """
    判断“是否仍像未补全”：
    - 原文存在较多问句（>=3）
    - 改写后仍保留大多数原问句
    - 且正文增长很少（仅小幅改动）
    """
    q_lines = _extract_question_lines(original_text)
    if len(q_lines) < 3:
        return False
    remained = sum(1 for q in q_lines if q in (filled_text or ""))
    ratio = remained / max(1, len(q_lines))
    growth = len((filled_text or "").strip()) - len((original_text or "").strip())
    return ratio >= 0.6 and growth < 120


def _markdown_pipe_to_rows(md: str) -> List[List[str]]:
    rows: List[List[str]] = []
    for ln in md.split("\n"):
        t = ln.strip()
        if not t or not t.startswith("|"):
            continue
        if re.match(r"^\|\s*[-:]+\s*(\|\s*[-:]+\s*)+\|?\s*$", t):
            continue
        parts = [p.strip() for p in t.strip("|").split("|")]
        rows.append(parts)
    return rows


_SEP_ROW_RE = re.compile(
    r"^\|\s*[-: ]+\s*(\|\s*[-: ]+\s*)+\|?\s*$"
)


def _expand_single_line_pipe_table(text: str) -> str:
    """
    模型或粘贴常把整张 Markdown 表压成一行。在「分隔行」前后及数据区拆成多行，便于解析。
    """
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if "\n" in t or "|" not in t:
        return t
    m = re.search(r"(\|\s*[-:]+\s*(?:\|\s*[-:]+\s*)+\|?\s*)", t)
    if not m:
        return t
    head = t[: m.start()].strip()
    sep = m.group(0).strip()
    tail = t[m.end() :].strip()
    lines = [head, sep] if head else [sep]
    if tail:
        # 每行形如 | a | b | c |（至少两竖线）
        for row in re.finditer(r"\|\s*(?:[^|\n]+\|)+\s*", tail):
            r = row.group(0).strip()
            if r:
                lines.append(r)
    return "\n".join(lines)


def _looks_like_markdown_pipe_table(text: str) -> bool:
    """段落内是否为多行 Markdown 管道表（模型把表写在 [PARA] 里时常出现）。"""
    t = _expand_single_line_pipe_table((text or "").strip())
    if not t:
        return False
    lines = [ln.strip() for ln in t.replace("\r", "\n").split("\n") if ln.strip()]
    if len(lines) < 2:
        return False
    pipe_rows = [ln for ln in lines if ln.startswith("|") and ln.count("|") >= 2]
    if len(pipe_rows) < 2:
        return False
    has_sep = any(_SEP_ROW_RE.match(ln) for ln in lines)
    # 有 |---| 分隔行最可靠；否则至少 3 行管道行（表头+多行数据），避免两行误识别
    return bool(has_sep or len(pipe_rows) >= 3)


def _normalize_table_rows(rows: List[List[str]]) -> List[List[str]]:
    if not rows:
        return rows
    ncol = max(len(r) for r in rows)
    out: List[List[str]] = []
    for r in rows:
        rr = list(r) + [""] * (ncol - len(r))
        out.append(rr[:ncol])
    return out


def _replace_paragraph_with_markdown_table(aw: Any, para: Any, md_text: str) -> bool:
    """
    将「整段管道表 Markdown」转为 Word 表格对象，避免单段落内 | 换行混乱。
    成功则移除原段落并插入表格，返回 True。
    """
    md_text = _expand_single_line_pipe_table(md_text.strip())
    if not _looks_like_markdown_pipe_table(md_text):
        return False
    rows = _markdown_pipe_to_rows(md_text)
    rows = _normalize_table_rows(rows)
    if len(rows) < 2:
        return False
    doc = para.document
    builder = aw.DocumentBuilder(doc)
    try:
        builder.move_to(para)
        builder.start_table()
        for row in rows:
            for cell in row:
                builder.insert_cell()
                builder.write((cell or "").replace("<br/>", "\n"))
            builder.end_row()
        builder.end_table()
        para.remove()
        return True
    except Exception as e:
        logger.warning("段落内 Markdown 管道表转为 Word 表格失败，将回退为纯文本：%s", e)
        return False


def _set_paragraph_text_keep_doc(aw: Any, para: Any, new_text: str) -> None:
    """仅替换段落内文字，尽量不动段落格式与图片等非文本节点。"""
    doc = para.document
    new_text = (new_text or "").replace("<br/>", "\n")

    def _run_has_drawing(run: Any) -> bool:
        """Run 内含图片/绘图时不可删除该 Run。"""
        try:
            s1 = run.get_child_nodes(aw.NodeType.SHAPE, True)
            if s1 is not None and getattr(s1, "count", 0) > 0:
                return True
        except Exception:
            pass
        try:
            s2 = run.get_child_nodes(aw.NodeType.DRAWING_ML, True)
            if s2 is not None and getattr(s2, "count", 0) > 0:
                return True
        except Exception:
            pass
        return False

    # 仅处理纯文本 run，保留包含图片/绘图的 run，避免图片被删
    text_runs: List[Any] = []
    try:
        runs = para.runs
        for i in range(runs.count):
            r = runs[i]
            if not _run_has_drawing(r):
                text_runs.append(r)
    except Exception:
        text_runs = []

    if not text_runs:
        # 没有可写文本 run（常见于“仅图片段落”），只在需要文字时追加新 run
        if new_text:
            para.append_child(aw.Run(doc, new_text))
        return

    # 写入首个文本 run，清空其余文本 run（不动图片 run）
    text_runs[0].text = new_text
    for r in text_runs[1:]:
        r.text = ""


def _apply_markdown_table_to_aw_table(aw: Any, table: Any, rows: List[List[str]]) -> None:
    if not rows:
        return
    # 防御：确保 table 是 Table
    try:
        if hasattr(table, "as_table"):
            t2 = table.as_table()
            if t2 is not None:
                table = t2
    except Exception:
        pass
    nrows = table.rows.count
    for ri, row_data in enumerate(rows):
        if ri >= nrows:
            logger.warning("Aspose 表格回写：模型行数多于原表，忽略多余行")
            break
        row_node = table.rows[ri]
        row = row_node
        try:
            if hasattr(row_node, "as_row"):
                r2 = row_node.as_row()
                if r2 is not None:
                    row = r2
        except Exception:
            pass
        # 兼容：某些情况下 row 仍是 Node
        if not hasattr(row, "cells"):
            logger.warning("Aspose 表格回写：行节点无 cells，跳过该行")
            continue
        ncells = row.cells.count
        for ci, cell_text in enumerate(row_data):
            if ci >= ncells:
                break
            cell_node = row.cells[ci]
            cell = cell_node
            try:
                if hasattr(cell_node, "as_cell"):
                    c2 = cell_node.as_cell()
                    if c2 is not None:
                        cell = c2
            except Exception:
                pass
            txt = (cell_text or "").replace("<br/>", "\n")
            pc = cell.paragraphs.count
            for pi in range(pc):
                p = cell.paragraphs[pi]
                if pi == 0:
                    _set_paragraph_text_keep_doc(aw, p, txt)
                else:
                    _set_paragraph_text_keep_doc(aw, p, "")


def run_aspose_structured_fill(
    docx_bytes: bytes,
    user_request: str,
    client: Any,
    *,
    model: str,
    max_tokens: Optional[int] = None,
    temperature: float = 0.25,
) -> bytes:
    """
    执行完整流程：抽取 → 大模型 → 回写 → 返回 .docx 字节。
    client: OpenAI 兼容客户端（含 chat.completions.create）。
    """
    ensure_aspose_installed()
    proc = AsposeDocxProcessor()
    doc = proc.load_document_bytes(docx_bytes)
    structured, n_blocks = proc.extract_structured_text(doc)
    if n_blocks == 0:
        raise RuntimeError("文档主故事区无可用块（段落/表）")
    original_segments = _parse_structured_response(structured)
    structure_summary = proc.block_structure_summary(doc)
    sys_msg, user_msg = generate_aspose_aware_prompt(
        structured,
        user_request,
        expected_blocks=n_blocks,
        structure_summary=structure_summary,
    )
    mt = max_tokens or int(os.getenv("AI_FILE_FILL_MAX_TOKENS", "8192"))
    from utils.ai_text_cleaner import (  # noqa: PLC0415
        EMPTY_CHAT_COMPLETION_USER_MESSAGE,
        _extract_chat_completion_text,
    )

    def chat_once(s: str, u: str) -> str:
        out = ""
        for attempt in range(2):
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": s},
                    {"role": "user", "content": u},
                ],
                temperature=temperature,
                max_tokens=mt,
            )
            out = _extract_chat_completion_text(response)
            if (out or "").strip():
                break
            if attempt == 0:
                logger.warning("Aspose structured fill：大模型返回空正文，重试一次")
        return out

    ai_out = chat_once(sys_msg, user_msg)
    if not (ai_out or "").strip():
        raise RuntimeError(EMPTY_CHAT_COMPLETION_USER_MESSAGE)

    # 若模型原样返回，追加强约束再请求一次，避免“改写后仍是原文”
    try:
        ai_segments = _parse_structured_response(ai_out)
        if _segments_equivalent(original_segments, ai_segments):
            logger.warning("Aspose structured fill：模型输出与原文一致，触发强约束重试")
            sys_retry = (
                sys_msg
                + "\n\n【额外硬约束】本次任务必须根据用户要求产生可见修改："
                "不得原样返回输入内容；若用户要求不明确，请在不改变结构前提下做最小可见改写。"
            )
            user_retry = user_msg + "\n\n【强制要求】输出结果必须与输入至少有一处可见文本差异。"
            ai_out_retry = chat_once(sys_retry, user_retry)
            if not (ai_out_retry or "").strip():
                raise RuntimeError(EMPTY_CHAT_COMPLETION_USER_MESSAGE)
            ai_segments_retry = _parse_structured_response(ai_out_retry)
            if _segments_equivalent(original_segments, ai_segments_retry):
                raise RuntimeError("未检测到文档内容变化，请提供更明确的改写要求后重试。")
            ai_out = ai_out_retry
    except RuntimeError:
        raise
    except Exception as e:
        logger.warning("Aspose structured fill：改写有效性校验失败，继续按当前输出回写：%s", e)

    # 完整性兜底：针对“问句列表未被逐条补全”场景再做一次强约束重写
    try:
        ai_segments_now = _parse_structured_response(ai_out)
        original_text = _segments_to_plain_text(original_segments)
        filled_text = _segments_to_plain_text(ai_segments_now)
        if _looks_incomplete_after_fill(original_text, filled_text):
            logger.warning("Aspose structured fill：检测到改写不完整，触发逐条补全重试")
            sys_complete = (
                sys_msg
                + "\n\n【补全质量硬约束】若原文中存在多条问句，请逐条给出完整答案；"
                "禁止仅保留问题或只回答其中一两条。"
            )
            user_complete = (
                user_msg
                + "\n\n【强制要求】请确保原文中的每个问题都被回答，输出应形成完整可交付文档。"
            )
            ai_out_complete = chat_once(sys_complete, user_complete)
            if not (ai_out_complete or "").strip():
                raise RuntimeError(EMPTY_CHAT_COMPLETION_USER_MESSAGE)
            ai_segments_complete = _parse_structured_response(ai_out_complete)
            filled_text_complete = _segments_to_plain_text(ai_segments_complete)
            if _looks_incomplete_after_fill(original_text, filled_text_complete):
                raise RuntimeError("文档改写结果仍不完整，请细化要求（例如：逐条回答每个问题并扩展为段落）后重试。")
            ai_out = ai_out_complete
    except RuntimeError:
        raise
    except Exception as e:
        logger.warning("Aspose structured fill：完整性校验失败，继续按当前输出回写：%s", e)

    for repair in range(2):
        try:
            proc.apply_structured_edits(doc, ai_out)
            raw_docx = proc.save_document_bytes(doc)
            from utils.aspose_watermark_remover import (  # noqa: PLC0415
                remove_evaluation_watermark_bytes,
            )

            return remove_evaluation_watermark_bytes(raw_docx)
        except RuntimeError as e:
            err = str(e)
            if (
                repair == 0
                and ("块数量不一致" in err or "块类型不一致" in err)
            ):
                logger.warning("%s，带纠错提示重新请求大模型一次", err)
                try:
                    prev_n = len(_parse_structured_response(ai_out))
                except Exception:
                    prev_n = -1
                sys_msg, user_msg = generate_aspose_retry_prompt(
                    structured,
                    user_request,
                    expected_blocks=n_blocks,
                    structure_summary=structure_summary,
                    previous_segment_count=prev_n,
                )
                ai_out = chat_once(sys_msg, user_msg)
                if not (ai_out or "").strip():
                    raise RuntimeError(EMPTY_CHAT_COMPLETION_USER_MESSAGE) from e
                continue
            raise
