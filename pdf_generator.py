import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table,
    TableStyle, HRFlowable, Image as RLImage
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.utils import ImageReader

# ── Colours ────────────────────────────────────────────────────────
NAVY       = colors.HexColor("#1a2f5e")
NAVY2      = colors.HexColor("#162548")
GOLD       = colors.HexColor("#c9a84c")
STEEL      = colors.HexColor("#2c4a8a")
LIGHT_GREY = colors.HexColor("#f0f3f8")
MID_GREY   = colors.HexColor("#d0d8e8")
DARK_GREY  = colors.HexColor("#6b7a99")
GREEN_BG   = colors.HexColor("#e8f5ee")
GREEN_TXT  = colors.HexColor("#1e7e44")
AMBER_BG   = colors.HexColor("#fff3e0")
AMBER_TXT  = colors.HexColor("#b45309")
WHITE      = colors.white
BLACK      = colors.HexColor("#1a1a1a")
CELL_HI    = colors.HexColor("#eef2fa")   # avg column bg

SECTIONS = [
    "Body Language",
    "Communication",
    "Skills & Functions",
    "Situational Handling Aptitude",
    "Stress Handling",
    "Team Work",
    "Presence of Mind",
    "Awareness",
    "Clarity of Thoughts",
    "Integrity",
]

PDF_DIR      = os.environ.get("PDF_DIR", "data/pdfs")
_BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH    = os.path.join(_BASE_DIR, "logo_transparent.png")
LOGO_FALLBACK= os.path.join(_BASE_DIR, "logo.png")

# ── Unique style counter — prevents ReportLab style cache collisions ─
_sc = 0
def _s(base, **kw):
    global _sc
    _sc += 1
    return ParagraphStyle(f"{base}_{_sc}", **kw)

# ── Logo helper ────────────────────────────────────────────────────
def _get_logo():
    for p in [LOGO_PATH, LOGO_FALLBACK]:
        if os.path.exists(p):
            return p
    return None

# ── Watermark ──────────────────────────────────────────────────────
def _watermark_page(canv, doc):
    logo = _get_logo()
    if not logo:
        return
    canv.saveState()
    canv.setFillAlpha(0.05)
    canv.setStrokeAlpha(0.05)
    W, H = A4
    sz = 190 * mm
    canv.drawImage(
        ImageReader(logo),
        (W - sz) / 2, (H - sz) / 2,
        sz, sz,
        mask="auto", preserveAspectRatio=True
    )
    canv.restoreState()

# ── Page border ────────────────────────────────────────────────────
def _page_border(canv, doc):
    _watermark_page(canv, doc)
    canv.saveState()
    canv.setStrokeColor(colors.HexColor("#c9a84c"))
    canv.setLineWidth(1.2)
    margin = 8 * mm
    W, H   = A4
    canv.rect(margin, margin, W - 2*margin, H - 2*margin)
    canv.restoreState()

