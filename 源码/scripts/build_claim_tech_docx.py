from __future__ import annotations

import argparse
import re
import shutil
import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn, nsdecls
from docx.shared import Cm, Pt, RGBColor
from lxml import etree


BODY_FONT = "宋体"
HEADING_FONT = "黑体"
LATIN_FONT = "Times New Roman"


def set_cjk_font(run, font_name: str, size_pt: float | None = None, bold: bool | None = None):
    run.font.name = font_name
    r_pr = run._r.get_or_add_rPr()
    r_fonts = r_pr.find(qn("w:rFonts"))
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.insert(0, r_fonts)
    r_fonts.set(qn("w:eastAsia"), font_name)
    r_fonts.set(qn("w:ascii"), LATIN_FONT)
    r_fonts.set(qn("w:hAnsi"), LATIN_FONT)
    if size_pt is not None:
        run.font.size = Pt(size_pt)
    if bold is not None:
        run.font.bold = bold


def set_para_spacing(p, line_spacing=1.5, first_line_indent_pt: float | None = None, before=0, after=0):
    pf = p.paragraph_format
    pf.line_spacing = line_spacing
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    if first_line_indent_pt is not None:
        pf.first_line_indent = Pt(first_line_indent_pt)


def set_page(section, a4=True):
    if a4:
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
    for attr in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
        setattr(section, attr, Cm(2.54))
    section.header_distance = Cm(1.25)
    section.footer_distance = Cm(1.25)


def clear_header_footer_part(part):
    part.is_linked_to_previous = False
    for p in part.paragraphs:
        p.clear()


def clear_all_headers_footers(section):
    clear_header_footer_part(section.header)
    clear_header_footer_part(section.footer)
    clear_header_footer_part(section.first_page_header)
    clear_header_footer_part(section.first_page_footer)
    clear_header_footer_part(section.even_page_header)
    clear_header_footer_part(section.even_page_footer)


def clear_document_body(doc):
    body = doc._body._element
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def add_cover_page(doc):
    section = doc.sections[0]
    set_page(section)
    section.different_first_page_header_footer = True
    clear_all_headers_footers(section)

    for _ in range(5):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_para_spacing(p, first_line_indent_pt=0)

    for line in ("2026年上半年中国科学技术信息研究所", "大模型调度服务建设"):
        p = doc.add_paragraph(style="Codex Cover Title" if "Codex Cover Title" in doc.styles else None)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_para_spacing(p, line_spacing=1.5, first_line_indent_pt=0, before=5, after=5)
        r = p.add_run(line)
        set_cjk_font(r, BODY_FONT, 18, False)

    for _ in range(4):
        p = doc.add_paragraph()
        set_para_spacing(p, first_line_indent_pt=0)

    p = doc.add_paragraph(style="封页副标题" if "封页副标题" in doc.styles else None)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_para_spacing(p, line_spacing=1.5, first_line_indent_pt=0)
    r = p.add_run("一致性评估智能体技术方案")
    set_cjk_font(r, HEADING_FONT, 36, True)

    for _ in range(4):
        p = doc.add_paragraph()
        set_para_spacing(p, first_line_indent_pt=0)

    p = doc.add_paragraph(style="修订记录标题" if "修订记录标题" in doc.styles else None)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_para_spacing(p, line_spacing=1.5, first_line_indent_pt=0)
    r = p.add_run("北京九瑞网络科技有限公司")
    set_cjk_font(r, BODY_FONT, 14, False)

    for _ in range(2):
        p = doc.add_paragraph()
        set_para_spacing(p, first_line_indent_pt=0)

    today = date.today()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_para_spacing(p, line_spacing=1.5, first_line_indent_pt=0)
    r = p.add_run(f"{today.year}年{today.month}月")
    set_cjk_font(r, BODY_FONT, 14, False)

    doc.add_section(WD_SECTION_START.NEW_PAGE)


