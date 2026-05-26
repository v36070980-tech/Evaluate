import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# ── Colours ───────────────────────────────────────────────────────
NAVY       = colors.HexColor("#1a2f5e")
GOLD       = colors.HexColor("#c9a84c")
STEEL      = colors.HexColor("#2c4a8a")
LIGHT_GREY = colors.HexColor("#f0f3f8")
MID_GREY   = colors.HexColor("#d0d8e8")
GREEN_BG   = colors.HexColor("#e8f5ee")
GREEN_TXT  = colors.HexColor("#1e7e44")
AMBER_BG   = colors.HexColor("#fff3e0")
AMBER_TXT  = colors.HexColor("#b45309")
WHITE      = colors.white
BLACK      = colors.HexColor("#1a1a1a")

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

PDF_DIR = os.environ.get("PDF_DIR", "data/pdfs")

# BUG FIX 6: Use a counter for unique style names to avoid ReportLab style cache collisions
_style_counter = 0
def _s(base, **kw):
    global _style_counter
    _style_counter += 1
    return ParagraphStyle(f"{base}_{_style_counter}", **kw)

def generate_pdf(student_name, student_roll, date_str, report_data):
    """Generate PDF and return file path."""
    os.makedirs(PDF_DIR, exist_ok=True)
    safe_roll = student_roll.replace("/", "-").replace(" ", "_").replace("|", "-")
    output    = os.path.join(PDF_DIR, f"Report_{safe_roll}.pdf")

    evaluators   = report_data["evaluators"]
    section_avgs = report_data["section_avgs"]
    grand_avg    = report_data["grand_avg"]
    n_eval       = len(evaluators)

    doc = SimpleDocTemplate(
        output, pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=14*mm,  bottomMargin=14*mm,
    )
    W     = A4[0] - 36*mm
    story = []

    # ── Reusable style helpers ────────────────────────────────────
    S_ORG   = _s("org",   fontName="Helvetica-Bold",    fontSize=18, textColor=NAVY,  alignment=TA_CENTER, spaceAfter=2)
    S_TAG   = _s("tag",   fontName="Helvetica-Oblique", fontSize=9,  textColor=GOLD,  alignment=TA_CENTER, spaceAfter=2)
    S_CHAN  = _s("chan",  fontName="Helvetica",          fontSize=8,  textColor=STEEL, alignment=TA_CENTER, spaceAfter=6)
    S_TITLE = _s("title", fontName="Helvetica-Bold",    fontSize=13, textColor=WHITE, alignment=TA_CENTER)
    S_CONF  = _s("conf",  fontName="Helvetica-Oblique", fontSize=7,
                 textColor=colors.HexColor("#aaaaaa"), alignment=TA_CENTER, spaceAfter=10)
    S_LBL   = _s("lbl",  fontName="Helvetica-Bold",    fontSize=9,  textColor=NAVY)
    S_VAL   = _s("val",  fontName="Helvetica",          fontSize=9,  textColor=BLACK)
    S_LINK  = _s("link", fontName="Helvetica-Bold",     fontSize=9,  textColor=STEEL, alignment=TA_CENTER)
    S_RH    = _s("rh",   fontName="Helvetica-Bold",     fontSize=9,  textColor=NAVY,  spaceAfter=2)
    S_REM   = _s("rem",  fontName="Helvetica-Oblique",  fontSize=8.5,textColor=BLACK, leading=13, spaceAfter=8)
    S_FOOT  = _s("foot", fontName="Helvetica",          fontSize=7,
                 textColor=colors.HexColor("#888888"), alignment=TA_CENTER)

    def th(txt):
        return Paragraph(txt, _s("th", fontName="Helvetica-Bold", fontSize=8.5,
                                  textColor=WHITE, alignment=TA_CENTER))

    def td(txt, bold=False, color=BLACK, align=TA_LEFT):
        return Paragraph(str(txt), _s("td", fontName="Helvetica-Bold" if bold else "Helvetica",
                                       fontSize=8.5, textColor=color, alignment=align))

    # ── Header ────────────────────────────────────────────────────
    story.append(Paragraph("PAREEKSHA GURUKUL", S_ORG))
    story.append(Paragraph("Aapki Taiyari Ka Apna Gurukul", S_TAG))
    story.append(Paragraph("Selection Lab  |  Vishwas GS Academy", S_CHAN))
    story.append(HRFlowable(width=W, thickness=2, color=GOLD, spaceAfter=8))

    title_tbl = Table([[Paragraph("IB SA Mock Interview Evaluation Report", S_TITLE)]],
                       colWidths=[W], rowHeights=[24])
    title_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), NAVY),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
    ]))
    story.append(title_tbl)
    story.append(Paragraph("Confidential — For Internal Use Only", S_CONF))

    # ── Student details ───────────────────────────────────────────
    det_data = [
        [Paragraph("Student Name",       S_LBL), Paragraph(student_name, S_VAL),
         Paragraph("Roll Number",        S_LBL), Paragraph(student_roll, S_VAL)],
        [Paragraph("Date of Evaluation", S_LBL), Paragraph(date_str, S_VAL),
         Paragraph("Total Evaluators",   S_LBL), Paragraph(str(n_eval), S_VAL)],
    ]
    det_tbl = Table(det_data, colWidths=[W*0.22, W*0.28, W*0.22, W*0.28])
    det_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), LIGHT_GREY),
        ("BOX",           (0,0),(-1,-1), 1,   MID_GREY),
        ("INNERGRID",     (0,0),(-1,-1), 0.5, MID_GREY),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ("ROWBACKGROUNDS",(0,0),(-1,-1), [LIGHT_GREY, WHITE]),
    ]))
    story.append(det_tbl)
    story.append(Spacer(1, 10))

    # ── Score table ───────────────────────────────────────────────
    iv_col_w   = (W - W*0.36 - W*0.12) / n_eval
    col_widths = [W*0.36] + [iv_col_w] * n_eval + [W*0.12]

    hdr        = [th("Section (Max: 5)")] + [th(ev["iv_name"]) for ev in evaluators] + [th("Avg")]
    score_rows = [hdr]

    for i, sec in enumerate(SECTIONS):
        row = [td(sec)]
        for ev in evaluators:
            val = ev["scores_list"][i]
            row.append(td("—" if val is None else str(val),
                          align=TA_CENTER,
                          color=colors.HexColor("#999999") if val is None else BLACK))
        avg_val = section_avgs[i]
        row.append(td("—" if avg_val is None else str(avg_val),
                      bold=True, color=NAVY, align=TA_CENTER))
        score_rows.append(row)

    # Total row
    tot_row = [Paragraph("TOTAL  (Max: 50)",
                          _s("tots", fontName="Helvetica-Bold", fontSize=9, textColor=WHITE))]
    for ev in evaluators:
        tot_row.append(Paragraph(str(ev["total"]),
                                  _s("tv", fontName="Helvetica-Bold", fontSize=9,
                                     textColor=WHITE, alignment=TA_CENTER)))
    tot_row.append(Paragraph(str(grand_avg),
                              _s("ta", fontName="Helvetica-Bold", fontSize=9,
                                 textColor=GOLD, alignment=TA_CENTER)))
    score_rows.append(tot_row)

    score_tbl = Table(score_rows, colWidths=col_widths)
    score_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),   NAVY),
        ("TOPPADDING",    (0,0), (-1,0),   7),
        ("BOTTOMPADDING", (0,0), (-1,0),   7),
        ("BACKGROUND",    (0,-1),(-1,-1),  STEEL),
        ("TOPPADDING",    (0,-1),(-1,-1),  7),
        ("BOTTOMPADDING", (0,-1),(-1,-1),  7),
        ("BOX",           (0,0), (-1,-1),  1,   MID_GREY),
        ("INNERGRID",     (0,0), (-1,-1),  0.4, MID_GREY),
        ("TOPPADDING",    (0,1), (-1,-2),  5),
        ("BOTTOMPADDING", (0,1), (-1,-2),  5),
        ("LEFTPADDING",   (0,0), (-1,-1),  8),
        ("RIGHTPADDING",  (0,0), (-1,-1),  8),
        ("BACKGROUND",    (-1,1),(-1,-2),  colors.HexColor("#eef2fa")),
        ("ROWBACKGROUNDS",(0,1), (-1,-2),  [WHITE, LIGHT_GREY]),
        ("VALIGN",        (0,0), (-1,-1),  "MIDDLE"),
    ]))
    story.append(score_tbl)
    story.append(Spacer(1, 12))

    # ── Verdict ───────────────────────────────────────────────────
    if grand_avg >= 40:
        v_bg, v_txt = GREEN_BG, GREEN_TXT
        v_head = "Interview Performance: GOOD"
        v_body = ("Your interview performance was good! Still, if you want to improve further, "
                  "you can directly book another interview session through our bot.")
    else:
        v_bg, v_txt = AMBER_BG, AMBER_TXT
        v_head = "Improvement Recommended"
        v_body = ("You should take 2–3 more mock interview sessions through our bot before "
                  "your actual interview and work on your weak areas.")

    v_score = Paragraph(f"{grand_avg}/50",
                         _s("vscore", fontName="Helvetica-Bold", fontSize=22,
                            textColor=v_txt, alignment=TA_CENTER))
    v_out   = Paragraph("out of 50",
                         _s("vout", fontName="Helvetica", fontSize=8,
                            textColor=v_txt, alignment=TA_CENTER))
    v_hd    = Paragraph(v_head, _s("vhd", fontName="Helvetica-Bold", fontSize=10, textColor=v_txt))
    v_bd    = Paragraph(v_body, _s("vbd", fontName="Helvetica", fontSize=9, textColor=BLACK, leading=14))

    v_inner = Table([[[v_score, v_out], [v_hd, Spacer(1, 4), v_bd]]],
                     colWidths=[W*0.18, W*0.82])
    v_inner.setStyle(TableStyle([
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("LEFTPADDING",   (0,0),(-1,-1), 0),
        ("RIGHTPADDING",  (0,0),(-1,-1), 0),
        ("TOPPADDING",    (0,0),(-1,-1), 0),
        ("BOTTOMPADDING", (0,0),(-1,-1), 0),
    ]))
    v_outer = Table([[v_inner]], colWidths=[W])
    v_outer.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), v_bg),
        ("BOX",           (0,0),(-1,-1), 1.5, v_txt),
        ("TOPPADDING",    (0,0),(-1,-1), 10),
        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
        ("LEFTPADDING",   (0,0),(-1,-1), 12),
        ("RIGHTPADDING",  (0,0),(-1,-1), 12),
    ]))
    story.append(v_outer)
    story.append(Spacer(1, 6))
    story.append(Paragraph("Book Your Next Session: http://t.me/pg_appointment_bot", S_LINK))
    story.append(Spacer(1, 12))

    # ── Remarks ───────────────────────────────────────────────────
    rem_hdr = Table(
        [[Paragraph("Evaluator Remarks",
                     _s("rh2", fontName="Helvetica-Bold", fontSize=10, textColor=WHITE))]],
        colWidths=[W], rowHeights=[20]
    )
    rem_hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), NAVY),
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("LEFTPADDING",   (0,0),(-1,-1), 10),
    ]))
    story.append(rem_hdr)

    rem_rows = [
        [Paragraph(ev["iv_name"], S_RH),
         Paragraph(f'"{ev["remark"]}"', S_REM)]
        for ev in evaluators
    ]
    rem_tbl = Table(rem_rows, colWidths=[W*0.22, W*0.78])
    rem_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), LIGHT_GREY),
        ("BOX",           (0,0),(-1,-1), 0.8, MID_GREY),
        ("INNERGRID",     (0,0),(-1,-1), 0.4, MID_GREY),
        ("TOPPADDING",    (0,0),(-1,-1), 8),
        ("BOTTOMPADDING", (0,0),(-1,-1), 8),
        ("LEFTPADDING",   (0,0),(-1,-1), 10),
        ("RIGHTPADDING",  (0,0),(-1,-1), 10),
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
        ("ROWBACKGROUNDS",(0,0),(-1,-1), [WHITE, LIGHT_GREY]),
    ]))
    story.append(rem_tbl)
    story.append(Spacer(1, 14))

    # ── Footer ────────────────────────────────────────────────────
    story.append(HRFlowable(width=W, thickness=1, color=GOLD, spaceAfter=5))
    story.append(Paragraph(
        "Report generated by Pareeksha Gurukul  |  Selection Lab  |  Vishwas GS Academy", S_FOOT))
    story.append(Paragraph(
        "This report is confidential and intended solely for the student's improvement.", S_FOOT))

    doc.build(story)
    return output
