# ── Default remark templates per section per score band ───────────
# Score bands: "low" = 0-2, "mid" = 3, "high" = 4-5
# Each entry is one sentence used to build the full remark.

DEFAULT_REMARKS = {
    "Body Language": {
        "high": "The candidate's body language was confident and professional, reflecting a strong sense of self-assurance throughout the session.",
        "mid":  "Body language was adequate but could benefit from more deliberate posture and eye contact to project greater confidence.",
        "low":  "Body language was noticeably weak — the candidate appeared tense and uncomfortable, which significantly impacted the overall impression.",
    },
    "Communication": {
        "high": "Communication was clear, articulate and well-structured, demonstrating excellent verbal ability and confidence in expression.",
        "mid":  "Communication was satisfactory; however, the candidate should work on clarity and flow to make responses more impactful.",
        "low":  "Communication skills require significant improvement — responses lacked coherence and confidence, making it difficult to follow the candidate's thoughts.",
    },
    "Skills & Functions": {
        "high": "The candidate demonstrated strong awareness of role-specific skills and functional knowledge relevant to the position.",
        "mid":  "Functional knowledge was moderate — the candidate showed awareness of basic skills but lacked depth in specific areas.",
        "low":  "Knowledge of role-specific skills and functions was limited and needs focused preparation before the actual interview.",
    },
    "Situational Handling Aptitude": {
        "high": "Situational handling was impressive — the candidate approached hypothetical scenarios with logic, composure and practical thinking.",
        "mid":  "Situational responses were reasonable but lacked the decisiveness and analytical depth expected at this level.",
        "low":  "The candidate struggled with situational questions and needs to develop stronger problem-solving and decision-making skills.",
    },
    "Stress Handling": {
        "high": "The candidate handled stress exceptionally well, maintaining composure and clarity even under challenging follow-up questions.",
        "mid":  "Stress handling was acceptable but the candidate showed signs of discomfort under pressure — further practice is recommended.",
        "low":  "Stress handling was poor — the candidate became visibly flustered under pressure, which is a critical area requiring urgent improvement.",
    },
    "Team Work": {
        "high": "A strong team orientation was evident — the candidate demonstrated excellent collaborative thinking and peer awareness.",
        "mid":  "The candidate showed a basic understanding of teamwork but should develop stronger examples of collaborative experience.",
        "low":  "Teamwork skills appeared underdeveloped — the candidate's responses reflected an individualistic approach rather than collaborative thinking.",
    },
    "Presence of Mind": {
        "high": "Presence of mind was a standout quality — the candidate responded quickly, accurately and thoughtfully to unexpected questions.",
        "mid":  "Presence of mind was moderate — responses were adequate but occasionally slow or hesitant when faced with unexpected queries.",
        "low":  "The candidate showed poor presence of mind, frequently pausing or giving incomplete responses to spontaneous questions.",
    },
    "Awareness": {
        "high": "Awareness of current affairs, general knowledge and the broader socio-political context was excellent and clearly demonstrated.",
        "mid":  "General awareness was satisfactory but the candidate should broaden their knowledge of current events and national affairs.",
        "low":  "Awareness of current affairs and general knowledge was notably weak — this is a critical gap that must be addressed immediately.",
    },
    "Clarity of Thoughts": {
        "high": "Thoughts were expressed with exceptional clarity — the candidate structured answers logically and communicated ideas precisely.",
        "mid":  "Clarity of thought was reasonable but responses occasionally lacked structure, making arguments harder to follow.",
        "low":  "The candidate struggled to express thoughts clearly — responses were often disorganised and difficult to comprehend.",
    },
    "Integrity": {
        "high": "The candidate demonstrated strong integrity and ethical reasoning, responding honestly and thoughtfully to values-based questions.",
        "mid":  "Integrity responses were adequate but lacked depth — the candidate should reflect more deeply on ethical scenarios.",
        "low":  "Responses to integrity-based questions were weak and unconvincing — this area requires serious introspection and preparation.",
    },
}

def get_band(score):
    if score is None: return None
    if score >= 4:    return "high"
    if score >= 3:    return "mid"
    return "low"

def build_auto_remark(iv_name, scores_dict, iv_note, templates):
    """
    Build an 8-9 line professional remark from:
    - iv_name: interviewer name
    - scores_dict: {0: score, 1: score, ...} int keys
    - iv_note: short note typed by interviewer
    - templates: dict from remarks.json (or DEFAULT_REMARKS)
    """
    from database import SECTION_NAMES
    lines = []

    # Opening line — interviewer's own note
    if iv_note.strip():
        lines.append(f"As observed by the evaluator, {iv_note.strip().rstrip('.')}.")

    # One sentence per section that was scored
    for i, sec in enumerate(SECTION_NAMES):
        val  = scores_dict.get(i)
        band = get_band(val)
        if band is None:
            continue
        sec_templates = templates.get(sec, DEFAULT_REMARKS.get(sec, {}))
        sentence = sec_templates.get(band, "")
        if sentence:
            lines.append(sentence)

    # Closing advice
    scored_vals = [v for v in scores_dict.values() if v is not None]
    if scored_vals:
        avg = sum(scored_vals) / len(scored_vals)
        if avg >= 4:
            lines.append(
                "Overall, the candidate has shown commendable preparation and is well-positioned "
                "for the actual interview with continued practice."
            )
        elif avg >= 3:
            lines.append(
                "With focused preparation on the areas highlighted above, the candidate has the "
                "potential to perform strongly in the actual interview."
            )
        else:
            lines.append(
                "It is strongly recommended that the candidate undertakes 2-3 more mock interview "
                "sessions to address the identified weaknesses before appearing for the actual interview."
            )

    return " ".join(lines)
