#!/usr/bin/env python3
"""Generate academic report in DOCX format (and export to PDF via MS Word on Windows)."""
from pathlib import Path
import docx
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt, RGBColor


NAVY = RGBColor(20, 48, 92)
DARK = RGBColor(30, 30, 30)
MUTED = RGBColor(90, 90, 90)
HEADER_BG = "1B365D"
STRIPE_BG = "F3F6FA"
BORDER_COLOR = "B8C4D4"
CODE_BG = "F4F5F7"


def set_cell_shading(cell, color_hex):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>')
    tcPr.append(shd)


def set_cell_margins(cell, top=80, bottom=80, left=110, right=110):
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


def add_page_number_fields(run_page, run_total):
    fldChar1 = parse_xml(r'<w:fldChar %s w:fldCharType="begin"/>' % nsdecls('w'))
    instrText = parse_xml(r'<w:instrText %s xml:space="preserve"> PAGE </w:instrText>' % nsdecls('w'))
    fldChar2 = parse_xml(r'<w:fldChar %s w:fldCharType="separate"/>' % nsdecls('w'))
    fldChar3 = parse_xml(r'<w:fldChar %s w:fldCharType="end"/>' % nsdecls('w'))
    run_page._r.append(fldChar1)
    run_page._r.append(instrText)
    run_page._r.append(fldChar2)
    run_page._r.append(fldChar3)

    fldChar4 = parse_xml(r'<w:fldChar %s w:fldCharType="begin"/>' % nsdecls('w'))
    instrText2 = parse_xml(r'<w:instrText %s xml:space="preserve"> NUMPAGES </w:instrText>' % nsdecls('w'))
    fldChar5 = parse_xml(r'<w:fldChar %s w:fldCharType="separate"/>' % nsdecls('w'))
    fldChar6 = parse_xml(r'<w:fldChar %s w:fldCharType="end"/>' % nsdecls('w'))
    run_total._r.append(fldChar4)
    run_total._r.append(instrText2)
    run_total._r.append(fldChar5)
    run_total._r.append(fldChar6)


def configure_styles(doc):
    normal = doc.styles['Normal']
    normal.font.name = 'Times New Roman'
    normal.font.size = Pt(11)
    normal.font.color.rgb = DARK
    normal.paragraph_format.line_spacing = 1.15
    normal.paragraph_format.space_after = Pt(5)
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    for level, size, space_before, space_after in [
        (1, 14, 14, 6),
        (2, 12, 10, 4),
        (3, 11, 8, 3),
    ]:
        h = doc.styles[f'Heading {level}']
        h.font.name = 'Times New Roman'
        h.font.size = Pt(size)
        h.font.bold = True
        h.font.color.rgb = NAVY
        h.paragraph_format.space_before = Pt(space_before)
        h.paragraph_format.space_after = Pt(space_after)
        h.paragraph_format.keep_with_next = True
        h.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT


def add_p(doc, text="", bold_prefix=None, italic=False, align=WD_ALIGN_PARAGRAPH.JUSTIFY, space_after=5):
    p = doc.add_paragraph()
    p.paragraph_format.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    if bold_prefix:
        rb = p.add_run(bold_prefix)
        rb.bold = True
    if text:
        r = p.add_run(text)
        r.italic = italic
    return p


def add_bullet(doc, bold_prefix, text):
    p = doc.add_paragraph(style='List Bullet')
    p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.12
    if bold_prefix:
        rb = p.add_run(bold_prefix)
        rb.bold = True
    p.add_run(text)
    return p


def add_formula(doc, formula_text, number_str=None):
    p = doc.add_paragraph()
    p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(6)
    r = p.add_run(formula_text)
    r.font.name = 'Cambria Math'
    r.font.size = Pt(11)
    r.italic = True
    if number_str:
        rn = p.add_run(f"      ({number_str})")
        rn.font.name = 'Times New Roman'
        rn.font.size = Pt(10.5)
    return p


def add_code_block(doc, code_text):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = tbl.cell(0, 0)
    set_cell_shading(cell, CODE_BG)
    set_cell_margins(cell, top=90, bottom=90, left=140, right=140)
    tcPr = cell._tc.get_or_add_tcPr()
    tcPr.append(parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'<w:top w:val="single" w:sz="4" w:space="0" w:color="D0D7DE"/>'
        f'<w:bottom w:val="single" w:sz="4" w:space="0" w:color="D0D7DE"/>'
        f'<w:left w:val="single" w:sz="12" w:space="0" w:color="{HEADER_BG}"/>'
        f'<w:right w:val="single" w:sz="4" w:space="0" w:color="D0D7DE"/>'
        f'</w:tcBorders>'
    ))
    p = cell.paragraphs[0]
    p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.line_spacing = 1.05
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run(code_text.strip())
    r.font.name = 'Consolas'
    r.font.size = Pt(8.8)
    r.font.color.rgb = RGBColor(25, 25, 25)
    sp = doc.add_paragraph()
    sp.paragraph_format.space_after = Pt(3)


def add_academic_table(doc, caption, headers, rows, right_align_cols=()):
    cp = doc.add_paragraph()
    cp.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    cp.paragraph_format.space_before = Pt(6)
    cp.paragraph_format.space_after = Pt(3)
    cp.paragraph_format.keep_with_next = True
    parts = caption.split(':', 1)
    r1 = cp.add_run(parts[0] + (':' if len(parts) > 1 else ''))
    r1.bold = True
    r1.font.size = Pt(10)
    r1.font.color.rgb = NAVY
    if len(parts) > 1:
        r2 = cp.add_run(parts[1])
        r2.font.size = Pt(10)

    tbl = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl)

    hdr_cells = tbl.rows[0].cells
    trPr = tbl.rows[0]._tr.get_or_add_trPr()
    trPr.append(parse_xml(f'<w:tblHeader {nsdecls("w")}/>'))
    for j, htext in enumerate(headers):
        cell = hdr_cells[j]
        set_cell_shading(cell, HEADER_BG)
        set_cell_margins(cell, top=80, bottom=80, left=85, right=85)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        p = cell.paragraphs[0]
        p.paragraph_format.alignment = (
            WD_ALIGN_PARAGRAPH.RIGHT if j in right_align_cols else WD_ALIGN_PARAGRAPH.LEFT
        )
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.05
        run = p.add_run(htext)
        run.bold = True
        run.font.name = 'Times New Roman'
        run.font.size = Pt(9.2)
        run.font.color.rgb = RGBColor(255, 255, 255)

    for i, row_data in enumerate(rows):
        row_cells = tbl.rows[i + 1].cells
        bg = STRIPE_BG if i % 2 == 1 else "FFFFFF"
        for j, val in enumerate(row_data):
            cell = row_cells[j]
            set_cell_shading(cell, bg)
            set_cell_margins(cell, top=60, bottom=60, left=85, right=85)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            p = cell.paragraphs[0]
            p.paragraph_format.alignment = (
                WD_ALIGN_PARAGRAPH.RIGHT if j in right_align_cols else WD_ALIGN_PARAGRAPH.LEFT
            )
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.05
            text_val = str(val)
            is_bold = text_val.startswith('**') and text_val.endswith('**')
            if is_bold:
                text_val = text_val[2:-2]
            run = p.add_run(text_val)
            run.bold = is_bold
            run.font.name = 'Times New Roman'
            run.font.size = Pt(9.0)
            run.font.color.rgb = DARK

    sp = doc.add_paragraph()
    sp.paragraph_format.space_after = Pt(4)
    return tbl


def add_figure(doc, image_path, caption, width_cm=15.6):
    if not Path(image_path).is_file():
        return
    p_img = doc.add_paragraph()
    p_img.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_img.paragraph_format.space_before = Pt(6)
    p_img.paragraph_format.space_after = Pt(2)
    p_img.paragraph_format.keep_with_next = True
    run_img = p_img.add_run()
    run_img.add_picture(str(image_path), width=Cm(width_cm))

    p_cap = doc.add_paragraph()
    p_cap.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_cap.paragraph_format.space_after = Pt(8)
    parts = caption.split(':', 1)
    r1 = p_cap.add_run(parts[0] + (':' if len(parts) > 1 else ''))
    r1.bold = True
    r1.font.size = Pt(9.5)
    r1.font.color.rgb = NAVY
    if len(parts) > 1:
        r2 = p_cap.add_run(parts[1])
        r2.italic = True
        r2.font.size = Pt(9.5)
        r2.font.color.rgb = MUTED


