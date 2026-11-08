"""How well do Grade Check's TAG grade rules turn TAG's own measurements into TAG's grade?

Every TAG DIG report states the centering, how many DINGS were counted, and the grade TAG gave. Feeding
the centering and DINGS into the grade rules (data/tag_calibration.json) and comparing with TAG's grade
tests the rules on their own, separately from how well the scanner measures a card.

Reads data/tag_reports.csv plus every ladder.json under data/tag_compare and data/tag_train.
Usage: .venv/bin/python scripts/grade_rules_test.py [--fit]   (--fit: refit the rules from all reports first)
"""

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.grading import standards  # noqa: E402

NUM = {"PRISTINE": 10.5, "10P": 10.5, "GEM MINT": 10, "10": 10}


def grade_num(g):
    g = str(g).upper().strip()
    if g in NUM:
        return NUM[g]
    m = re.findall(r"\d+(?:\.\d)?", g)
    return float(m[0]) if m else None


def worst_pair(s):
    n = [float(x) for x in re.findall(r"[\d.]+", s or "")]
    return max(max(n[0], n[1]), max(n[2], n[3])) if len(n) >= 4 else None


def reports():
    out = {}
    for r in csv.DictReader((ROOT / "data" / "tag_reports.csv").open()):
        g = 10.5 if r["condition"] == "PRISTINE" else grade_num(r["grade"])
        out[r["cert"]] = {"grade": g, "front": max(float(r["fL"]), float(r["fR"]), float(r["fT"]), float(r["fB"])),
                          "back": max(float(r["bL"]), float(r["bR"]), float(r["bT"]), float(r["bB"])),
                          "dings": sum(int(r[k]) for k in ("dings_corner_f", "dings_corner_b", "dings_edge_f", "dings_edge_b")),
                          "surface": int(r["dings_surface_f"]) + int(r["dings_surface_b"]),
                          "score": int(r["score"]) if r["score"] else None, "card": r.get("name", "")}
    for ladder in list((ROOT / "data" / "tag_compare").glob("*/ladder.json")) + list((ROOT / "data" / "tag_train").glob("*/ladder.json")):
        for cert, v in json.loads(ladder.read_text()).items():
            d = v.get("dings") or []
            if len(d) < 6 or not v.get("centF"):
                continue
            out[cert] = {"grade": grade_num(v["grade"]), "front": worst_pair(v["centF"]), "back": worst_pair(v["centB"]),
                         "dings": d[0] + d[1] + d[2] + d[3], "surface": d[4] + d[5], "score": v.get("score"),
                         "card": ladder.parent.name}
    return out


def predict(ladder, r):
    row, _ = standards._ladder(ladder, r["front"], r["back"], "clean", r["dings"] + r["surface"])
    return row[1] if row else 7.5


def main():
    data = reports()
    if "--fit" in sys.argv:
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "scripts" / "calibrate_tag.py")], check=True, capture_output=True)
    cal = json.loads((ROOT / "data" / "tag_calibration.json").read_text())
    ladder = [tuple(r) for r in cal["ladder"]]
    rows = [r for r in data.values() if r["grade"] is not None and r["front"] and r["back"] and r["grade"] >= 8]
    hits = near = 0
    confusion = Counter()
    for r in rows:
        p = predict(ladder, r)
        confusion[(r["grade"], p)] += 1
        hits += p == r["grade"]
        near += abs(p - r["grade"]) <= 0.5
    print(f"{len(rows)} TAG reports graded 8 or better (rules fitted from {cal['n_reports']})")
    print(f"Rules give TAG's exact grade {hits}/{len(rows)} ({hits / len(rows):.0%}), within half a grade {near}/{len(rows)} ({near / len(rows):.0%})")
    grades = sorted({g for g, _ in confusion} | {p for _, p in confusion}, reverse=True)
    print("TAG grade -> rules' grade")
    for g in grades:
        line = {p: confusion[(g, p)] for p in grades if confusion[(g, p)]}
        if line:
            print(f"  {g:>4}: {line}")


if __name__ == "__main__":
    main()
