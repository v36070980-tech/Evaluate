import json
import os
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "data/db.json")

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

class Database:
    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        if not os.path.exists(DB_PATH):
            self._write({})

    def _read(self):
        try:
            with open(DB_PATH, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write(self, data):
        with open(DB_PATH, "w") as f:
            json.dump(data, f, indent=2)

    def save_report(self, roll, name, date_str, iv_key, iv_name, scores, remark):
        """Save one interviewer's report for a student."""
        data = self._read()
        key  = roll.strip().upper()
        if key not in data:
            data[key] = {
                "name":      name,
                "roll":      roll,
                "date":      date_str,
                "reports":   {}
            }
        # scores: dict with int keys (json stores as str) → convert
        scores_clean = {str(i): v for i, v in scores.items() if v is not None}
        data[key]["reports"][iv_key] = {
            "iv_name": iv_name,
            "scores":  scores_clean,
            "remark":  remark,
            "total":   sum(scores_clean.values()),
        }
        self._write(data)

    def get_reports(self, roll):
        """Return list of submitted reports for a student."""
        data = self._read()
        key  = roll.strip().upper()
        if key not in data:
            return []
        return list(data[key]["reports"].values())

    def compile_report(self, roll):
        """Compile final averaged report data for PDF generation."""
        data = self._read()
        key  = roll.strip().upper()
        if key not in data:
            return None

        record  = data[key]
        reports = record["reports"]
        if not reports:
            return None

        evaluators = []   # list of {iv_name, scores_list, total, remark}
        for iv_key, rep in reports.items():
            sc_dict = rep["scores"]  # {"0": 4, "2": 3, ...} str keys
            scores_list = [sc_dict.get(str(i)) for i in range(10)]  # None if skipped
            evaluators.append({
                "iv_name":     rep["iv_name"],
                "scores_list": scores_list,
                "total":       rep["total"],
                "remark":      rep["remark"],
            })

        # Section averages (only over interviewers who scored that section)
        section_avgs = []
        for i in range(10):
            vals = [ev["scores_list"][i] for ev in evaluators if ev["scores_list"][i] is not None]
            section_avgs.append(round(sum(vals)/len(vals), 1) if vals else None)

        totals = [ev["total"] for ev in evaluators]
        grand_avg = round(sum(totals)/len(totals), 1)

        return {
            "student_name":  record["name"],
            "roll":          record["roll"],
            "date":          record["date"],
            "evaluators":    evaluators,
            "section_avgs":  section_avgs,
            "grand_avg":     grand_avg,
        }

    def search_student(self, query_text):
        """Search by name or roll number. Returns list of {name, roll}."""
        data    = self._read()
        q       = query_text.strip().lower()
        results = []
        for key, record in data.items():
            if (q in record["name"].lower() or
                q in record["roll"].lower()):
                results.append({"name": record["name"], "roll": record["roll"]})
        return results

db = Database()
