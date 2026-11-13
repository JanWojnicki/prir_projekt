#!/usr/bin/env python3
"""Convert PRZEWODNIK_PO_PROJEKCIE.md into a richly styled DOCX and export to PDF."""
import re
from pathlib import Path
from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt, RGBColor


NAVY = RGBColor(20, 48, 92)
ACCENT = RGBColor(36, 92, 160)
DARK = RGBColor(32, 35, 42)
MUTED = RGBColor(95, 102, 114)
CODE_COLOR = RGBColor(145, 35, 65)
HEADER_BG = "1B365D"
STRIPE_BG = "F3F6FA"
CALLOUT_BG = "EEF4FB"
CALLOUT_BORDER = "2B6CB0"
BORDER_COLOR = "B8C4D4"
CODE_BG = "F4F5F7"


def set_cell_shading(cell, color_hex):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>')
    tcPr.append(shd)


def set_cell_margins(cell, top=90, bottom=90, left=130, right=130):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for name, val in (('top', top), ('bottom', bottom), ('left', left), ('right', right)):
        node = OxmlElement(f'w:{name}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)


def set_table_borders(table, color=BORDER_COLOR):
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'<w:top w:val="single" w:sz="6" w:space="0" w:color="{color}"/>'
        f'<w:bottom w:val="single" w:sz="8" w:space="0" w:color="{HEADER_BG}"/>'
        f'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="{color}"/>'
        f'<w:insideV w:val="single" w:sz="4" w:space="0" w:color="{color}"/>'
        f'<w:left w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)


def set_callout_borders(table):
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'<w:top w:val="single" w:sz="4" w:space="0" w:color="D0DFEE"/>'
        f'<w:bottom w:val="single" w:sz="4" w:space="0" w:color="D0DFEE"/>'
        f'<w:left w:val="single" w:sz="24" w:space="0" w:color="{CALLOUT_BORDER}"/>'
        f'<w:right w:val="single" w:sz="4" w:space="0" w:color="D0DFEE"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)


def add_page_number_fields(run_page, run_total):
    for run, field in ((run_page, "PAGE"), (run_total, "NUMPAGES")):
        fldChar1 = parse_xml(r'<w:fldChar %s w:fldCharType="begin"/>' % nsdecls('w'))
        instrText = parse_xml(r'<w:instrText %s xml:space="preserve"> %s </w:instrText>' % (nsdecls('w'), field))
        fldChar2 = parse_xml(r'<w:fldChar %s w:fldCharType="separate"/>' % nsdecls('w'))
        fldChar3 = parse_xml(r'<w:fldChar %s w:fldCharType="end"/>' % nsdecls('w'))
        run._r.extend([fldChar1, instrText, fldChar2, fldChar3])


def clean_latex_inline(text: str) -> str:
    replacements = {
        r'\rightarrow': '→',
        r'\Delta': 'Δ',
        r'\varepsilon': 'ε',
        r'\ge': '≥',
        r'\le': '≤',
        r'\times': '×',
        r'\log_2': 'log₂',
        r'p_i': 'pᵢ',
        r'c_i': 'cᵢ',
        r'10^{-9}': '10⁻⁹',
        r'10^{-15}': '10⁻¹⁵',
        r'2^8': '2⁸',
        r'{,}': ',',
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    text = re.sub(r'\$([^$]+)\$', lambda m: m.group(1), text)
    return text


def add_formatted_runs(paragraph, text: str, base_italic: bool = False, font_size: int = 11):
    """Parse **bold**, *italic*, and `code` inline segments and append runs."""
    text = clean_latex_inline(text)
    pattern = re.compile(r'(\*\*.*?\*\*|\*[^*]+?\*|`[^`]+?`)')
    pos = 0
    for match in pattern.finditer(text):
        if match.start() > pos:
            plain = text[pos:match.start()]
            r = paragraph.add_run(plain)
            r.font.size = Pt(font_size)
            if base_italic:
                r.italic = True
        token = match.group(0)
        if token.startswith('**') and token.endswith('**'):
            inner = token[2:-2]
            # Check if inner has backticks
            sub_parts = re.split(r'(`[^`]+?`)', inner)
            for sp in sub_parts:
                if not sp:
                    continue
                if sp.startswith('`') and sp.endswith('`'):
                    r = paragraph.add_run(sp[1:-1])
                    r.bold = True
                    r.font.name = 'Consolas'
                    r.font.size = Pt(font_size - 0.5)
                    r.font.color.rgb = CODE_COLOR
                else:
                    r = paragraph.add_run(sp)
                    r.bold = True
                    r.font.size = Pt(font_size)
                    if base_italic:
                        r.italic = True
        elif token.startswith('*') and token.endswith('*'):
            r = paragraph.add_run(token[1:-1])
            r.italic = True
            r.font.size = Pt(font_size)
        elif token.startswith('`') and token.endswith('`'):
            r = paragraph.add_run(token[1:-1])
            r.font.name = 'Consolas'
            r.font.size = Pt(font_size - 0.5)
            r.font.color.rgb = CODE_COLOR
            if base_italic:
                r.italic = True
        pos = match.end()
    if pos < len(text):
        r = paragraph.add_run(text[pos:])
        r.font.size = Pt(font_size)
        if base_italic:
            r.italic = True


def add_callout_box(doc, lines):
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_callout_borders(t)
    cell = t.cell(0, 0)
    set_cell_shading(cell, CALLOUT_BG)
    set_cell_margins(cell, top=110, bottom=110, left=180, right=160)
    first = True
    for line in lines:
        if not line.strip():
            continue
        p = cell.paragraphs[0] if first else cell.add_paragraph()
        first = False
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.line_spacing = 1.15
        if line.strip().startswith('* '):
            p.paragraph_format.left_indent = Cm(0.4)
            r_bul = p.add_run("• ")
            r_bul.bold = True
            r_bul.font.color.rgb = ACCENT
            add_formatted_runs(p, line.strip()[2:], font_size=10.5)
        else:
            add_formatted_runs(p, line.strip(), font_size=10.5)
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(4)


def add_code_block(doc, code_lines):
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t, color="CBD5E1")
    cell = t.cell(0, 0)
    set_cell_shading(cell, CODE_BG)
    set_cell_margins(cell, top=90, bottom=90, left=140, right=140)
    p = cell.paragraphs[0]
    p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.08
    r = p.add_run("\n".join(code_lines))
    r.font.name = "Consolas"
    r.font.size = Pt(9)
    r.font.color.rgb = DARK
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(4)


def add_md_table(doc, table_lines):
    rows_data = []
    for line in table_lines:
        stripped = line.strip().strip('|')
        cells = [c.strip() for c in stripped.split('|')]
        # Skip separator row like :--- | :---:
        if all(re.match(r'^:?-+:?$', c) for c in cells):
            continue
        rows_data.append(cells)
    if len(rows_data) < 2:
        return
    headers = rows_data[0]
    body = rows_data[1:]
    t = doc.add_table(rows=1 + len(body), cols=len(headers))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = True
    set_table_borders(t)

    hdr_cells = t.rows[0].cells
    for idx, h_text in enumerate(headers):
        cell = hdr_cells[idx]
        set_cell_shading(cell, HEADER_BG)
        set_cell_margins(cell, top=90, bottom=90, left=100, right=100)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(clean_latex_inline(h_text.replace('**', '')))
        r.bold = True
        r.font.size = Pt(9.5)
        r.font.color.rgb = RGBColor(255, 255, 255)

    for r_idx, row_vals in enumerate(body):
        row_cells = t.rows[r_idx + 1].cells
        bg = STRIPE_BG if r_idx % 2 == 1 else "FFFFFF"
        for c_idx, val in enumerate(row_vals):
            if c_idx >= len(row_cells):
                break
            cell = row_cells[c_idx]
            set_cell_shading(cell, bg)
            set_cell_margins(cell, top=75, bottom=75, left=100, right=100)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if c_idx in (1, 2) else WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            add_formatted_runs(p, val, font_size=9.5)

    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(6)


def build_guide():
    root = Path(__file__).resolve().parent.parent
    md_path = root / "PRZEWODNIK_PO_PROJEKCIE.md"
    out_docx = root / "PRZEWODNIK_PO_PROJEKCIE.docx"

    doc = Document()

    for section in doc.sections:
        section.top_margin = Cm(2.0)
        section.bottom_margin = Cm(2.0)
        section.left_margin = Cm(2.2)
        section.right_margin = Cm(2.2)
        section.different_first_page_header_footer = True

        header = section.header
        hp = header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        hr = hp.add_run("Przewodnik po projekcie C05: Entropia i segmentacja plików binarnych (Od zera do HPC)")
        hr.font.name = "Calibri"
        hr.font.size = Pt(8.5)
        hr.font.color.rgb = MUTED
        hr.italic = True

        footer = section.footer
        fp = footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r0 = fp.add_run("Jan Wojnicki (147020), Adrian Sajdak (146992)  •  Strona ")
        r0.font.name = "Calibri"
        r0.font.size = Pt(9)
        r0.font.color.rgb = MUTED
        r_page = fp.add_run()
        r_page.font.name = "Calibri"
        r_page.font.size = Pt(9)
        r_page.font.color.rgb = MUTED
        r_mid = fp.add_run(" z ")
        r_mid.font.name = "Calibri"
        r_mid.font.size = Pt(9)
        r_mid.font.color.rgb = MUTED
        r_total = fp.add_run()
        r_total.font.name = "Calibri"
        r_total.font.size = Pt(9)
        r_total.font.color.rgb = MUTED
        add_page_number_fields(r_page, r_total)

    normal = doc.styles['Normal']
    normal.font.name = 'Calibri'
    normal.font.size = Pt(11)
    normal.font.color.rgb = DARK
    normal.paragraph_format.line_spacing = 1.18
    normal.paragraph_format.space_after = Pt(5)

    for level, size, color, sb, sa in [
        (1, 16, NAVY, 16, 6),
        (2, 13, ACCENT, 12, 4),
        (3, 11.5, NAVY, 9, 3),
    ]:
        st = doc.styles[f'Heading {level}']
        st.font.name = 'Calibri'
        st.font.size = Pt(size)
        st.font.bold = True
        st.font.color.rgb = color
        st.paragraph_format.space_before = Pt(sb)
        st.paragraph_format.space_after = Pt(sa)
        st.paragraph_format.keep_with_next = True

    # Title banner at the top of page 1
    banner = doc.add_table(rows=1, cols=1)
    banner.alignment = WD_TABLE_ALIGNMENT.CENTER
    bcell = banner.cell(0, 0)
    set_cell_shading(bcell, HEADER_BG)
    set_cell_margins(bcell, top=180, bottom=180, left=200, right=200)
    bp1 = bcell.paragraphs[0]
    bp1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    bp1.paragraph_format.space_after = Pt(4)
    br1 = bp1.add_run("PRZEWODNIK POPULARNONAUKOWY I ARCHITEKTONICZNY (OD ZERA DO HPC)")
    br1.font.size = Pt(10)
    br1.bold = True
    br1.font.color.rgb = RGBColor(190, 215, 245)

    bp2 = bcell.add_paragraph()
    bp2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    bp2.paragraph_format.space_after = Pt(6)
    br2 = bp2.add_run("C05: Entropia i segmentacja plików binarnych")
    br2.font.size = Pt(20)
    br2.bold = True
    br2.font.color.rgb = RGBColor(255, 255, 255)

    bp3 = bcell.add_paragraph()
    bp3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    bp3.paragraph_format.space_after = Pt(0)
    br3 = bp3.add_run(
        "Jak za pomocą klocków LEGO, przesuwnej lupy, pracowników w fabryce i tysięcy mrówek na karcie graficznej "
        "zrozumieć nowoczesne przetwarzanie równoległe (OpenMP, MPI, CUDA)\n"
        "Autorzy projektu: Jan Wojnicki (147020) • Adrian Sajdak (146992)"
    )
    br3.font.size = Pt(10)
    br3.italic = True
    br3.font.color.rgb = RGBColor(225, 235, 248)

    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(6)

    lines = md_path.read_text(encoding='utf-8').splitlines()
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped or stripped == '---':
            i += 1
            continue

        # Skip top-level # title since we rendered the hero banner
        if stripped.startswith('# '):
            i += 1
            continue

        # Code block
        if stripped.startswith('```'):
            i += 1
            code_lines = []
            while i < n and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            i += 1
            add_code_block(doc, code_lines)
            continue

        # Blockquote / Callout
        if stripped.startswith('>'):
            q_lines = []
            while i < n and lines[i].strip().startswith('>'):
                q_lines.append(lines[i].strip()[1:].lstrip())
                i += 1
            add_callout_box(doc, q_lines)
            continue

        # Markdown table
        if stripped.startswith('|') and stripped.endswith('|'):
            t_lines = []
            while i < n and lines[i].strip().startswith('|'):
                t_lines.append(lines[i])
                i += 1
            add_md_table(doc, t_lines)
            continue

        # Display formula $$...$$
        if stripped.startswith('$$') and stripped.endswith('$$'):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(6)
            r = p.add_run("H = − ∑ pᵢ · log₂(pᵢ)    (dla wszystkich koszyków o cᵢ > 0)")
            r.bold = True
            r.font.name = "Cambria Math"
            r.font.size = Pt(12)
            r.font.color.rgb = NAVY
            i += 1
            continue

        # Image ![caption](path)
        img_match = re.match(r'^!\[(.*?)\]\((.*?)\)$', stripped)
        if img_match:
            caption, rel_path = img_match.group(1), img_match.group(2)
            img_file = root / rel_path
            if img_file.exists():
                p_img = doc.add_paragraph()
                p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p_img.paragraph_format.space_before = Pt(6)
                p_img.paragraph_format.space_after = Pt(2)
                p_img.paragraph_format.keep_with_next = True
                run_img = p_img.add_run()
                run_img.add_picture(str(img_file), width=Cm(15.2))

                p_cap = doc.add_paragraph()
                p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p_cap.paragraph_format.space_after = Pt(8)
                rc = p_cap.add_run(f"Ilustracja z projektu: {caption}")
                rc.italic = True
                rc.font.size = Pt(9.5)
                rc.font.color.rgb = MUTED
            i += 1
            continue

        # Headings
        if stripped.startswith('## '):
            h = doc.add_heading(clean_latex_inline(stripped[3:]), level=1)
            i += 1
            continue
        if stripped.startswith('### '):
            h = doc.add_heading(clean_latex_inline(stripped[4:]), level=2)
            i += 1
            continue
        if stripped.startswith('#### '):
            h = doc.add_heading(clean_latex_inline(stripped[5:]), level=3)
            i += 1
            continue

        # Bullet or numbered list item
        if re.match(r'^(\*|-|\d+\.)\s+', stripped):
            indent_spaces = len(line) - len(line.lstrip(' '))
            is_numbered = bool(re.match(r'^\d+\.\s+', stripped))
            prefix_match = re.match(r'^(\*|-|\d+\.)\s+(.*)$', stripped)
            item_text = prefix_match.group(2)

            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.6 if indent_spaces < 2 else 1.2)
            p.paragraph_format.first_line_indent = Cm(-0.4)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.15
            marker = prefix_match.group(1) + " " if is_numbered else "• "
            rm = p.add_run(marker)
            rm.bold = True
            rm.font.color.rgb = ACCENT
            add_formatted_runs(p, item_text, font_size=11)
            i += 1
            continue

        # Regular paragraph (merge consecutive plain lines)
        para_lines = [stripped]
        i += 1
        while i < n:
            nxt = lines[i].strip()
            if (
                not nxt
                or nxt == '---'
                or nxt.startswith('#')
                or nxt.startswith('```')
                or nxt.startswith('>')
                or nxt.startswith('|')
                or nxt.startswith('$$')
                or nxt.startswith('![')
                or re.match(r'^(\*|-|\d+\.)\s+', nxt)
            ):
                break
            para_lines.append(nxt)
            i += 1
        p = doc.add_paragraph()
        p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_after = Pt(5)
        add_formatted_runs(p, " ".join(para_lines), font_size=11)

    doc.save(str(out_docx))
    print(f"Saved guide DOCX: {out_docx}")


if __name__ == "__main__":
    build_guide()
