import json
import os
import zipfile
from datetime import datetime, timedelta

DB_PATH    = os.environ.get("DB_PATH",    "data/db.json")
CACHE_PATH = os.environ.get("CACHE_PATH", "data/recent.json")
REM_PATH   = os.environ.get("REM_PATH",   "data/remarks.json")
PDF_DIR    = os.environ.get("PDF_DIR",    "data/pdfs")

SECTION_NAMES = [
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
        for path in [DB_PATH, CACHE_PATH, REM_PATH]:
            d = os.path.dirname(path)
            if d:
                os.makedirs(d, exist_ok=True)
            if not os.path.exists(path):
                default = [] if path == CACHE_PATH else {}
                with open(path, "w") as f:
                    json.dump(default, f)
        # Seed default remark templates if remarks.json is empty
        if os.path.getsize(REM_PATH) <= 2:
            from remarks import DEFAULT_REMARKS
            with open(REM_PATH, "w") as f:
                json.dump(DEFAULT_REMARKS, f, indent=2)

    # ── Core DB ──────────────────────────────────────────────────
    def _read(self):
        try:
            with open(DB_PATH, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write(self, data):
        with open(DB_PATH, "w") as f:
            json.dump(data, f, indent=2)

    def _read_remarks(self):
        try:
            with open(REM_PATH, "r") as f:
                return json.load(f)
        except Exception:
            from remarks import DEFAULT_REMARKS
            return DEFAULT_REMARKS

    # ── Save / retrieve reports ───────────────────────────────────
    def save_report(self, roll, name, date_str, iv_key, iv_name, scores, remark):
        data = self._read()
        key  = roll.strip().upper()
        if key not in data:
            data[key] = {
                "name":       name,
                "roll":       roll,
                "date":       date_str,
                "reports":    {},
                "generated":  False,
                "gen_date":   None,
            }
        scores_clean = {str(i): v for i, v in scores.items() if v is not None}
        data[key]["reports"][iv_key] = {
            "iv_name": iv_name,
            "scores":  scores_clean,
            "remark":  remark,
            "total":   sum(scores_clean.values()),
        }
        self._write(data)

    def mark_generated(self, roll):
        """Mark report as fully generated (for manager download tracking)."""
        data = self._read()
        key  = roll.strip().upper()
        if key in data:
            data[key]["generated"] = True
            data[key]["gen_date"]  = datetime.now().strftime("%d %b %Y")
            self._write(data)

    def get_reports(self, roll):
        data = self._read()
        key  = roll.strip().upper()
        if key not in data:
            return []
        return list(data[key]["reports"].values())

    def compile_report(self, roll):
        data = self._read()
        key  = roll.strip().upper()
        if key not in data:
            return None
        record  = data[key]
        reports = record["reports"]
        if not reports:
            return None

        evaluators = []
        for iv_key, rep in reports.items():
            sc_dict     = rep["scores"]
            scores_list = [sc_dict.get(str(i)) for i in range(10)]
            evaluators.append({
                "iv_name":     rep["iv_name"],
                "scores_list": scores_list,
                "total":       rep["total"],
                "remark":      rep["remark"],
            })

        section_avgs = []
        for i in range(10):
            vals = [ev["scores_list"][i] for ev in evaluators if ev["scores_list"][i] is not None]
            section_avgs.append(round(sum(vals) / len(vals), 1) if vals else None)

        totals    = [ev["total"] for ev in evaluators]
        grand_avg = round(sum(totals) / len(totals), 1)

        return {
            "student_name": record["name"],
            "roll":         record["roll"],
            "date":         record["date"],
            "evaluators":   evaluators,
            "section_avgs": section_avgs,
            "grand_avg":    grand_avg,
        }

    def search_student(self, query_text):
        data    = self._read()
        q       = query_text.strip().lower()
        results = []
        for key, record in data.items():
            if q in record["name"].lower() or q in record["roll"].lower():
                results.append({"name": record["name"], "roll": record["roll"]})
        return results

    # ── Manager: last / today / all reports ──────────────────────
    def get_last_report(self):
        """Return the most recently generated report's roll number."""
        data = self._read()
        generated = [
            (k, v) for k, v in data.items()
            if v.get("generated") and v.get("gen_date")
        ]
        if not generated:
            return None
        # Sort by gen_date — use date string comparison (format: "26 May 2026")
        try:
            generated.sort(
                key=lambda x: datetime.strptime(x[1]["gen_date"], "%d %b %Y"),
                reverse=True
            )
        except Exception:
            pass
        return generated[0][1]["roll"]

    def get_today_reports(self):
        """Return list of rolls generated today."""
        data    = self._read()
        today   = datetime.now().strftime("%d %b %Y")
        results = []
        for k, v in data.items():
            if v.get("generated") and v.get("gen_date") == today:
                results.append(v["roll"])
        return results

    def get_all_reports(self):
        """Return list of all generated rolls."""
        data = self._read()
        return [v["roll"] for v in data.values() if v.get("generated")]

    def build_all_zip(self):
        """Build a ZIP of all generated PDFs. Returns zip path."""
        from pdf_generator import generate_pdf
        rolls    = self.get_all_reports()
        zip_path = os.path.join(PDF_DIR, "All_Reports.zip")
        os.makedirs(PDF_DIR, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for roll in rolls:
                report_data = self.compile_report(roll)
                if not report_data:
                    continue
                pdf_path = generate_pdf(
                    report_data["student_name"],
                    roll,
                    report_data["date"],
                    report_data,
                )
                safe = roll.replace("/", "-").replace(" ", "_")
                zf.write(pdf_path, f"Report_{safe}.pdf")
        return zip_path

    # ── Auto-remark builder ───────────────────────────────────────
    def build_remark(self, scores_dict, iv_note):
        """Build auto remark from scores + interviewer short note."""
        from remarks import build_auto_remark
        templates = self._read_remarks()
        return build_auto_remark("", scores_dict, iv_note, templates)

    # ── 20-min Recent Student Cache ───────────────────────────────
    def _read_cache(self):
        try:
            with open(CACHE_PATH, "r") as f:
                return json.load(f)
        except Exception:
            return []

    def _write_cache(self, data):
        with open(CACHE_PATH, "w") as f:
            json.dump(data, f, indent=2)

    def add_recent_student(self, name, roll):
        cache = self._read_cache()
        key   = roll.strip().upper()
        cache = [e for e in cache if e["roll"].upper() != key]
        cache.append({"name": name, "roll": roll, "added_at": datetime.now().isoformat()})
        self._write_cache(cache)

    def get_recent_students(self, minutes=20):
        cache   = self._read_cache()
        cutoff  = datetime.now() - timedelta(minutes=minutes)
        valid   = []
        changed = False
        for entry in cache:
            try:
                added = datetime.fromisoformat(entry["added_at"])
                if added >= cutoff:
                    valid.append({"name": entry["name"], "roll": entry["roll"]})
                else:
                    changed = True
            except Exception:
                changed = True
        if changed:
            self._write_cache([
                e for e in cache
                if datetime.fromisoformat(e.get("added_at", "2000-01-01")) >= cutoff
            ])
        return valid

    def remove_recent_student(self, roll):
        cache = self._read_cache()
        key   = roll.strip().upper()
        cache = [e for e in cache if e["roll"].upper() != key]
        self._write_cache(cache)

db = Database()
