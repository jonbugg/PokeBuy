"""Turn measurements and findings into expected grades and grade odds per grading company.

PSA and CGC centering limits are from their official grading-scale pages (read 2026-11-07).
TAG doesn't publish limits; data/tag_calibration.json (scripts/calibrate_tag.py) is fitted from public
TAG DIG reports: per grade, the worst centering TAG accepted and how many corner/edge DINGS it tolerated.
Without that file a provisional TAG ladder is used.

Odds come from re-running the estimate many times with the uncertainty a flatbed scan really has:
centering moves a little between scans, and borderline findings may or may not count with a grader.
"""

import json
from pathlib import Path

import numpy as np

CALIBRATION_PATH = Path(__file__).resolve().parents[2] / "data" / "tag_calibration.json"
CENTERING_WOBBLE = 1.0  # points a rescan can move; used for the cautious "could be" grade
SIGMA_FRONT, SIGMA_BACK = 0.6, 0.8  # measured scan-to-scan spread (front border is crisper than the back's)
P_RED_COUNTS, P_YELLOW_COUNTS = 0.9, 0.5  # chance a grader counts a red / yellow finding against the card

# (label, numeric grade, max front off-centre %, max back off-centre %) — "55" means 55/45 or better.
PSA = [
    ("10", 10, 55, 75),   # "approximately 55/45 to 60/40 ... and 75/25 on the reverse"
    ("9", 9, 60, 90),     # "60/40 to 65/35 or better on the front and 90/10 or better on the reverse"
    ("8", 8, 65, 90),
    ("7", 7, 70, 90),
]
CGC = [
    ("Pristine 10", 10.5, 50.5, 55),  # "The centering is 50/50"; back not stated, 55/45 assumed
    ("Gem Mint 10", 10, 55, 75),      # "not to exceed approximately 55/45 ... reverse ... 75/25"
    ("9", 9, 60, 90),                 # CGC states these for sports/non-sports cards only
    ("8", 8, 65, 90),
    ("7", 7, 70, 90),
]
# TAG rows also carry (score range) and max corner+edge DINGS.
TAG_PROVISIONAL = [
    ("Pristine 10", 10.5, 51.5, 51.5, (990, 1000), 0),
    ("Gem Mint 10", 10, 55, 55, (950, 989), 1),
    ("Mint 9", 9, 57, 61, (900, 949), 3),
    ("NM-MT+ 8.5", 8.5, 58, 62, (850, 899), 5),
    ("NM-MT 8", 8, 60, 65, (800, 849), 6),
]

DEFECT_LEVELS = ["clean", "minor", "moderate", "heavy"]
MAX_GRADE_FOR_LEVEL = {"clean": 10.5, "minor": 9, "moderate": 8, "heavy": 7, "unknown": 10.5}


def _counted(findings):
    """Findings that count: everything except yellows the 180° scan cleared (likely dust)."""
    return [f for f in findings if not (f.get("cleared") or (f["severity"] == "yellow" and f.get("both") is False))]


def defect_level(front, back, extra_findings=()):
    usable = [m for m in (front, back) if m and m.get("edges_reliable")]
    if not usable:
        return "unknown", {"red": 0, "yellow": 0, "likely_dust": 0}
    findings = [f for m in usable for f in m.get("findings", [])] + list(extra_findings)
    counted = _counted(findings)
    red = sum(f["severity"] == "red" for f in counted)
    yellow = sum(f["severity"] == "yellow" for f in counted)
    return _level(red, yellow), {"red": red, "yellow": yellow, "likely_dust": len(findings) - len(counted)}


def _level(red, yellow):
    if red == 0 and yellow <= 2:
        return "clean"
    if red <= 1 and yellow <= 5:
        return "minor"
    if red <= 3:
        return "moderate"
    return "heavy"


def _off(c):
    return None if not c or "worst" not in c else c["worst"]


def _passes(row, f_off, b_off, level, dings):
    """Does a card with this centering and condition meet this ladder row?"""
    label, value, f_max, b_max = row[:4]
    ok_f = f_off is None or f_off <= f_max
    ok_b = b_off is None or b_off <= b_max
    if len(row) > 5 and level != "unknown":
        cond_ok = dings <= row[5]
    else:
        cond_ok = value <= MAX_GRADE_FOR_LEVEL[level]
    return ok_f, ok_b, cond_ok


def _ladder(ladder, f_off, b_off, level, dings=0):
    reasons = []
    for row in ladder:
        label, _, f_max, b_max = row[:4]
        ok_f, ok_b, cond_ok = _passes(row, f_off, b_off, level, dings)
        if ok_f and ok_b and cond_ok:
            return row, reasons
        if not ok_f:
            reasons.append(f"Not {label}: front centering {f_off:.1f}/{100 - f_off:.1f} is outside {f_max:g}/{100 - f_max:g}")
        if not ok_b:
            reasons.append(f"Not {label}: back centering {b_off:.1f}/{100 - b_off:.1f} is outside {b_max:g}/{100 - b_max:g}")
        if not cond_ok:
            reasons.append(f"Not {label}: {dings} corner/edge DING{'S' if dings != 1 else ''} (allows {row[5]})" if len(row) > 5
                           else f"Not {label}: corner/edge/surface findings ({level})")
    return None, reasons