def build_report(root: Path, output_docx: Path):
    plots = root / 'results' / 'plots'
    doc = Document()

    for section in doc.sections:
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(2.3)
        section.bottom_margin = Cm(2.3)
        section.left_margin = Cm(2.3)
        section.right_margin = Cm(2.3)
        section.different_first_page_header_footer = True

        # Running header and footer on subsequent pages
        hdr = section.header.paragraphs[0]
        hdr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        rh = hdr.add_run("Programowanie Równoległe i Rozproszone — Projekt C05: Entropia i segmentacja plików binarnych")
        rh.font.name = 'Times New Roman'
        rh.font.size = Pt(8.5)
        rh.italic = True
        rh.font.color.rgb = MUTED

        ftr = section.footer.paragraphs[0]
        ftr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        rf_left = ftr.add_run("Jan Wojnicki (147020), Adrian Sajdak (146992)  |  Strona ")
        rf_left.font.name = 'Times New Roman'
        rf_left.font.size = Pt(9)
        rf_left.font.color.rgb = MUTED
        r_pg = ftr.add_run()
        r_pg.font.name = 'Times New Roman'
        r_pg.font.size = Pt(9)
        r_pg.font.color.rgb = MUTED
        rf_mid = ftr.add_run(" z ")
        rf_mid.font.name = 'Times New Roman'
        rf_mid.font.size = Pt(9)
        rf_mid.font.color.rgb = MUTED
        r_tot = ftr.add_run()
        r_tot.font.name = 'Times New Roman'
        r_tot.font.size = Pt(9)
        r_tot.font.color.rgb = MUTED
        add_page_number_fields(r_pg, r_tot)

    configure_styles(doc)

    # =========================================================================
    # STRONA TYTUŁOWA
    # =========================================================================
    p_top = doc.add_paragraph()
    p_top.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_top.paragraph_format.space_before = Pt(18)
    p_top.paragraph_format.space_after = Pt(4)
    r_top = p_top.add_run("PROGRAMOWANIE RÓWNOLEGŁE I ROZPROSZONE\nSPRAWOZDANIE Z PROJEKTU OBLICZENIOWEGO")
    r_top.bold = True
    r_top.font.size = Pt(12)
    r_top.font.color.rgb = NAVY

    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(24)
    p_title.paragraph_format.space_after = Pt(10)
    r_title = p_title.add_run("Projekt C05: Entropia i segmentacja plików binarnych")
    r_title.bold = True
    r_title.font.size = Pt(20)
    r_title.font.color.rgb = NAVY

    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_sub.paragraph_format.space_after = Pt(22)
    r_sub = p_sub.add_run(
        "Analiza porównawcza implementacji referencyjnej (C++20), wielowątkowej (OpenMP),\n"
        "wieloprocesowej (MPI) oraz akcelerowanej na GPU (NVIDIA CUDA)\n"
        "z uwzględnieniem przyrostowej aktualizacji przesuwnego histogramu (zakres 2-osobowy)"
    )
    r_sub.italic = True
    r_sub.font.size = Pt(11.5)
    r_sub.font.color.rgb = MUTED

    add_academic_table(
        doc,
        "Metryka projektu i skład zespołu autorskiego",
        ["Parametr projektu", "Wartość / Szczegóły"],
        [
            ["**Autor 1**", "**Jan Wojnicki — nr albumu: 147020**"],
            ["**Autor 2**", "**Adrian Sajdak — nr albumu: 146992**"],
            ["Identyfikator i poziom tematu", "C05 — Entropia i segmentacja plików binarnych (poziom łatwy, zespół 2-osobowy)"],
            ["Zakres rozszerzony (2 osoby)", "Przyrostowa aktualizacja histogramu (--mode incremental) i porównanie z wariantem naiwnym (--mode naive) we wszystkich 4 technologiach"],
            ["Zrealizowane technologie", "1) Referencja sekwencyjna C++20, 2) OpenMP, 3) MPI (OpenMPI 4.1.6), 4) NVIDIA CUDA 12.6"],
            ["Platforma obliczeniowa CPU", "AMD Ryzen 5 2600 Six-Core Processor (1 węzeł, 6 rdzeni fizycznych / 12 wątków logicznych SMT, 16 GB RAM DDR4)"],
            ["Platforma obliczeniowa GPU", "NVIDIA GeForce GTX 1660 (architektura Turing TU116, sm_75, 22 multiprocesory SM, 1408 rdzeni CUDA, 6 GB GDDR5)"],
            ["Środowisko kompilacji", "Ubuntu 24.04 LTS (WSL2), GCC 13.3.0 (-O3 -march=native), CUDA nvcc 12.6.85 (-O3 -arch=sm_75 -lineinfo), CMake 3.28.3"],
        ],
    )

    add_p(
        doc,
        "W niniejszym sprawozdaniu przedstawiono projekt, implementację oraz kompleksową analizę "
        "wydajnościową i numeryczną systemu obliczającego entropię Shannona rozkładu bajtów w kolejnych "
        "oknach pliku binarnego w celu lokalizacji granic obszarów o odmiennej strukturze statystycznej. "
        "Zrealizowano cztery pełne implementacje: sekwencyjną referencję CPU, wersję wielowątkową OpenMP "
        "(z prywatnymi histogramami wątków), wersję wieloprocesową MPI (z podziałem domenowym i zakładką halo) "
        "oraz wersję akcelerowaną na karcie graficznej NVIDIA CUDA (z histogramami w pamięci współdzielonej bloków "
        "i redukcją drzewiastą). W ramach zakresu dla zespołu dwuosobowego we wszystkich czterech technologiach "
        "zaimplementowano i porównano dwa warianty algorytmiczne: wariant naiwny O(K·W) oraz wariant przyrostowej "
        "aktualizacji przesuwnego histogramu O(W + K·S). Ponadto opracowano algorytm scalania sąsiednich okien "
        "przekraczających próg zmiany w pojedyncze zdarzenia granic (--events), zbadano błąd estymacji entropii "
        "względem asymptotycznego obciążenia Millera–Madowa oraz przeprowadzono parametryczną analizę wpływu "
        "koncentracji bajtów (k = 1..256) na konkurencję operacji atomowych w pamięci współdzielonej GPU.",
        bold_prefix="Streszczenie. ",
        space_after=8,
    )

    doc.add_page_break()

    # =========================================================================
    # 1. CEL PROJEKTU I SFORMUŁOWANIE MATEMATYCZNE
    # =========================================================================
    doc.add_heading("1. Cel projektu i matematyczne sformułowanie problemu", level=1)
    add_p(
        doc,
        "Analiza entropii przesuwnych fragmentów (okien) pliku binarnego jest jedną z podstawowych metod "
        "wstępnej segmentacji nieznanych obiektów binarnych (np. obrazów pamięci, kontenerów firmware, "
        "plików wykonywalnych oraz strumieni sieciowych). Różne klasy danych cechują się odmiennym rozkładem "
        "częstości bajtów: obszary wypełnione stałą wartością (padding) mają entropię równą 0 bit/bajt, "
        "tekst w kodowaniu ASCII wykazuje entropię rzędu 4,0–5,0 bit/bajt, kod maszynowy osiąga zwykle "
        "5,5–6,8 bit/bajt, natomiast dane skompresowane lub zaszyfrowane zbliżają się do maksymalnej "
        "entropii 8,0 bit/bajt. Gwałtowna zmiana entropii pomiędzy kolejnymi oknami wskazuje na granicę "
        "pomiędzy segmentami o różnej strukturze."
    )
    add_p(
        doc,
        "Sama wysoka wartość entropii nie stanowi dowodu złośliwości pliku ani użycia szyfrowania — "
        "identyczną entropię bliską 8 bit/bajt posiadają legalne archiwa skompresowane (ZIP, GZ, XZ), "
        "zasoby multimedialne (JPEG, MP4, WebP) oraz ciągi pseudolosowe.",
        bold_prefix="Istotna uwaga interpretacyjna: ",
    )

    doc.add_heading("1.1. Układ pełnych okien, niepełne okno końcowe oraz przerwy", level=2)
    add_p(
        doc,
        "Niech wejściowy plik binarny o rozmiarze N bajtów będzie reprezentowany jako ciąg "
        "B = (b_0, b_1, ..., b_{N-1}), gdzie każdy bajt przyjmuje wartość ze zbioru {0, 1, ..., 255}. "
        "Dla zadanej długości okna W >= 1 oraz kroku przesunięcia okna S >= 1 analizowane są wyłącznie "
        "pełne okna mieszczące się w granicach pliku. Liczba pełnych okien K wynosi:"
    )
    add_formula(doc, "K = 0   gdy N < W,       oraz       K = 1 + ⌊(N − W) / S⌋   gdy N ≥ W.", "1")
    add_p(
        doc,
        "Każde okno o indeksie i ∈ {0, 1, ..., K − 1} rozpoczyna się pod globalnym offsetem bajtowym "
        "offset_i = i · S i obejmuje spójny przedział bajtów [i · S, i · S + W). Przyjęcie zasady "
        "wyłącznego przetwarzania pełnych okien ma kluczowe uzasadnienie statystyczne: uwzględnienie "
        "krótszego okna końcowego o rozmiarze W_ogon << W wprowadziłoby silne ujemne obciążenie "
        "estymatora entropii na samym końcu pliku, generując fałszywą granicę segmentu. "
        "Program jawnie wylicza i raportuje na standardowym wyjściu diagnostycznym (stderr):"
    )
    add_bullet(
        doc,
        "Bajty pominięte za ostatnim pełnym oknem (omitted_trailing_bytes): ",
        "N_trail = N (gdy K = 0) lub N_trail = N − ((K − 1)·S + W) (gdy K >= 1)."
    )
    add_bullet(
        doc,
        "Bajty w niepokrytych przerwach między oknami dla S > W (uncovered_gap_bytes): ",
        "N_gap = (K − 1)·(S − W) gdy S > W oraz K >= 1 (0 w przeciwnym razie)."
    )

    doc.add_heading("1.2. Histogram rozkładu bajtów i entropia Shannona", level=2)
    add_p(
        doc,
        "W każdym oknie i budowany jest 256-koszykowy histogram częstości wystąpień poszczególnych wartości "
        "bajtów c_i[v] dla v ∈ {0, 1, ..., 255}, spełniający warunek ∑_{v=0}^{255} c_i[v] = W. "
        "Empiryczne prawdopodobieństwo wystąpienia bajtu v w oknie i wynosi p_i(v) = c_i[v] / W. "
        "Entropia Shannona H_i wyrażona w bitach na bajt (o zakresie wartości [0, 8]) określona jest wzorem:"
    )
    add_formula(doc, "H_i = − ∑_{v ∈ {0..255} : c_i[v] > 0} (c_i[v] / W) · log₂(c_i[v] / W).", "2")
    add_p(
        doc,
        "Zgodnie z granicą matematyczną lim_{p → 0⁺} p · log₂(p) = 0 wszystkie koszyki o zerowej liczności "
        "(c_i[v] = 0) są jawnie pomijane przed wywołaniem funkcji logarytmicznej, co zapobiega powstawaniu "
        "wartości nieoznaczonych NaN (0 · (−∞)) w arytmetyce IEEE-754."
    )

    doc.add_heading("1.3. Detekcja granic oraz scalanie sąsiednich przekroczeń progu (--events)", level=2)
    add_p(
        doc,
        "Dla każdego okna i >= 1 wyznaczana jest podpisana różnica entropii względem okna poprzedniego: "
        "ΔH_i = H_i − H_{i-1} (dla pierwszego okna i = 0 przyjmujemy ΔH_0 = 0 oraz brak flagi granicy, "
        "nawet gdy próg T = 0). Okno i >= 1 otrzymuje flagę przekroczenia progu (is_boundary = 1) wtedy "
        "i tylko wtedy, gdy spełniona jest nierówność słaba:"
    )
    add_formula(doc, "|ΔH_i| = |H_i − H_{i-1}| ≥ T.", "3")
    add_p(
        doc,
        "W przypadku okien nakładających się (S < W, np. S = W/4) pojedyncza fizyczna granica pomiędzy dwoma "
        "segmentami o różnych rozkładach znajduje się równocześnie wewnątrz około W/S kolejnych okien. "
        "W rezultacie zmiana entropii narasta stopniowo przez W/S kroków, a każde z tych kolejnych okien "
        "może przekroczyć próg T, dając serię sąsiednich flag is_boundary = 1 dla jednej fizycznej zmiany. "
        "Aby zwrócić użytkownikowi zwięzłą i jednoznaczną listę zmian w pliku, w module common/io.cpp "
        "zaimplementowano procedurę merge_boundaries (aktywowaną opcją --events PLIK.csv), która łączy "
        "każdy maksymalny spójny ciąg kolejnych oznaczonych okien [i_first, i_last] w pojedyncze zdarzenie "
        "zmiany (BoundaryEvent) i wyznacza estymowany offset fizycznej granicy jako środek przedziału przejściowego:"
    )
    add_formula(doc, "x̂_granica = ⌊ ((i_first − 1)·S + (i_last·S + W)) / 2 ⌋.", "4")

    # =========================================================================
    # 2. ARCHITEKTURA, PODZIAŁ OBLICZEŃ, SYNCHRONIZACJA I KOMUNIKACJA
    # =========================================================================
    doc.add_heading("2. Architektura rozwiązania i szczegóły implementacyjne", level=1)

    doc.add_heading("2.1. Wyodrębnienie wkładu własnego i rola bibliotek", level=2)
    add_p(
        doc,
        "Cały rdzeń obliczeniowy projektu — obejmujący wyznaczanie histogramów 256-wartościowych, "
        "przyrostową aktualizację przesuwnego okna, obliczanie entropii Shannona, równoległą redukcję "
        "drzewiastą w pamięci współdzielonej GPU, podział domenowy z zakładką halo w MPI, detekcję "
        "przekroczeń progu oraz scalanie zdarzeń zmian — został napisany w 100% samodzielnie w językach "
        "C++20 oraz CUDA C++. Wykorzystane biblioteki zewnętrzne pełnią wyłącznie rolę niskopoziomowych "
        "mechanizmów uruchomieniowych i pomocniczych: OpenMP (dyrektywy wielowątkowości), OpenMPI "
        "(komunikacja międzyprocesowa), CUDA Runtime API (zarządzanie pamięcią GPU, strumieniami i "
        "zdarzeniami pomiarowymi) oraz pakiety Python (matplotlib, seaborn, pandas, numpy) w skryptach "
        "generujących wykresy."
    )

    doc.add_heading("2.2. Wariant naiwny vs wariant przyrostowy (zakres dla zespołu 2-osobowego)", level=2)
    add_p(
        doc,
        "Zgodnie z wymaganiami dla zespołu dwuosobowego we wszystkich czterech technologiach (Reference, "
        "OpenMP, MPI, CUDA) zaimplementowano i poddano porównaniu dwa algorytmy budowy histogramu:"
    )
    add_academic_table(
        doc,
        "Tabela 1: Porównanie algorytmiczne wariantu naiwnego (--mode naive) oraz przyrostowego (--mode incremental)",
        ["Kryterium", "Wariant naiwny (--mode naive)", "Wariant przyrostowy (--mode incremental)"],
        [
            ["Zasada aktualizacji histogramu", "Pełne wyzerowanie 256 liczników i zliczenie wszystkich W bajtów w każdym z K okien niezależnie.", "Zbudowanie pełnego histogramu tylko dla pierwszego okna pasma, a następnie dla każdego kolejnego okna (gdy S < W) odjęcie S bajtów opuszczających okno i dodanie S bajtów wchodzących do okna."],
            ["Złożoność czasowa zliczania bajtów", "O(K · W) operacji aktualizacji koszyków", "O(W + (K − 1) · 2S) operacji aktualizacji koszyków (dla S < W)"],
            ["Teoretyczna redukcja operacji na bajtach", "1,00× (punkt odniesienia)", "W / (2S) — dla S = W/4 dokładnie 2,00× mniej operacji na pamięci; dla S = W/8: 4,00× mniej"],
            ["Złożoność wyznaczania entropii z histogramu", "O(K · 256) operacji zmiennoprzecinkowych double", "O(K · 256) operacji zmiennoprzecinkowych double (identyczna)"],
            ["Zależności danych między oknami", "Brak — wszystkie okna mogą być przetwarzane w dowolnej kolejności.", "Zależność sekwencyjna wewnątrz spójnego pasma okien przydzielonego do jednego wątku / procesu / bloku GPU."],
        ],
    )

    doc.add_heading("2.3. Podział obliczeń, synchronizacja i komunikacja w poszczególnych technologiach", level=2)
    add_bullet(
        doc,
        "1. Wersja referencyjna (src/reference.cpp, common/compute.cpp): ",
        "Realizuje przetwarzanie jednowątkowe na CPU. W trybie naive wywołuje funkcję window_entropy dla każdego "
        "podprzedziału bytes.subspan(i * S, W). W trybie incremental utrzymuje pojedynczą tablicę Histogram (1 KB) "
        "w pamięci podręcznej L1 i aktualizuje ją w pętli po j ∈ [0, S): --histogram[bytes[old_start + j]] oraz "
        "++histogram[bytes[old_start + W + j]]."
    )
    add_bullet(
        doc,
        "2. Wersja OpenMP (src/openmp.cpp): ",
        "Wewnątrz bloku #pragma omp parallel każdy wątek roboczy deklaruje na stosie własną, prywatną tablicę "
        "c05::Histogram histogram{} (std::array<uint32_t, 256>). Dzięki temu podczas analizy bajtów żaden licznik "
        "nie jest współdzielony między wątkami, nie występują operacje atomowe na CPU ani zjawisko false sharing "
        "linii pamięci podręcznej. W trybie naive okna rozdzielane są dyrektywą #pragma omp for schedule(static), "
        "natomiast w trybie incremental zbiór K okien dzielony jest na P spójnych pasm o rozmiarach różniących się "
        "o co najwyżej 1 okno (first = (K/P)*t + min(t, K%P)), a każdy wątek wykonuje aktualizację przyrostową "
        "na swoim paśmie. Synchronizacja ogranicza się do pojedynczej bariery kończącej region równoległy."
    )
    add_bullet(
        doc,
        "3. Wersja MPI (src/mpi.cpp): ",
        "Zastosowano podział domenowy po indeksach okien: proces o randze r ∈ {0, ..., P − 1} otrzymuje spójny "
        "przedział count_r okien zaczynający się od globalnego okna first_r. Ponieważ każde okno ma dokładnie "
        "jednego właściciela, na granicach podobszarów nie powstają zduplikowane wyniki. Aby proces r mógł "
        "obliczyć swoje okna bez dodatkowej komunikacji w trakcie obliczeń, proces 0 przesyła mu spójny wycinek "
        "bajtów o długości byte_count[r] = (count_r − 1)·S + W zaczynający się od byte_offset[r] = first_r · S "
        "(zawierający zakładkę halo o szerokości W − S bajtów wspólną z kolejnym procesem). Ze względu na nakładanie "
        "się wycinków w pamięci procesu 0 dystrybucja realizowana jest nieblokującymi wywołaniami MPI_Isend + "
        "MPI_Waitall (na procesie 0) oraz MPI_Recv (na procesach 1..P−1). Po lokalnym obliczeniu entropii (w trybie "
        "naive lub incremental) wyniki są scalane na procesie 0 wywołaniem kolektywnym MPI_Gatherv z tablicą "
        "przesunięć offsets[r] = first_r, co zachowuje globalne pozycje bajtowe."
    )
    add_bullet(
        doc,
        "4. Wersja CUDA (src/cuda_entropy.cu): ",
        "Każdy blok wątków posiada w szybkiej pamięci współdzielonej (shared memory) własny histogram "
        "__shared__ unsigned int s_hist[256] (1 KB) oraz tablicę __shared__ double s_terms[256] (2 KB). "
        "W trybie naive (histogram_entropy_kernel) jeden blok przetwarza jedno okno na iterację pętli grid-stride: "
        "wątki zerują s_hist, po barierze __syncthreads() odczytują koalescencyjnie bajty okna (co krok blockDim.x) "
        "i wykonują atomicAdd(&s_hist[b], 1U) w pamięci współdzielonej, a po kolejnej barierze obliczają składniki "
        "−p·log₂(p) i sumują je drzewiastą redukcją równoległą (stride = 128, 64, ..., 1). W trybie incremental "
        "(incremental_entropy_kernel) każdy blok otrzymuje spójne pasmo okien (do 64 okien na pasmo): pierwsze "
        "okno pasma budowane jest w całości, a kolejne okna aktualizowane są przez atomicSub (dla S bajtów "
        "opuszczających okno) oraz atomicAdd (dla S bajtów wchodzących). Drugi kernel (boundary_flags_kernel) "
        "wyznacza równolegle wektor flag przekroczenia progu d_flags[i]."
    )

    # =========================================================================
    # 3. KONFIGURACJA SPRZĘTOWA, DANE I METODOLOGIA POMIARÓW
    # =========================================================================
    doc.add_heading("3. Konfiguracja sprzętowa, zbiory danych i metodologia pomiarów", level=1)
    add_academic_table(
        doc,
        "Tabela 2: Szczegółowa konfiguracja sprzętowa i programowa stanowiska pomiarowego",
        ["Komponent", "Specyfikacja techniczna"],
        [
            ["Procesor (CPU)", "AMD Ryzen 5 2600 Six-Core Processor (architektura Zen+, 1 węzeł, 6 rdzeni fizycznych, 12 wątków logicznych SMT)"],
            ["Pamięć operacyjna (RAM)", "16 GB DDR4 (11,68 GB dostępne w instancji Linux WSL2, /dev/shm = 2 GB dla transportu shared-memory MPI)"],
            ["Akcelerator GPU", "NVIDIA GeForce GTX 1660 (architektura Turing TU116, Compute Capability 7.5, 22 SM, 1408 rdzeni CUDA, 6144 MB GDDR5)"],
            ["Sterownik GPU / CUDA", "NVIDIA Driver 610.88 (CUDA UMD 13.3) / NVIDIA CUDA Toolkit 12.6.85 (nvcc V12.6.85)"],
            ["System operacyjny", "Ubuntu 24.04 LTS (jądro Linux 5.15.167.4-microsoft-standard-WSL2 x86_64, glibc 2.39)"],
            ["Kompilator C++ / OpenMP", "GCC 13.3.0 (flagi: -std=c++20 -O3 -march=native -Wall -Wextra -fopenmp)"],
            ["Flagi kompilacji CUDA", "nvcc -std=c++20 -O3 -arch=sm_75 -lineinfo -Xcompiler=-Wall,-Wextra,-march=native (bez --use_fast_math)"],
            ["Środowisko MPI", "OpenMPI 4.1.6 (transport lokalny shared-memory, pojedynczy węzeł fizyczny)"],
            ["Środowisko analizy i wykresów", "Python 3.12.3, NumPy 1.26.4, Pandas 2.1.4, Matplotlib 3.6.3, Seaborn 0.13.2"],
        ],
    )

    add_academic_table(
        doc,
        "Tabela 3: Charakterystyka deterministycznych zbiorów danych testowych (seed = 2026)",
        ["Nazwa zbioru", "Rozmiar [B]", "Liczba symboli k", "Entropia teoretyczna H_teor", "Przeznaczenie eksperymentalne i suma SHA-256 (skrót)"],
        [
            ["constant_bytes.bin", "100 000 000", "1 (0x00)", "0,000000 bit/B", "Maksymalna koncentracja bajtów w 1 koszyku (100% kolizji atomic). SHA-256: a993f8c5..."],
            ["uniform_random.bin", "100 000 000", "256", "8,000000 bit/B", "Rozkład jednostajny pełnego alfabetu (minimalna kolizja atomic). SHA-256: c0bb4bf1..."],
            ["mixed_segmented.bin", "150 000 000", "23 / 252 / 1", "4,5236 / 7,9546 / 0,0", "3 segmenty po 50 MB (ASCII, biased random, zera); granice: 50 MB i 100 MB. SHA-256: 7a15b6aa..."],
            ["multi_segmented.bin", "150 000 000", "1 / 4 / 23 / 256 / 16", "0 / 2 / 4,5236 / 8 / 4", "5 segmentów o różnych długościach (20, 30, 40, 30, 30 MB); 4 granice: 20, 50, 90, 120 MB. SHA-256: fa5c9e45..."],
            ["ksym_{1..256}.bin", "9 × 50 000 000", "1, 2, 4, 8, 16, 32, 64, 128, 256", "log₂(k) = 0,0 .. 8,0 bit/B", "Seria 9 plików o kontrolowanej koncentracji 1/k do badania konkurencji operacji atomowych GPU."],
        ],
    )

    add_p(
        doc,
        "Zgodnie z wymogami metodologicznymi we wszystkich eksperymentach oddzielono pomiar czasu rdzenia "
        "obliczeń (T_core — wyłącznie wyznaczanie histogramów i entropii) od całkowitego czasu przetwarzania "
        "(T_total — obejmującego wczytanie pliku wejściowego z dysku, alokację pamięci, inicjalizację zasobów "
        "CUDA/MPI, transfery H2D i D2H, detekcję granic, scalenie zmian oraz zapis i zamknięcie pliku CSV). "
        "Na GPU przed rozpoczęciem każdej fazy pomiarowej wykonywane jest cudaDeviceSynchronize(), znacznik "
        "końcowy cudaEventRecord(stop) kolejkowany jest bezpośrednio po operacji w strumieniu, a odczyt czasu "
        "następuje dopiero po pełnej synchronizacji urządzenia. Dla każdej z 134 konfiguracji głównych oraz "
        "wszystkich konfiguracji dodatkowych wykonano 1 odrzucany przebieg rozgrzewkowy (warm-up) oraz 5 "
        "niezależnych pomiarów właściwych w losowo przetasowanej kolejności. W tabelach i na wykresach "
        "prezentowana jest mediana oraz rozrzut min–max."
    )

    # =========================================================================
    # 4. WALIDACJA POPRAWNOŚCI I ANALIZA BŁĘDU ENTROPII
    # =========================================================================
    doc.add_heading("4. Walidacja poprawności i analiza błędu entropii", level=1)
    add_p(
        doc,
        "Przed uruchomieniem pomiarów wydajności przeprowadzono pełną weryfikację poprawności wszystkich "
        "czterech technologii za pomocą zestawu testów automatycznych CTest (100% testów zakończonych "
        "wynikiem PASS):"
    )
    add_bullet(
        doc,
        "Test 1 (host_model_correctness — tests/check_cuda_model.py): ",
        "500 losowych modeli redukcji drzewiastej dla bloków 64..1024 wątków (błąd względem math.fsum < 10⁻¹²), "
        "weryfikacja jednoznacznego pokrycia indeksów w pętlach grid-stride oraz symulacja przeplotu "
        "atomicSub/atomicAdd w arytmetyce modularnej uint32_t."
    )
    add_bullet(
        doc,
        "Test 2 (reference_and_openmp_correctness — tests/verify_correctness.py): ",
        "144 przypadki brzegowe (pusty plik, N < W, W = 1, S < W, S = W, S > W, progi 0,0, 0,1, 8,0) porównujące "
        "Ref-Naive, Ref-Incremental, OMP-Naive i OMP-Incremental (dla 1, 2 i 4 wątków) z niezależną wyrocznią "
        "w Pythonie (max_error = 0), test progu włącznego |ΔH| = T, weryfikacja plików --events oraz odrzucania "
        "błędnych argumentów CLI i próby nadpisania pliku wejściowego."
    )
    add_bullet(
        doc,
        "Test 3 (mpi_correctness — tests/verify_mpi.py): ",
        "128 konfiguracji porównujących MPI-Naive i MPI-Incremental dla liczby procesów p ∈ {1, 2, 4, 7} "
        "(w tym przypadek brzegowy p > K, w którym część procesów otrzymuje 0 okien) z referencją sekwencyjną "
        "(max_error = 0)."
    )
    add_bullet(
        doc,
        "Test 4 (cuda_correctness — tests/verify_cuda.py): ",
        "112 konfiguracji uruchomionych na fizycznej karcie NVIDIA GeForce GTX 1660 dla obu trybów (naive oraz "
        "incremental) i wszystkich rozmiarów bloku (64, 128, 256, 512, 1024); maksymalny zaobserwowany błąd "
        "względem referencji CPU wyniósł 3,55 × 10⁻¹⁵ bit/bajt."
    )

    add_academic_table(
        doc,
        "Tabela 4: Zgodność numeryczna poszczególnych implementacji względem sekwencyjnej referencji Ref-Naive (zbiór mixed_segmented.bin, W = 65536, S = 16384, K = 9152 okna)",
        ["Implementacja", "Tryb algorytmu", "Maks. błąd |ΔH|_max [bit/B]", "Średni błąd |ΔH|_śr [bit/B]", "Zgodność flag granic (is_boundary)"],
        [
            ["Ref-Naive (1 wątek)", "naive", "0,0", "0,0", "100% (9152 / 9152)"],
            ["Ref-Incremental (1 wątek)", "incremental", "0,0", "0,0", "100% (9152 / 9152)"],
            ["OMP (12 wątków)", "naive", "0,0", "0,0", "100% (9152 / 9152)"],
            ["OMP-Incremental (12 wątków)", "incremental", "0,0", "0,0", "100% (9152 / 9152)"],
            ["MPI (6 procesów)", "naive", "0,0", "0,0", "100% (9152 / 9152)"],
            ["MPI-Incremental (6 procesów)", "incremental", "0,0", "0,0", "100% (9152 / 9152)"],
            ["CUDA (blok 256)", "naive", "1,688 × 10⁻¹⁴", "1,007 × 10⁻¹⁵", "100% (9152 / 9152)"],
            ["CUDA-Incremental (blok 256)", "incremental", "1,688 × 10⁻¹⁴", "1,007 × 10⁻¹⁵", "100% (9152 / 9152)"],
        ],
        right_align_cols=(2, 3),
    )

    add_p(
        doc,
        "Niezależnie od zgodności numerycznej pomiędzy CPU a GPU, w raporcie zbadano również statystyczny "
        "błąd estymacji entropii z okna o skończonej długości W względem teoretycznej entropii populacji "
        "H_teor generatora. Zgodnie z rozwinięciem Taylora (poprawka Millera–Madowa) wartość oczekiwana "
        "estymatora plug-in na próbie o liczności W dla alfabetu o k niezerowych symbolach jest obciążona ujemnie:"
    )
    add_formula(doc, "Bias_MM(W, k) = E[H_emp] − H_teor ≈ − (k − 1) / (2 · W · ln 2).", "5")

    add_academic_table(
        doc,
        "Tabela 5: Porównanie empirycznego błędu estymacji entropii z okna skończonego z teoretycznym obciążeniem Millera–Madowa (wyniki z results/entropy_accuracy_summary.csv)",
        ["Rodzaj segmentu", "Symbole k", "H_teor [bit/B]", "Okno W [B]", "Teor. bias Millera–Madowa", "Średni błąd H_emp − H_teor", "Średni błąd |H_emp − H_teor|", "Maks. błąd |ΔH|_max"],
        [
            ["zeros (constant)", "1", "0,000000", "1024..65536", "0,000000", "0,000000", "0,000000", "0,000000"],
            ["ksymbol_4", "4", "2,000000", "1024", "−0,002113", "−0,002111", "0,002111", "0,016875"],
            ["ksymbol_4", "4", "2,000000", "65536", "−0,000033", "−0,000031", "0,000031", "0,000212"],
            ["ksymbol_16", "16", "4,000000", "1024", "−0,010567", "−0,010595", "0,010595", "0,033621"],
            ["ksymbol_16", "16", "4,000000", "65536", "−0,000165", "−0,000164", "0,000164", "0,000375"],
            ["synthetic_ascii", "23", "4,523562", "1024", "−0,015498", "−0,015559", "0,015559", "0,040818"],
            ["synthetic_ascii", "23", "4,523562", "4096", "−0,003874", "−0,003888", "0,003888", "0,010806"],
            ["synthetic_ascii", "23", "4,523562", "16384", "−0,000969", "−0,000969", "0,000969", "0,002188"],
            ["synthetic_ascii", "23", "4,523562", "65536", "−0,000242", "−0,000243", "0,000243", "0,000489"],
            ["uniform_256", "256", "8,000000", "1024", "−0,179632", "−0,191289", "0,191289", "0,270488"],
            ["uniform_256", "256", "8,000000", "4096", "−0,044908", "−0,045403", "0,045403", "0,060694"],
            ["uniform_256", "256", "8,000000", "16384", "−0,011227", "−0,011248", "0,011248", "0,015135"],
            ["uniform_256", "256", "8,000000", "65536", "−0,002807", "−0,002813", "0,002813", "0,003627"],
        ],
        right_align_cols=(1, 2, 3, 4, 5, 6, 7),
    )

    add_figure(
        doc,
        plots / 'entropy_error_analysis.png',
        "Rysunek 1: Średni błąd bezwzględny estymacji entropii |H_emp − H_teor| w funkcji rozmiaru okna W w zestawieniu z teoretycznym obciążeniem Millera–Madowa.",
    )

    # =========================================================================
    # 5. SKALOWANIE SILNE CPU (OPENMP) I MPI (LOKALNE SHARED-MEMORY)
    # =========================================================================
    doc.add_heading("5. Skalowanie silne CPU (OpenMP) i MPI (lokalna pamięć współdzielona)", level=1)
    add_p(
        doc,
        "Badanie skalowania silnego (strong scaling) przeprowadzono przy stałym rozmiarze problemu "
        "(zbiór mixed_segmented.bin, N = 150 MB, W = 65536, S = 16384, K = 9152 okna). Przyspieszenie "
        "S(p) = T_core(1) / T_core(p) oraz efektywność E(p) = S(p) / p wyznaczono względem pojedynczego "
        "wątku/procesu (p = 1) tej samej metody i technologii. Wszystkie uruchomienia MPI wykonano na "
        "jednym komputerze lokalnym (1 węzeł, 6 rdzeni fizycznych / 12 wątków SMT), co zostało jawnie "
        "oznaczone w metadanych i na wykresach jako pomiar lokalnej komunikacji shared-memory, a nie "
        "skalowalności wielowęzłowego klastra."
    )

    add_academic_table(
        doc,
        "Tabela 6: Wyniki skalowania silnego OpenMP oraz lokalnego MPI na zbiorze mixed_segmented.bin (N = 150 MB, W = 65536, S = 16384)",
        ["Implementacja", "p", "Mediana T_core [ms] (min–max)", "Mediana T_total [ms]", "N / T_core [GB/s]", "KW / T_core [GB/s]", "Przyspieszenie S(p)", "Efektywność E(p)"],
        [
            ["OMP (naive)", "1", "1334,81 (1316,9..1539,7)", "1399,05", "0,11", "0,45", "1,00×", "1,000"],
            ["OMP (naive)", "2", "675,15 (665,8..769,7)", "760,42", "0,22", "0,89", "1,98×", "0,989"],
            ["OMP (naive)", "4", "343,87 (336,7..355,2)", "412,40", "0,44", "1,74", "3,88×", "0,970"],
            ["**OMP (naive)**", "**6**", "**240,88 (230,1..243,7)**", "**303,24**", "**0,62**", "**2,49**", "**5,54×**", "**0,924**"],
            ["OMP (naive)", "8", "200,21 (189,6..244,8)", "277,49", "0,75", "3,00", "6,67×", "0,833"],
            ["OMP (naive)", "12", "222,45 (191,1..285,0)", "299,91", "0,67", "2,70", "6,00×", "0,500"],
            ["OMP-Incremental", "1", "655,20 (650,7..680,2)", "736,76", "0,23", "0,92", "1,00×", "1,000"],
            ["OMP-Incremental", "2", "334,48 (326,9..334,7)", "397,05", "0,45", "1,79", "1,96×", "0,979"],
            ["OMP-Incremental", "4", "177,50 (174,7..178,8)", "242,31", "0,85", "3,38", "3,69×", "0,923"],
            ["**OMP-Incremental**", "**6**", "**125,95 (120,2..172,0)**", "**200,22**", "**1,19**", "**4,76**", "**5,20×**", "**0,867**"],
            ["**OMP-Incremental**", "**8**", "**96,92 (92,5..104,5)**", "**167,47**", "**1,55**", "**6,19**", "**6,76×**", "**0,845**"],
            ["OMP-Incremental", "12", "97,39 (84,7..137,1)", "166,56", "1,54", "6,16", "6,73×", "0,561"],
            ["MPI (naive, lokalne)", "1", "1324,70 (1315,7..1366,7)", "1432,73", "0,11", "0,45", "1,00×", "1,000"],
            ["MPI (naive, lokalne)", "2", "668,77 (658,8..673,3)", "770,77", "0,22", "0,90", "1,98×", "0,990"],
            ["MPI (naive, lokalne)", "4", "342,44 (339,3..362,9)", "460,48", "0,44", "1,75", "3,87×", "0,967"],
            ["**MPI (naive, lokalne)**", "**6**", "**242,64 (232,8..297,8)**", "**358,62**", "**0,62**", "**2,47**", "**5,46×**", "**0,910**"],
            ["MPI (naive, lokalne)", "8", "183,30 (175,9..188,0)", "295,97", "0,82", "3,27", "7,23×", "0,903"],
            ["MPI-Incremental (lok.)", "1", "655,00 (652,3..657,2)", "757,73", "0,23", "0,92", "1,00×", "1,000"],
            ["MPI-Incremental (lok.)", "2", "333,77 (330,2..343,4)", "441,17", "0,45", "1,80", "1,96×", "0,981"],
            ["MPI-Incremental (lok.)", "4", "176,21 (173,6..178,6)", "288,57", "0,85", "3,40", "3,72×", "0,929"],
            ["**MPI-Incremental (lok.)**", "**6**", "**131,39 (124,2..153,7)**", "**272,35**", "**1,14**", "**4,56**", "**4,99×**", "**0,831**"],
            ["MPI-Incremental (lok.)", "8", "97,74 (92,2..152,4)", "212,59", "1,53", "6,14", "6,70×", "0,838"],
        ],
        right_align_cols=(1, 2, 3, 4, 5, 6, 7),
    )

    add_figure(
        doc,
        plots / 'speedup_efficiency_omp_mpi.png',
        "Rysunek 2: Przyspieszenie S(p) = T(1)/T(p) oraz efektywność E(p) = S(p)/p dla OpenMP i lokalnego MPI w wariantach naive i incremental.",
    )

    add_p(
        doc,
        "Analiza wyników z Tabeli 6 oraz Rysunku 2 prowadzi do następujących wniosków: "
        "(1) Do liczby p = 6 (odpowiadającej 6 fizycznym rdzeniom procesora Ryzen 5 2600) skalowanie rdzenia "
        "obliczeń jest niemal idealne — efektywność wynosi 92,4% dla OMP oraz 91,0% dla MPI w trybie naiwnym, "
        "co potwierdza skuteczność eliminacji współdzielonych liczników przez prywatne histogramy w L1 cache. "
        "(2) Przy przejściu do p = 8 (wykorzystanie wątków logicznych SMT) czas rdzenia nadal maleje (przyspieszenie "
        "rośnie do 6,67–7,23×), natomiast przy p = 12 wątkach następuje nasycenie jednostek wykonawczych rdzeni "
        "i spadek efektywności do 50–56%. "
        "(3) Czas całkowity T_total wersji MPI jest systematycznie wyższy o 45–70 ms od czasu OpenMP przy tym samym p, "
        "ponieważ w MPI proces główny musi przesłać 150 MB danych wraz z zakładkami przez bufory komunikacyjne "
        "(T_distribute ≈ 26 ms) oraz ponieść narzut uruchomienia procesów przez mpiexec."
    )

    # =========================================================================
    # 6. PORÓWNANIE TECHNOLOGII ORAZ WARIANTU NAIWNEGO I PRZYROSTOWEGO
    # =========================================================================
    doc.add_heading("6. Porównanie wszystkich technologii oraz analiza wariantu przyrostowego (zakres 2-osobowy)", level=1)
    add_p(
        doc,
        "W Tabeli 7 zestawiono wyniki wszystkich 8 zaimplementowanych wariantów na zbiorze mixed_segmented.bin "
        "(150 MB) dla czterech rozmiarów okna W ∈ {1024, 4096, 16384, 65536} przy kroku S = W/4 (75% zakładki "
        "między sąsiednimi oknami)."
    )

    add_academic_table(
        doc,
        "Tabela 7: Porównanie czasu wykonania i przepustowości wszystkich 8 implementacji w funkcji rozmiaru okna W (mixed_segmented.bin, S = W/4)",
        ["Okno W (krok S)", "Implementacja (zasoby)", "Mediana T_core [ms]", "Mediana T_total [ms]", "N / T_core [GB/s]", "KW / T_core [GB/s]", "Przyspieszenie wzgl. Ref-Naive", "Zysk Incremental vs Naive"],
        [
            ["W=1024 (S=256)", "Ref-Naive (1)", "1797,83", "2397,53", "0,08", "0,33", "1,00×", "—"],
            ["W=1024 (S=256)", "Ref-Incremental (1)", "1161,62", "1755,68", "0,13", "0,52", "1,55×", "**1,55×**"],
            ["W=1024 (S=256)", "OMP (12)", "305,75", "911,60", "0,49", "1,96", "5,88×", "—"],
            ["W=1024 (S=256)", "OMP-Incremental (12)", "226,53", "839,79", "0,66", "2,65", "7,94×", "**1,35×**"],
            ["W=1024 (S=256)", "MPI (6)", "512,68", "1268,29", "0,29", "1,17", "3,51×", "—"],
            ["W=1024 (S=256)", "MPI-Incremental (6)", "409,74", "1185,34", "0,37", "1,46", "4,39×", "**1,25×**"],
            ["W=1024 (S=256)", "CUDA (256)", "76,02", "889,20", "1,97", "7,89", "23,65×", "—"],
            ["W=1024 (S=256)", "**CUDA-Incremental (256)**", "**57,09**", "**862,61**", "**2,63**", "**10,51**", "**31,49×**", "**1,33×**"],
            ["W=4096 (S=1024)", "Ref-Naive (1)", "1418,86", "1606,16", "0,11", "0,42", "1,00×", "—"],
            ["W=4096 (S=1024)", "Ref-Incremental (1)", "769,69", "986,37", "0,19", "0,78", "1,84×", "**1,84×**"],
            ["W=4096 (S=1024)", "OMP (12)", "203,26", "397,97", "0,74", "2,95", "6,98×", "—"],
            ["W=4096 (S=1024)", "OMP-Incremental (12)", "138,65", "334,60", "1,08", "4,33", "10,23×", "**1,47×**"],
            ["W=4096 (S=1024)", "MPI (6)", "325,08", "627,06", "0,46", "1,85", "4,36×", "—"],
            ["W=4096 (S=1024)", "MPI-Incremental (6)", "198,17", "510,37", "0,76", "3,03", "7,16×", "**1,64×**"],
            ["W=4096 (S=1024)", "CUDA (256)", "33,47", "425,37", "4,48", "17,92", "42,39×", "—"],
            ["W=4096 (S=1024)", "**CUDA-Incremental (256)**", "**22,78**", "**398,77**", "**6,58**", "**26,34**", "**62,28×**", "**1,47×**"],
            ["W=16384 (S=4096)", "Ref-Naive (1)", "1336,56", "1423,24", "0,11", "0,45", "1,00×", "—"],
            ["W=16384 (S=4096)", "Ref-Incremental (1)", "673,11", "762,09", "0,22", "0,89", "1,99×", "**1,99×**"],
            ["W=16384 (S=4096)", "OMP (12)", "168,07", "270,03", "0,89", "3,57", "7,95×", "—"],
            ["W=16384 (S=4096)", "OMP-Incremental (12)", "90,58", "183,75", "1,66", "6,62", "14,76×", "**1,86×**"],
            ["W=16384 (S=4096)", "MPI (6)", "252,61", "398,96", "0,59", "2,38", "5,29×", "—"],
            ["W=16384 (S=4096)", "MPI-Incremental (6)", "171,71", "518,87", "0,87", "3,49", "7,78×", "**1,47×**"],
            ["W=16384 (S=4096)", "CUDA (256)", "22,36", "308,09", "6,71", "26,83", "59,77×", "—"],
            ["W=16384 (S=4096)", "**CUDA-Incremental (256)**", "**12,41**", "**300,13**", "**12,09**", "**48,34**", "**107,68×**", "**1,80×**"],
            ["W=65536 (S=16384)", "Ref-Naive (1)", "1300,18", "1359,41", "0,12", "0,46", "1,00×", "—"],
            ["W=65536 (S=16384)", "Ref-Incremental (1)", "666,94", "784,00", "0,22", "0,90", "1,95×", "**1,95×**"],
            ["W=65536 (S=16384)", "OMP (12)", "222,45", "299,91", "0,67", "2,70", "5,84×", "—"],
            ["W=65536 (S=16384)", "OMP-Incremental (12)", "97,39", "166,56", "1,54", "6,16", "13,35×", "**2,28×**"],
            ["W=65536 (S=16384)", "MPI (6)", "242,64", "358,62", "0,62", "2,47", "5,36×", "—"],
            ["W=65536 (S=16384)", "MPI-Incremental (6)", "131,39", "272,35", "1,14", "4,56", "9,90×", "**1,85×**"],
            ["W=65536 (S=16384)", "CUDA (256)", "20,52", "285,43", "7,31", "29,23", "63,37×", "—"],
            ["W=65536 (S=16384)", "**CUDA-Incremental (256)**", "**11,49**", "**290,30**", "**13,05**", "**52,18**", "**113,12×**", "**1,78×**"],
        ],
        right_align_cols=(2, 3, 4, 5, 6, 7),
    )

    add_figure(
        doc,
        plots / 'throughput_comparison.png',
        "Rysunek 3: Porównanie przepustowości wejściowej N / T_core [GB/s] wszystkich 8 wariantów dla okien rozłącznych (S = W) oraz nakładających się (S = W/4).",
    )
    add_figure(
        doc,
        plots / 'naive_vs_incremental_comparison.png',
        "Rysunek 4: Stosunek czasu rdzenia T_core(naive) / T_core(incremental) w funkcji rozmiaru okna W dla S = W/4 (zakres 2-osobowy).",
    )

    # =========================================================================
    # 7. ANALIZA GPU: TRANSFERY, ROZMIAR BLOKU, ROZMIAR DANYCH I OPERACJE ATOMOWE
    # =========================================================================
    doc.add_heading("7. Szczegółowa analiza wydajności GPU (CUDA)", level=1)

    doc.add_heading("7.1. Koszt transferów H2D/D2H względem obliczeń kernela", level=2)
    add_academic_table(
        doc,
        "Tabela 8: Dekompozycja czasu faz GPU na zbiorze mixed_segmented.bin (150 MB, blok 256, S = W/4)",
        ["Okno W [B]", "Liczba okien K", "H2D wall (event) [ms]", "Kernel entropii [ms]", "Kernel granic [ms]", "D2H wall (event) [ms]", "Postproc. CPU [ms]", "T_total [ms]", "Udział transferów w fazach GPU"],
        [
            ["1024", "585 934", "21,69 (19,47)", "76,01", "0,161", "1,11 (1,03)", "1,225", "889,20", "23,0%"],
            ["4096", "146 481", "23,01 (19,41)", "33,47", "0,130", "0,44 (0,37)", "0,320", "425,37", "41,1%"],
            ["16384", "36 618", "22,04 (18,57)", "22,36", "0,100", "0,28 (0,19)", "0,079", "308,09", "49,8%"],
            ["65536", "9 152", "22,94 (19,38)", "20,52", "0,135", "0,23 (0,17)", "0,023", "285,43", "**52,9%**"],
        ],
        right_align_cols=(1, 2, 3, 4, 5, 6, 7, 8),
    )

    add_figure(
        doc,
        plots / 'cuda_transfer_breakdown.png',
        "Rysunek 5: Składowe czasu wykonania na GPU (transfer H2D, kernel entropii, kernel detekcji granic, transfer D2H) w funkcji rozmiaru okna W.",
    )

    doc.add_heading("7.2. Wpływ konfiguracji bloku wątków oraz rozmiaru danych wejściowych", level=2)
    add_academic_table(
        doc,
        "Tabela 9: Wpływ liczby wątków w bloku CUDA (threads_per_block) na czas kernela [ms] oraz przepustowość logiczną [GB/s] dla W = 65536, S = 16384",
        ["Wątki w bloku", "CUDA (constant_bytes)", "CUDA (uniform_random)", "CUDA (mixed_segmented)", "CUDA-Incremental (mixed_segmented)"],
        [
            ["64", "23,80 ms (16,80 GB/s)", "13,05 ms (30,63 GB/s)", "24,45 ms (24,53 GB/s)", "**10,02 ms (59,88 GB/s)**"],
            ["128", "**22,81 ms (17,53 GB/s)**", "11,55 ms (34,61 GB/s)", "21,08 ms (28,45 GB/s)", "10,70 ms (56,06 GB/s)"],
            ["256", "23,78 ms (16,81 GB/s)", "11,09 ms (36,04 GB/s)", "20,52 ms (29,23 GB/s)", "11,49 ms (52,18 GB/s)"],
            ["512", "24,33 ms (16,43 GB/s)", "**10,77 ms (37,11 GB/s)**", "**18,83 ms (31,86 GB/s)**", "11,97 ms (50,12 GB/s)"],
            ["1024", "27,58 ms (14,50 GB/s)", "11,83 ms (33,78 GB/s)", "20,92 ms (28,67 GB/s)", "11,44 ms (52,43 GB/s)"],
        ],
        right_align_cols=(0, 1, 2, 3, 4),
    )

    add_figure(
        doc,
        plots / 'cuda_block_size_impact.png',
        "Rysunek 6: Czas wykonania kernela entropii oraz przepustowość logiczna w funkcji rozmiaru bloku wątków CUDA (64..1024).",
    )
    add_figure(
        doc,
        plots / 'gpu_datasize_scaling.png',
        "Rysunek 7: Wpływ rozmiaru pliku wejściowego N (10..180 MB) na przepustowość rdzenia N / T_core oraz czas całkowity T_total.",
    )

    add_p(
        doc,
        "Rysunek 7 ilustruje kluczowe zjawisko inżynierskie: podczas gdy sam kernel GPU (T_core) wykazuje "
        "ponad 60–110-krotne przyspieszenie względem jednowątkowego CPU i 8–15-krotne względem 12-wątkowego "
        "OpenMP, w całkowitym czasie wykonania pojedynczego procesu (T_total) dla plików 10–180 MB najszybszy "
        "okazuje się 12-wątkowy OMP-Incremental (16,4 ms dla 10 MB; 173,5 ms dla 180 MB). Wynika to ze stałego "
        "kosztu inicjalizacji kontekstu CUDA w sterowniku WDDM (T_setup ≈ 180–240 ms) oraz transferu PCIe H2D. "
        "Wersja GPU przewyższa natomiast jednowątkowy CPU w czasie całkowitym już od rozmiaru pliku N >= 25 MB."
    )

    doc.add_heading("7.3. Wpływ koncentracji bajtów na konkurencję operacji atomowych w pamięci współdzielonej", level=2)
    add_academic_table(
        doc,
        "Tabela 10: Czas kernela CUDA i przepustowość logiczna w funkcji liczby różnych symboli k w alfabecie (N = 50 MB, W = 65536, S = 16384, blok = 256)",
        ["Liczba symboli k", "Prawdop. kolizji 1/k", "H_teor [bit/B]", "CUDA (naive) T_kernel [ms]", "CUDA (naive) log. GB/s", "CUDA-Inc T_kernel [ms]", "CUDA-Inc log. GB/s", "Przyspieszenie wzgl. k=1 (naive / inc)"],
        [
            ["1 (stały bajt)", "100,00%", "0,0", "15,195", "13,15", "6,558", "30,46", "1,00× / 1,00×"],
            ["2", "50,00%", "1,0", "7,858", "25,42", "4,027", "49,60", "1,93× / 1,63×"],
            ["4", "25,00%", "2,0", "5,397", "37,02", "2,471", "80,82", "2,82× / 2,65×"],
            ["8", "12,50%", "3,0", "4,163", "47,99", "1,799", "111,05", "3,65× / 3,65×"],
            ["16", "6,25%", "4,0", "4,550", "43,90", "1,643", "121,55", "3,34× / 3,99×"],
            ["32", "3,13%", "5,0", "4,006", "49,87", "1,877", "106,40", "3,79× / 3,49×"],
            ["64", "1,56%", "6,0", "3,946", "50,62", "**1,425**", "**140,18**", "3,85× / **4,60×**"],
            ["128", "0,78%", "7,0", "**3,682**", "**54,25**", "1,550", "128,90", "**4,13×** / 4,23×"],
            ["256 (jednostajny)", "0,39%", "8,0", "3,804", "52,52", "2,200", "90,78", "3,99× / 2,98×"],
        ],
        right_align_cols=(0, 1, 2, 3, 4, 5, 6, 7),
    )

    add_figure(
        doc,
        plots / 'atomic_contention_impact.png',
        "Rysunek 8: Wpływ rozkładu danych (k = 1 vs k = 256 w funkcji W) oraz ciągłej zmiany koncentracji bajtów (k = 1..256) na przepustowość logiczną kernela CUDA.",
    )

    # =========================================================================
    # 8. DOKŁADNOŚĆ SEGMENTACJI I LOKALIZACJI ZNANYCH GRANIC
    # =========================================================================
    doc.add_heading("8. Dokładność segmentacji i lokalizacji znanych granic", level=1)
    add_academic_table(
        doc,
        "Tabela 11: Dokładność lokalizacji granic w plikach mixed_segmented.bin (2 granice) oraz multi_segmented.bin (4 granice) dla progu T = 0,1",
        ["Zbiór danych", "Okno W [B]", "Krok S [B]", "Granice rzeczywiste", "Surowe flagi okien", "Scalone zdarzenia (--events)", "Trafione / Fałszywe (FP)", "Średni błąd lokalizacji [B]", "Maks. błąd lokalizacji [B] (wzgl. S)"],
        [
            ["mixed_segmented.bin", "1024", "1024", "2", "34", "31", "2 / 29", "192 B", "256 B (0,25·S)"],
            ["mixed_segmented.bin", "1024", "256", "2", "8", "**2**", "**2 / 0**", "**64 B**", "**128 B (0,50·S)**"],
            ["mixed_segmented.bin", "4096", "1024", "2", "9", "**2**", "**2 / 0**", "192 B", "256 B (0,25·S)"],
            ["mixed_segmented.bin", "16384", "4096", "2", "9", "**2**", "**2 / 0**", "960 B", "1792 B (0,44·S)"],
            ["mixed_segmented.bin", "65536", "16384", "2", "10", "**2**", "**2 / 0**", "2240 B", "4224 B (0,26·S)"],
            ["multi_segmented.bin", "1024", "256", "4", "17", "**4**", "**4 / 0**", "**32 B**", "**128 B (0,50·S)**"],
            ["multi_segmented.bin", "4096", "4096", "4", "8", "**4**", "**4 / 0**", "1344 B", "1920 B (0,47·S)"],
            ["multi_segmented.bin", "16384", "4096", "4", "17", "**4**", "**4 / 0**", "1152 B", "3328 B (0,81·S)"],
            ["multi_segmented.bin", "65536", "16384", "4", "18", "**4**", "**4 / 0**", "5760 B", "11520 B (0,70·S)"],
        ],
        right_align_cols=(1, 2, 3, 4, 5, 7, 8),
    )

    add_figure(
        doc,
        plots / 'segmentation_accuracy.png',
        "Rysunek 9: Wyznaczony profil entropii Shannona oraz lokalizacja granic w plikach mixed_segmented.bin (3 segmenty) i multi_segmented.bin (5 segmentów).",
    )

    # =========================================================================
    # 9. WNIOSKI KOŃCOWE, REPRODUKOWALNOŚĆ I PODZIAŁ PRACY
    # =========================================================================
    doc.add_heading("9. Podsumowanie, instrukcja odtworzenia wyników i podział pracy", level=1)
    add_bullet(
        doc,
        "1. Zgodność numeryczna i poprawność: ",
        "Wszystkie cztery technologie (Reference, OpenMP, MPI, CUDA) w obu wariantach (naive i incremental) "
        "dają identyczne wyniki klasyfikacji granic (100% zgodności flag). Implementacje CPU są bitowo identyczne "
        "(max_error = 0), a maksymalna różnica numeryczna na GPU z tytułu redukcji drzewiastej wynosi 1,69 × 10⁻¹⁴ bit/bajt."
    )
    add_bullet(
        doc,
        "2. Skalowanie równoległe na CPU (OpenMP i MPI): ",
        "Prywatne histogramy wątków w OpenMP oraz podział blokowy z zakładką halo w MPI zapewniają efektywność "
        "powyżej 91% na 6 rdzeniach fizycznych (S(6) = 5,54× w OpenMP i 5,46× w MPI) oraz przyspieszenie do "
        "6,76–7,23× przy wykorzystaniu wątków SMT (p = 8)."
    )
    add_bullet(
        doc,
        "3. Akceleracja GPU i wpływ operacji atomowych: ",
        "W rdzeniu obliczeniowym (T_core) karta GeForce GTX 1660 osiąga przyspieszenie do 69,1× w trybie naive "
        "(18,83 ms) oraz do 129,8× w trybie incremental (10,02 ms) względem jednowątkowej referencji CPU. "
        "Koncentracja wszystkich bajtów w jednym koszyku (k = 1) spowalnia kernel ponad 4-krotnie względem "
        "rozkładu równomiernego na skutek serializacji operacji atomowych w pamięci współdzielonej."
    )
    add_bullet(
        doc,
        "4. Zysk z przyrostowej aktualizacji histogramu (zakres 2-osobowy): ",
        "Wariant przyrostowy (--mode incremental) skraca czas rdzenia obliczeń o 1,78–2,28× dla S = W/4 we "
        "wszystkich czterech technologiach bez jakiejkolwiek utraty dokładności."
    )

    doc.add_heading("9.1. Polecenia budowania, testowania i odtworzenia eksperymentów", level=2)
    add_code_block(
        doc,
        "cmake -S . -B build -GNinja -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=75 -DC05_REQUIRE_ALL=ON\n"
        "cmake --build build --parallel\n"
        "ctest --test-dir build --output-on-failure\n"
        "python3 scripts/benchmark_runner.py --build-dir build --datasets datasets --results results --generate-datasets\n"
        "python3 scripts/plot_entropy.py --csv results/segmentation.csv --events results/segmentation_events.csv \\\n"
        "    --ground-truth results/ground_truth_boundaries.json --output results/plots/entropy_profile_cli.png"
    )

    doc.add_heading("9.2. Podział pracy w zespole dwuosobowym", level=2)
    add_academic_table(
        doc,
        "Tabela 12: Podział zadań pomiędzy członków zespołu dwuosobowego",
        ["Członek zespołu", "Zrealizowany zakres prac"],
        [
            [
                "**Jan Wojnicki**\n(nr albumu: **147020**)",
                "• Projekt i implementacja wspólnego modułu common/ (parser CLI, walidacja ścieżek i parametrów, odczyt plików binarnych, wyznaczanie układu pełnych okien, zapis CSV).\n"
                "• Implementacja sekwencyjnej referencji w trybie naiwnym (compute_naive, src/reference.cpp) oraz zrównoleglenia OpenMP w trybie naiwnym z prywatnymi histogramami wątków (src/openmp.cpp).\n"
                "• Implementacja kernela histogram_entropy_kernel (CUDA-Naive), kernela detekcji granic boundary_flags_kernel oraz redukcji drzewiastej w pamięci współdzielonej (src/cuda_entropy.cu).\n"
                "• Opracowanie generatora deterministycznych zbiorów danych (scripts/generate_datasets.py) oraz testów poprawności referencji i GPU (tests/verify_correctness.py, tests/verify_cuda.py)."
            ],
            [
                "**Adrian Sajdak**\n(nr albumu: **146992**)",
                "• Opracowanie i implementacja rozszerzenia dla zespołu 2-osobowego: przyrostowej aktualizacji przesuwnego histogramu (--mode incremental) w wersji referencyjnej (compute_incremental), OpenMP (OMP-Incremental), MPI (MPI-Incremental) oraz CUDA (incremental_entropy_kernel z operacjami atomicSub/atomicAdd).\n"
                "• Implementacja wersji MPI (src/mpi.cpp) z podziałem blokowym po oknach, nieblokującą dystrybucją zakładki halo (MPI_Isend/MPI_Waitall/MPI_Recv) i zbieraniem wyników (MPI_Gatherv).\n"
                "• Implementacja algorytmu scalania sąsiednich przekroczeń progu w pojedyncze zdarzenia zmiany (BoundaryEvent, merge_boundaries, --events), testów MPI (tests/verify_mpi.py) i modelu hosta (tests/check_cuda_model.py).\n"
                "• Opracowanie skryptów pomiarowych i wizualizacyjnych (scripts/benchmark_runner.py, scripts/plot_results.py, scripts/plot_entropy.py)."
            ],
        ],
    )
    add_p(
        doc,
        "Obaj autorzy wspólnie przeprowadzili sesje pomiarowe, analizę wyników oraz redakcję niniejszego "
        "sprawozdania i w pełni rozumieją całość rozwiązania."
    )

    output_docx.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_docx))
    print(f"Saved DOCX report: {output_docx}")


if __name__ == '__main__':
    repo_root = Path(__file__).resolve().parents[1]
    build_report(repo_root, repo_root / 'SPRAWOZDANIE.docx')
