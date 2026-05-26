import json
import os
from datetime import datetime, timedelta

DB_PATH      = os.environ.get("DB_PATH", "data/db.json")
CACHE_PATH   = os.environ.get("CACHE_PATH", "data/recent.json")

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
        for path in [DB_PATH, CACHE_PATH]:
            d = os.path.dirname(path)
            if d:
                os.makedirs(d, exist_ok=True)
            if not os.path.exists(path):
                with open(path, "w") as f:
                    json.dump({} if path == DB_PATH else [], f)

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

    def save_report(self, roll, name, date_str, iv_key, iv_name, scores, remark):
        data = self._read()
        key  = roll.strip().upper()
        if key not in data:
            data[key] = {"name": name, "roll": roll, "date": date_str, "reports": {}}
        scores_clean = {str(i): v for i, v in scores.items() if v is not None}
        data[key]["reports"][iv_key] = {
            "iv_name": iv_name,
            "scores":  scores_clean,
            "remark":  remark,
            "total":   sum(scores_clean.values()),
        }
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

    # ── 20-minute Recent Student Cache ────────────────────────────
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
        """Add/refresh a student in the 20-min cache."""
        cache = self._read_cache()
        now   = datetime.now().isoformat()
        key   = roll.strip().upper()
        # Remove if already present (refresh timestamp)
        cache = [e for e in cache if e["roll"].upper() != key]
        cache.append({"name": name, "roll": roll, "added_at": now})
        self._write_cache(cache)

    def get_recent_students(self, minutes=20):
        """Return students added within the last N minutes, unexpired only."""
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
                    changed = True   # expired entry
            except Exception:
                changed = True
        if changed:
            # Rewrite cache without expired entries
            now = datetime.now().isoformat()
            self._write_cache([
                {"name": e["name"], "roll": e["roll"], "added_at": e["added_at"]}
                for e in cache
                if datetime.fromisoformat(e.get("added_at", "2000-01-01")) >= cutoff
            ])
        return valid

    def remove_recent_student(self, roll):
        """Remove student from cache once final report is generated."""
        cache = self._read_cache()
        key   = roll.strip().upper()
        cache = [e for e in cache if e["roll"].upper() != key]
        self._write_cache(cache)

db = Database()
