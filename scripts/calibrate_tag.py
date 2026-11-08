#!/usr/bin/env python3
"""Fit TAG's grade ladder from public TAG DIG reports.

Reads data/tag_reports.csv (one row per TAG report: score, grade, the 8 centering numbers, DINGS counts)
and writes data/tag_calibration.json, which src/grading/standards.py uses for TAG estimates.

For each grade it records the worst centering TAG accepted (front and back) and how many corner/edge
DINGS it tolerated, using the 90th percentile so one odd report doesn't loosen a grade.
Run again whenever more reports are added:  .venv/bin/python scripts/calibrate_tag.py
"""

import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC, OUT = ROOT / "data" / "tag_reports.csv", ROOT / "data" / "tag_calibration.json"
LADDER = [  # (label shown, numeric grade, how it's named in reports)
    ("Pristine 10", 10.5, "PRISTINE"),
    ("Gem Mint 10", 10, "GEM MINT"),
    ("Mint 9", 9, "9"),
    ("NM-MT+ 8.5", 8.5, "8.5"),
    ("NM-MT 8", 8, "8"),
]


def worst(a, b):
    return max(float(a), float(b))


def report_rows():
    """Every TAG report we have: data/tag_reports.csv plus the copies saved by the harvests (ladder.json files).
    Each row: grade key (as in LADDER), worst off-centre % front and back, corner+edge DINGS, surface DINGS,
    score and which card it is."""
    import re
    rows = []
    for r in csv.DictReader(SRC.open()):
        key = r["condition"] if r["condition"] in ("PRISTINE", "GEM MINT") else r["grade"]
        rows.append({"key": key, "card": r.get("name") or r["cert"], "cert": r["cert"],
                     "front": max(worst(r["fL"], r["fR"]), worst(r["fT"], r["fB"])),
                     "back": max(worst(r["bL"], r["bR"]), worst(r["bT"], r["bB"])),
                     "dings": sum(int(r[k]) for k in ("dings_corner_f", "dings_corner_b", "dings_edge_f", "dings_edge_b")),
                     "surface": int(r["dings_surface_f"]) + int(r["dings_surface_b"]),
                     "score": int(r["score"]) if r["score"] else None})
    seen = {r["cert"] for r in rows}
    pair = lambda t: (lambda n: max(max(n[0], n[1]), max(n[2], n[3])) if len(n) >= 4 else None)([float(x) for x in re.findall(r"[\d.]+", t or "")])
    for ladder in sorted((ROOT / "data" / "tag_compare").glob("*/ladder.json")) + sorted((ROOT / "data" / "tag_train").glob("*/ladder.json")):
        for cert, v in json.loads(ladder.read_text()).items():
            d = v.get("dings") or []
            if cert in seen or len(d) < 6 or not v.get("centF") or not v.get("centB"):
                continue
            g = str(v.get("grade"))
            key = {"10P": "PRISTINE", "10": "GEM MINT"}.get(g, g)
            f, b = pair(v["centF"]), pair(v["centB"])
            if f is None or b is None:
                continue
            seen.add(cert)
            rows.append({"key": key, "card": ladder.parent.name, "cert": cert, "front": f, "back": b,
                         "dings": d[0] + d[1] + d[2] + d[3], "surface": d[4] + d[5], "score": v.get("score")})
    return rows


def fit(rows):
    groups = {}
    for r in rows:
        groups.setdefault(r["key"], []).append(r)
    ladder, prev = [], None
    for label, value, key in LADDER:
        g = groups.get(key, [])
        if len(g) < 3:
            continue
        f = np.percentile([x["front"] for x in g], 90)
        b = np.percentile([x["back"] for x in g], 90)
        d = int(np.ceil(np.percentile([x["dings"] for x in g], 90)))
        scores = [x["score"] for x in g if x["score"]]
        lo = min(scores) if scores else (990 if value > 10 else 950)
        hi = max(scores) if scores else 1000
        if value > 10:
            lo, hi = 990, 1000
        # a lower grade can never be stricter than the one above it
        if prev:
            f, b, d = max(f, prev[2]), max(b, prev[3]), max(d, prev[5])
        row = [label, value, round(float(f) + 0.5, 1), round(float(b) + 0.5, 1), [int(lo), int(hi)], d]
        ladder.append(row)
        prev = row
    return ladder, {k: len(v) for k, v in groups.items()}


def main():
    rows = report_rows()
    ladder, bands = fit(rows)
    out = {
        "n_reports": len(rows),
        "ladder": ladder,
        "note": "front/back = worst off-centre % accepted (e.g. 55.5 means 55.5/44.5); last field = corner+edge DINGS tolerated",
        "bands": bands,
    }
    OUT.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