def _odds(ladder, f_off, b_off, level, findings, n=3000, seed=7):
    """Monte Carlo grade distribution: centering jitter + each finding counting with some probability."""
    rng = np.random.default_rng(seed)
    f = (np.full(n, np.nan) if f_off is None else f_off + rng.normal(0, SIGMA_FRONT, n))
    b = (np.full(n, np.nan) if b_off is None else b_off + rng.normal(0, SIGMA_BACK, n))
    f = np.where(np.isnan(f), np.nan, np.maximum(f, 50.0))
    b = np.where(np.isnan(b), np.nan, np.maximum(b, 50.0))
    counted = _counted(findings)
    reds = sum(x["severity"] == "red" for x in counted)
    yellows = sum(x["severity"] == "yellow" for x in counted)
    red_s = rng.binomial(reds, P_RED_COUNTS, n) if reds else np.zeros(n, int)
    yel_s = rng.binomial(yellows, P_YELLOW_COUNTS, n) if yellows else np.zeros(n, int)
    tally = {}
    for i in range(n):
        lvl = level if level == "unknown" else _level(int(red_s[i]), int(yel_s[i]))
        fo = None if np.isnan(f[i]) else float(f[i])
        bo = None if np.isnan(b[i]) else float(b[i])
        row, _ = _ladder(ladder, fo, bo, lvl, int(red_s[i] + yel_s[i]))
        key = row[0] if row else f"below {ladder[-1][0]}"
        tally[key] = tally.get(key, 0) + 1
    order = [r[0] for r in ladder] + [f"below {ladder[-1][0]}"]
    return [{"grade": k, "p": round(tally[k] / n, 3)} for k in order if tally.get(k, 0) / n >= 0.01]


def _company(ladder, f_off, b_off, level, counts, findings, note, unknown_why=None):
    dings = counts.get("red", 0) + counts.get("yellow", 0)
    row, reasons = _ladder(ladder, f_off, b_off, level, dings)
    worse = lambda o: None if o is None else min(100.0, o + CENTERING_WOBBLE)
    cautious_level = level if level == "unknown" else _level(counts.get("red", 0), 2 * counts.get("yellow", 0))
    low_row, _ = _ladder(ladder, worse(f_off), worse(b_off), cautious_level, counts.get("red", 0) + 2 * counts.get("yellow", 0))
    grade = row[0] if row else f"below {ladder[-1][0]}"
    low = low_row[0] if low_row else f"below {ladder[-1][0]}"
    if level == "unknown":
        reasons.insert(0, unknown_why or "Corners and edges not checked (needs a 600+ dpi scan): centering-only ceiling")
    odds = _odds(ladder, f_off, b_off, level, findings)
    if odds and level != "unknown":
        # Headline = the most likely grade. Counting every borderline (yellow) finding as a full defect
        # undersold cards whose yellows are mostly harmless; the odds weigh each one instead.
        ranked = sorted(odds, key=lambda o: -o["p"])
        grade = ranked[0]["grade"]
        nxt = next((o for o in ranked[1:] if o["p"] >= 0.15), None)
        low = nxt["grade"] if nxt else grade
        names = [r[0] for r in ladder]
        if grade in names:  # drop "Not <grade>" reasons for the grade we landed on and below
            keep = names[:names.index(grade)]
            reasons = [r for r in reasons if not r.startswith("Not ") or any(r.startswith(f"Not {k}:") for k in keep)]
    out = {"grade": grade, "could_be": low if low != grade else None, "reasons": reasons, "note": note, "odds": odds}
    if len(ladder[0]) > 4:
        by_name = {r[0]: r[4] for r in ladder}
        top, bottom = by_name.get(grade), by_name.get(out["could_be"] or grade)
        hi = top[1] if top else 799
        lo = min(bottom[0], top[0]) if (bottom and top) else (top[0] if top else 700)
        out["score_range"] = [lo, hi]
    return out


def load_tag_calibration():
    if CALIBRATION_PATH.exists():
        return json.loads(CALIBRATION_PATH.read_text())
    return None


TAG_SCALE = [(990, "Pristine 10"), (950, "Gem Mint 10"), (900, "Mint 9"), (850, "NM-MT+ 8.5"), (800, "NM-MT 8"),
             (750, "NM+ 7.5"), (700, "NM 7"), (650, "EX-MT+ 6.5"), (600, "EX-MT 6"), (0, "6 or lower")]


def tag_grade(score):
    for floor, label in TAG_SCALE:
        if score >= floor:
            return label
    return TAG_SCALE[-1][1]


def estimate_all(front, back, surface_findings=()):
    level, counts = defect_level(front, back, surface_findings)
    f_off, b_off = _off(front and front["centering"]), _off(back and back["centering"])
    findings = [f for m in (front, back) if m and m.get("edges_reliable") for f in m.get("findings", [])] + list(surface_findings)
    cal = load_tag_calibration()
    tag_ladder = [tuple(r) for r in cal["ladder"]] if cal else TAG_PROVISIONAL
    tag_note = (f"Fitted from {cal['n_reports']} TAG reports" if cal
                else "Provisional: from the public TAG reports collected so far")
    dark = any(m and m.get("dark_card") for m in (front, back))
    why = ("Black-bordered card: corners and edges aren't scored against the black guide, so this is a "
           "centering-only ceiling") if dark else None
    missing = [name for name, m in (("front", front), ("back", back)) if not m]
    return {
        "missing": missing,  # sides not scanned yet: grades are only a ceiling until both are in
        "defect_level": level,
        "unknown_why": why,
        "counts": counts,
        "front_off": f_off,
        "back_off": b_off,
        "TAG": _company(tag_ladder, f_off, b_off, level, counts, findings, tag_note, why),
        "PSA": _company(PSA, f_off, b_off, level, counts, findings, "PSA's published centering limits", why),
        "CGC": _company(CGC, f_off, b_off, level, counts, findings, "CGC's published centering limits", why),
    }