# ══════════════════════════════════════════════════════════════════
# MAIN PDF GENERATOR
# ══════════════════════════════════════════════════════════════════
def generate_pdf(student_name, student_roll, date_str, report_data):
    os.makedirs(PDF_DIR, exist_ok=True)
    safe_roll = (student_roll
                 .replace("/", "-")
                 .replace(" ", "_")
                 .replace("|", "-"))
    output = os.path.join(PDF_DIR, f"Report_{safe_roll}.pdf")

    evaluators   = report_data["evaluators"]
    section_avgs = report_data["section_avgs"]
    grand_avg    = report_data["grand_avg"]
    n_eval       = len(evaluators)
    logo         = _get_logo()

    doc = SimpleDocTemplate(
        output, pagesize=A4,
        leftMargin=16*mm, rightMargin=16*mm,
        topMargin=14*mm,  bottomMargin=16*mm,
    )
    W     = A4[0] - 32*mm
    story = []

    # ── Helper: table-cell paragraph ──────────────────────────────
    def th(txt):
        return Paragraph(txt, _s("th",
            fontName="Helvetica-Bold", fontSize=8.5,
            textColor=WHITE, alignment=TA_CENTER, leading=11))

    def td(txt, bold=False, color=BLACK, align=TA_LEFT, size=8.5):
        return Paragraph(str(txt), _s("td",
            fontName="Helvetica-Bold" if bold else "Helvetica",
            fontSize=size, textColor=color, alignment=align))

    # ══════════════════════════════════════════════════════════════
    # SECTION 1: HEADER
    # Logo (left) | Org name + tagline + channels (centre-left) | Report type (right)
    # ══════════════════════════════════════════════════════════════
    LOGO_SZ = 24 * mm

    if logo:
        logo_cell = RLImage(logo, width=LOGO_SZ, height=LOGO_SZ)
    else:
        logo_cell = Spacer(LOGO_SZ, LOGO_SZ)

    mid_col = [
        Paragraph("PAREEKSHA GURUKUL",
            _s("org", fontName="Helvetica-Bold", fontSize=17,
               textColor=NAVY, spaceAfter=2, leading=19)),
        Paragraph("Aapki Taiyari Ka Apna Gurukul",
            _s("tag", fontName="Helvetica-Oblique", fontSize=9,
               textColor=GOLD, spaceAfter=2)),
        Paragraph("Selection Lab  |  Vishwas GS Academy",
            _s("chan", fontName="Helvetica", fontSize=8,
               textColor=STEEL, spaceAfter=0)),
    ]

    right_col = [
        Paragraph("IB SA Mock Interview",
            _s("rt1", fontName="Helvetica-Bold", fontSize=9,
               textColor=NAVY, alignment=TA_RIGHT, spaceAfter=3)),
        Paragraph("Evaluation Report",
            _s("rt2", fontName="Helvetica-Oblique", fontSize=8.5,
               textColor=STEEL, alignment=TA_RIGHT)),
    ]

    # Column widths: logo | text | report-type label
    C1 = LOGO_SZ + 5*mm
    C3 = W * 0.28
    C2 = W - C1 - C3

    hdr_tbl = Table([[logo_cell, mid_col, right_col]],
                    colWidths=[C1, C2, C3])
    hdr_tbl.setStyle(TableStyle([
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",   (0,0), (0,0),   0),
        ("RIGHTPADDING",  (0,0), (0,0),   4*mm),
        ("LEFTPADDING",   (1,0), (1,0),   0),
        ("RIGHTPADDING",  (1,0), (1,0),   4*mm),
        ("LEFTPADDING",   (2,0), (2,0),   0),
        ("RIGHTPADDING",  (2,0), (2,0),   0),
        ("TOPPADDING",    (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ]))
    story.append(hdr_tbl)
    story.append(Spacer(1, 6))

    # Gold divider — full width
    story.append(HRFlowable(width=W, thickness=2.5, color=GOLD, spaceAfter=0))
    story.append(HRFlowable(width=W, thickness=0.5, color=MID_GREY, spaceAfter=0))

    # Title bar — navy bg, white text, centred
    title_tbl = Table(
        [[Paragraph("IB SA Mock Interview Evaluation Report",
            _s("ttl", fontName="Helvetica-Bold", fontSize=12,
               textColor=WHITE, alignment=TA_CENTER))]],
        colWidths=[W], rowHeights=[24],
    )
    title_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), NAVY),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 0),
        ("RIGHTPADDING",  (0,0),(-1,-1), 0),
    ]))
    story.append(title_tbl)

    story.append(Paragraph(
        "Confidential \u2014 For Internal Use Only",
        _s("conf", fontName="Helvetica-Oblique", fontSize=6.5,
           textColor=colors.HexColor("#aaaaaa"),
           alignment=TA_CENTER, spaceBefore=3, spaceAfter=8)))

    # ══════════════════════════════════════════════════════════════
    # SECTION 2: STUDENT DETAILS — 4-column grid, left gold border
    # ══════════════════════════════════════════════════════════════
    S_LBL = _s("lbl", fontName="Helvetica-Bold", fontSize=8,   textColor=DARK_GREY)
    S_VAL = _s("val", fontName="Helvetica",       fontSize=9.5, textColor=BLACK)

    det_data = [
        [Paragraph("Student Name",       S_LBL), Paragraph(student_name, S_VAL),
         Paragraph("Roll Number",        S_LBL), Paragraph(student_roll, S_VAL)],
        [Paragraph("Date of Evaluation", S_LBL), Paragraph(date_str, S_VAL),
         Paragraph("Total Evaluators",   S_LBL), Paragraph(str(n_eval), S_VAL)],
    ]
    det_tbl = Table(det_data,
                    colWidths=[W*0.21, W*0.29, W*0.21, W*0.29])
    det_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), LIGHT_GREY),
        ("BOX",           (0,0),(-1,-1), 0.8, MID_GREY),
        ("LINEBELOW",     (0,0),(-1,0),  0.5, MID_GREY),
        ("LINEAFTER",     (1,0),(1,-1),  0.5, MID_GREY),
        ("TOPPADDING",    (0,0),(-1,-1), 7),
        ("BOTTOMPADDING", (0,0),(-1,-1), 7),
        ("LEFTPADDING",   (0,0),(-1,-1), 10),
        ("RIGHTPADDING",  (0,0),(-1,-1), 8),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS",(0,0),(-1,-1), [LIGHT_GREY, WHITE]),
    ]))

    # Wrap in gold left-border outer shell
    det_outer = Table([[det_tbl]], colWidths=[W])
    det_outer.setStyle(TableStyle([
        ("LINEBEFORE",    (0,0),(0,-1),  4, GOLD),
        ("TOPPADDING",    (0,0),(-1,-1), 0),
        ("BOTTOMPADDING", (0,0),(-1,-1), 0),
        ("LEFTPADDING",   (0,0),(-1,-1), 0),
        ("RIGHTPADDING",  (0,0),(-1,-1), 0),
    ]))
    story.append(det_outer)
    story.append(Spacer(1, 10))

    # ══════════════════════════════════════════════════════════════
    # SECTION 3: SCORE TABLE
    # Columns: Section | Interviewer(s) | Avg
    # Rows: 10 sections + header + total
    # ══════════════════════════════════════════════════════════════
    sec_col  = W * 0.33
    avg_col  = W * 0.12
    iv_col_w = (W - sec_col - avg_col) / n_eval
    col_widths = [sec_col] + [iv_col_w] * n_eval + [avg_col]

    # Verify widths sum exactly to W (floating point guard)
    total_w = sec_col + iv_col_w * n_eval + avg_col
    if abs(total_w - W) > 0.01:
        sec_col = W - iv_col_w * n_eval - avg_col
        col_widths = [sec_col] + [iv_col_w] * n_eval + [avg_col]

    hdr_row = (
        [th("Section")] +
        [th(f"{ev['iv_name']}\n(Max: 5)") for ev in evaluators] +
        [th("Avg")]
    )
    score_rows = [hdr_row]

    for i, sec in enumerate(SECTIONS):
        row = [td(sec)]
        for ev in evaluators:
            val = ev["scores_list"][i]
            row.append(td(
                "\u2014" if val is None else str(val),
                align=TA_CENTER,
                color=colors.HexColor("#bbbbbb") if val is None else BLACK,
            ))
        avg_val = section_avgs[i]
        row.append(td(
            "\u2014" if avg_val is None else str(avg_val),
            bold=True, color=NAVY, align=TA_CENTER,
        ))
        score_rows.append(row)

    # Total row
    tot_row = [Paragraph(
        "TOTAL  (Max: 50)",
        _s("totlbl", fontName="Helvetica-Bold", fontSize=9, textColor=WHITE),
    )]
    for ev in evaluators:
        tot_row.append(Paragraph(
            str(ev["total"]),
            _s("tv", fontName="Helvetica-Bold", fontSize=9,
               textColor=WHITE, alignment=TA_CENTER),
        ))
    tot_row.append(Paragraph(
        str(grand_avg),
        _s("ta", fontName="Helvetica-Bold", fontSize=10,
           textColor=GOLD, alignment=TA_CENTER),
    ))
    score_rows.append(tot_row)

    score_tbl = Table(score_rows, colWidths=col_widths)
    score_tbl.setStyle(TableStyle([
        # Header row
        ("BACKGROUND",    (0,0),  (-1,0),   NAVY),
        ("TOPPADDING",    (0,0),  (-1,0),   8),
        ("BOTTOMPADDING", (0,0),  (-1,0),   8),
        # Total row
        ("BACKGROUND",    (0,-1), (-1,-1),  STEEL),
        ("TOPPADDING",    (0,-1), (-1,-1),  8),
        ("BOTTOMPADDING", (0,-1), (-1,-1),  8),
        # All cells
        ("BOX",           (0,0),  (-1,-1),  1,   MID_GREY),
        ("INNERGRID",     (0,0),  (-1,-1),  0.4, MID_GREY),
        # Data rows
        ("TOPPADDING",    (0,1),  (-1,-2),  6),
        ("BOTTOMPADDING", (0,1),  (-1,-2),  6),
        ("LEFTPADDING",   (0,0),  (-1,-1),  8),
        ("RIGHTPADDING",  (0,0),  (-1,-1),  8),
        # Avg column highlight
        ("BACKGROUND",    (-1,1), (-1,-2),  CELL_HI),
        # Alternating row bg
        ("ROWBACKGROUNDS",(0,1),  (-1,-2),  [WHITE, LIGHT_GREY]),
        ("VALIGN",        (0,0),  (-1,-1),  "MIDDLE"),
    ]))
    story.append(score_tbl)
    story.append(Spacer(1, 11))

    # ══════════════════════════════════════════════════════════════
    # SECTION 4: VERDICT BOX
    # Score (left) | Head + body text (right)
    # ══════════════════════════════════════════════════════════════
    if grand_avg >= 40:
        v_bg, v_txt = GREEN_BG, GREEN_TXT
        v_head = "Interview Performance: GOOD"
        v_body = (
            "Your interview performance was good! Still, if you want to improve "
            "further, you can directly book another interview session through our bot."
        )
    else:
        v_bg, v_txt = AMBER_BG, AMBER_TXT
        v_head = "Improvement Recommended"
        v_body = (
            "You should take 2\u20133 more mock interview sessions through our bot "
            "before your actual interview and work on your weak areas."
        )

    v_score = Paragraph(
        f"{grand_avg}/50",
        _s("vs", fontName="Helvetica-Bold", fontSize=24,
           textColor=v_txt, alignment=TA_CENTER, leading=26))
    v_hd = Paragraph(
        v_head,
        _s("vh", fontName="Helvetica-Bold", fontSize=10,
           textColor=v_txt, spaceAfter=4))
    v_bd = Paragraph(
        v_body,
        _s("vb", fontName="Helvetica", fontSize=9,
           textColor=BLACK, leading=14))
    v_lnk = Paragraph(
        "Book your next session: http://t.me/pg_appointment_bot",
        _s("vl", fontName="Helvetica-Bold", fontSize=8.5,
           textColor=STEEL, spaceBefore=5))

    SCORE_COL = W * 0.17
    TEXT_COL  = W - SCORE_COL

    v_inner = Table(
        [[v_score, [v_hd, v_bd, v_lnk]]],
        colWidths=[SCORE_COL, TEXT_COL],
    )
    v_inner.setStyle(TableStyle([
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("LEFTPADDING",   (0,0),(-1,-1), 0),
        ("RIGHTPADDING",  (0,0),(-1,-1), 0),
        ("TOPPADDING",    (0,0),(-1,-1), 0),
        ("BOTTOMPADDING", (0,0),(-1,-1), 0),
        ("LINEAFTER",     (0,0),(0,-1),  0.8, v_txt),
        ("RIGHTPADDING",  (0,0),(0,0),   8),
        ("LEFTPADDING",   (1,0),(1,0),   10),
    ]))

    v_outer = Table([[v_inner]], colWidths=[W])
    v_outer.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), v_bg),
        ("BOX",           (0,0),(-1,-1), 1.5,  v_txt),
        ("TOPPADDING",    (0,0),(-1,-1), 10),
        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
        ("LEFTPADDING",   (0,0),(-1,-1), 10),
        ("RIGHTPADDING",  (0,0),(-1,-1), 12),
    ]))
    story.append(v_outer)
    story.append(Spacer(1, 11))

    # ══════════════════════════════════════════════════════════════
    # SECTION 5: EVALUATOR REMARKS
    # Header bar | Name col | Remark col
    # ══════════════════════════════════════════════════════════════
    rem_hdr = Table(
        [[Paragraph("Evaluator Remarks",
            _s("rh2", fontName="Helvetica-Bold", fontSize=10,
               textColor=WHITE, alignment=TA_LEFT))]],
        colWidths=[W], rowHeights=[22],
    )
    rem_hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), NAVY),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 10),
    ]))
    story.append(rem_hdr)

    NAME_COL   = W * 0.21
    REMARK_COL = W - NAME_COL

    rem_rows = []
    for ev in evaluators:
        rem_rows.append([
            Paragraph(ev["iv_name"],
                _s("rn", fontName="Helvetica-Bold", fontSize=9,
                   textColor=NAVY, leading=13)),
            Paragraph(
                f"\u201c{ev['remark']}\u201d",
                _s("rt", fontName="Helvetica-Oblique", fontSize=8.5,
                   textColor=BLACK, leading=13)),
        ])

    rem_tbl = Table(rem_rows, colWidths=[NAME_COL, REMARK_COL])
    rem_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), LIGHT_GREY),
        ("BOX",           (0,0),(-1,-1), 0.8, MID_GREY),
        ("INNERGRID",     (0,0),(-1,-1), 0.4, MID_GREY),
        ("TOPPADDING",    (0,0),(-1,-1), 9),
        ("BOTTOMPADDING", (0,0),(-1,-1), 9),
        ("LEFTPADDING",   (0,0),(-1,-1), 10),
        ("RIGHTPADDING",  (0,0),(-1,-1), 10),
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
        ("ROWBACKGROUNDS",(0,0),(-1,-1), [WHITE, LIGHT_GREY]),
        ("LINEBEFORE",    (0,0),(0,-1),  3,   GOLD),
    ]))
    story.append(rem_tbl)
    story.append(Spacer(1, 12))

    # ══════════════════════════════════════════════════════════════
    # FOOTER
    # ══════════════════════════════════════════════════════════════
    story.append(HRFlowable(width=W, thickness=1.5, color=GOLD, spaceAfter=5))

    S_FOOT = _s("ft", fontName="Helvetica", fontSize=7,
                textColor=colors.HexColor("#888888"), alignment=TA_CENTER)
    S_FOOT2 = _s("ft2", fontName="Helvetica-Oblique", fontSize=6.5,
                 textColor=colors.HexColor("#aaaaaa"), alignment=TA_CENTER)

    story.append(Paragraph(
        "Report generated by Pareeksha Gurukul  \u2022  Selection Lab  \u2022  Vishwas GS Academy",
        S_FOOT,
    ))
    story.append(Spacer(1, 2))
    story.append(Paragraph(
        "This report is confidential and intended solely for the student\u2019s improvement.",
        S_FOOT2,
    ))

    doc.build(story, onFirstPage=_page_border, onLaterPages=_page_border)
    return output