def add_toc_page(doc):
    section = doc.sections[-1]
    set_page(section)
    section.different_first_page_header_footer = False
    clear_all_headers_footers(section)

    for _ in range(3):
        p = doc.add_paragraph()
        set_para_spacing(p, first_line_indent_pt=0)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_para_spacing(p, line_spacing=2.0, first_line_indent_pt=0, before=0, after=12)
    r = p.add_run("目  录")
    set_cjk_font(r, HEADING_FONT, 18, True)

    p = doc.add_paragraph()
    set_para_spacing(p, line_spacing=1.5, first_line_indent_pt=0)
    run = p.add_run()
    run._r.append(parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="begin"/>'))
    run = p.add_run()
    run._r.append(parse_xml(f'<w:instrText {nsdecls("w")} xml:space="preserve"> TOC \\o "1-3" \\h \\z \\u </w:instrText>'))
    run = p.add_run()
    run._r.append(parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="separate"/>'))
    r = p.add_run('（请在Word中打开后，右键此处选择"更新域"以生成目录）')
    set_cjk_font(r, BODY_FONT, 10.5, False)
    r.font.color.rgb = RGBColor(150, 150, 150)
    run = p.add_run()
    run._r.append(parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="end"/>'))

    doc.add_section(WD_SECTION_START.NEW_PAGE)


def add_page_field(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pre = paragraph.add_run("— ")
    set_cjk_font(pre, BODY_FONT, 9, False)
    r = paragraph.add_run()
    r._r.append(parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="begin"/>'))
    r = paragraph.add_run()
    r._r.append(parse_xml(f'<w:instrText {nsdecls("w")} xml:space="preserve"> PAGE </w:instrText>'))
    r = paragraph.add_run()
    r._r.append(parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="separate"/>'))
    num = paragraph.add_run("1")
    set_cjk_font(num, BODY_FONT, 9, False)
    r = paragraph.add_run()
    r._r.append(parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="end"/>'))
    post = paragraph.add_run(" —")
    set_cjk_font(post, BODY_FONT, 9, False)


def configure_content_section(doc):
    section = doc.sections[-1]
    set_page(section)
    section.different_first_page_header_footer = False
    clear_all_headers_footers(section)

    hp = section.header.paragraphs[0]
    hp.clear()
    hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    hr = hp.add_run("一致性评估智能体技术方案")
    set_cjk_font(hr, BODY_FONT, 9, False)
    p_pr = hp._p.get_or_add_pPr()
    p_pr.append(parse_xml(
        f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="4" w:space="4" w:color="000000"/></w:pBdr>'
    ))

    fp = section.footer.paragraphs[0]
    fp.clear()
    add_page_field(fp)


def clean_inline(text: str) -> str:
    text = re.sub(r"!\[(.*?)\]\((.*?)\)", r"\1", text)
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"__(.*?)__", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    return text.strip()


def add_heading(doc, text: str, level: int):
    level = min(max(level, 1), 3)
    p = doc.add_paragraph(style=f"Heading {level}")
    set_para_spacing(p, line_spacing=2.0, first_line_indent_pt=0, before=12, after=12)
    r = p.add_run(text)
    size = {1: 16, 2: 14, 3: 12}.get(level, 12)
    set_cjk_font(r, HEADING_FONT, size, True)
    p_pr = p._p.get_or_add_pPr()
    outline = p_pr.find(qn("w:outlineLvl"))
    if outline is None:
        outline = OxmlElement("w:outlineLvl")
        p_pr.append(outline)
    outline.set(qn("w:val"), str(level - 1))


def add_inline_runs(p, text: str, size=12):
    pattern = r"(\*\*.*?\*\*|__.*?__|`[^`]+`|\[.*?\]\(.*?\))"
    for token in re.split(pattern, text):
        if not token:
            continue
        if token.startswith("**") and token.endswith("**"):
            r = p.add_run(token[2:-2])
            set_cjk_font(r, BODY_FONT, size, True)
        elif token.startswith("__") and token.endswith("__"):
            r = p.add_run(token[2:-2])
            set_cjk_font(r, BODY_FONT, size, True)
        elif token.startswith("`") and token.endswith("`"):
            r = p.add_run(token[1:-1])
            r.font.name = "Consolas"
            r.font.size = Pt(10)
        else:
            m = re.match(r"\[(.*?)\]\((.*?)\)$", token)
            r = p.add_run(m.group(1) if m else token)
            set_cjk_font(r, BODY_FONT, size, False)


def add_paragraph(doc, text: str, *, first_indent=True, list_item=False):
    p = doc.add_paragraph()
    if list_item:
        set_para_spacing(p, line_spacing=1.5, first_line_indent_pt=0, before=0, after=0)
        p.paragraph_format.left_indent = Cm(0.75)
    else:
        set_para_spacing(p, line_spacing=1.5, first_line_indent_pt=24 if first_indent else 0, before=0, after=0)
    add_inline_runs(p, text)


def add_code_block(doc, lines: list[str]):
    p = doc.add_paragraph()
    set_para_spacing(p, line_spacing=1.0, first_line_indent_pt=0, before=6, after=6)
    p_pr = p._p.get_or_add_pPr()
    p_pr.append(parse_xml(f'<w:shd {nsdecls("w")} w:fill="F5F5F5" w:val="clear"/>'))
    p_pr.append(parse_xml(
        f'<w:pBdr {nsdecls("w")}><w:top w:val="single" w:sz="4" w:space="4" w:color="D0D0D0"/>'
        f'<w:left w:val="single" w:sz="4" w:space="4" w:color="D0D0D0"/>'
        f'<w:bottom w:val="single" w:sz="4" w:space="4" w:color="D0D0D0"/>'
        f'<w:right w:val="single" w:sz="4" w:space="4" w:color="D0D0D0"/></w:pBdr>'
    ))
    r = p.add_run("\n".join(lines))
    r.font.name = "Consolas"
    r.font.size = Pt(9)


def add_table(doc, rows: list[str]):
    parsed: list[list[str]] = []
    for row in rows:
        cells = [clean_inline(c) for c in row.strip().strip("|").split("|")]
        parsed.append(cells)
    if not parsed:
        return
    col_count = max(len(row) for row in parsed)
    parsed = [row + [""] * (col_count - len(row)) for row in parsed]

    doc.add_paragraph()
    table = doc.add_table(rows=len(parsed), cols=col_count)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    tbl_pr = table._tbl.tblPr
    tbl_pr.append(parse_xml(f'<w:tblW {nsdecls("w")} w:w="5000" w:type="pct"/>'))

    for ri, row in enumerate(parsed):
        for ci, cell_text in enumerate(row):
            cell = table.cell(ri, ci)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            cell.text = ""
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if ri == 0 else WD_ALIGN_PARAGRAPH.LEFT
            set_para_spacing(p, line_spacing=1.15, first_line_indent_pt=0, before=2, after=2)
            r = p.add_run(cell_text)
            set_cjk_font(r, HEADING_FONT if ri == 0 else BODY_FONT, 10.5, ri == 0)
            if ri == 0:
                cell._tc.get_or_add_tcPr().append(parse_xml(f'<w:shd {nsdecls("w")} w:fill="D9E2F3" w:val="clear"/>'))
    doc.add_paragraph()


def parse_markdown(doc, md_path: Path):
    lines = md_path.read_text(encoding="utf-8").splitlines()
    in_code = False
    code_lines: list[str] = []
    table_rows: list[str] = []
    skip_initial_h1 = True

    for raw in lines:
        line = raw.rstrip()

        if line.strip().startswith("```"):
            fence = line.strip()
            if not in_code:
                in_code = True
                code_lines = []
                code_lang = fence[3:].strip().lower()
            else:
                if code_lines:
                    add_code_block(doc, code_lines)
                in_code = False
                code_lines = []
            continue

        if in_code:
            code_lines.append(line)
            continue

        is_table = line.strip().startswith("|") and "|" in line.strip()[1:]
        is_sep = bool(re.match(r"^\|[\s:|\-]+\|$", line.strip()))
        if is_table and not is_sep:
            table_rows.append(line)
            continue
        if is_sep and table_rows:
            continue
        if table_rows:
            add_table(doc, table_rows)
            table_rows = []

        if not line.strip():
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            level = len(heading.group(1))
            text = clean_inline(heading.group(2))
            if level == 1 and skip_initial_h1:
                skip_initial_h1 = False
                continue
            add_heading(doc, text, max(1, level - 1))
            continue

        skip_initial_h1 = False

        if line.strip() in ("---", "***", "___"):
            doc.add_paragraph()
            continue

        if line.strip().startswith(">"):
            add_paragraph(doc, clean_inline(line.strip()[1:].strip()), first_indent=False)
            continue

        list_match = re.match(r"^\s*((?:[-*+])|\d+\.)\s+(.+)$", line)
        if list_match:
            add_paragraph(doc, f"{list_match.group(1)} {list_match.group(2)}", list_item=True)
            continue

        add_paragraph(doc, line)

    if table_rows:
        add_table(doc, table_rows)
    if in_code and code_lines:
        add_code_block(doc, code_lines)


def set_update_fields_on_open(docx_path: Path):
    tmp = Path(tempfile.mkdtemp(prefix="claim_docx_patch_"))
    try:
        with zipfile.ZipFile(docx_path, "r") as z:
            z.extractall(tmp)
        settings = tmp / "word" / "settings.xml"
        parser = etree.XMLParser(remove_blank_text=False)
        tree = etree.parse(str(settings), parser)
        root = tree.getroot()
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        uf = root.find("w:updateFields", namespaces=ns)
        if uf is None:
            uf = etree.Element(f"{{{ns['w']}}}updateFields")
            root.insert(0, uf)
        uf.set(f"{{{ns['w']}}}val", "true")
        tree.write(str(settings), xml_declaration=True, encoding="UTF-8", standalone="yes")
        with zipfile.ZipFile(docx_path, "w", zipfile.ZIP_DEFLATED) as z:
            for p in tmp.rglob("*"):
                if p.is_file():
                    z.write(p, p.relative_to(tmp).as_posix())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build(reference: Path, markdown: Path, output: Path):
    if output.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(output, output.with_suffix(output.suffix + f".bak_{stamp}"))

    doc = Document(str(reference))
    clear_document_body(doc)
    add_cover_page(doc)
    add_toc_page(doc)
    configure_content_section(doc)
    parse_markdown(doc, markdown)

    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output))
    set_update_fields_on_open(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--markdown", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    build(args.reference, args.markdown, args.output)


if __name__ == "__main__":
    main()
