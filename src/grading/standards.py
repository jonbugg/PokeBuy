"""Turn measurements and findings into expected grades per grading company.

PSA and CGC centering limits are from their official grading-scale pages (read 2026-11-07).
TAG does not publish limits. Until data/tag_calibration.json exists, TAG uses a provisional rule read
off the public TAG reports collected so far (every Pristine 10 was 51/49 or better with no DINGS;
Gem Mint 10s sat at about 55/45 with at most one DING).
"""

import json
from pathlib import Path

CALIBRATION_PATH = Path(__file__).resolve().parents[2] / "data" / "tag_calibration.json"
CENTERING_WOBBLE = 1.0  # points of centering a rescan can move; used for the cautious grade

# (grade label, numeric grade, max front off-centre %, max back off-centre %) — "55" means 55/45 or better.
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
TAG_PROVISIONAL = [  # (label, numeric, front, back, score range)
    ("Pristine 10", 10.5, 51.5, 51.5, (990, 1000)),
    ("Gem Mint 10", 10, 55, 55, (950, 989)),
    ("Mint 9", 9, 57, 61, (900, 949)),
    ("NM-MT+ 8.5", 8.5, 58, 62, (850, 899)),
    ("NM-MT 8", 8, 60, 65, (800, 849)),
]

DEFECT_LEVELS = ["clean", "minor", "moderate", "heavy"]
MAX_GRADE_FOR_LEVEL = {"clean": 10.5, "minor": 9, "moderate": 8, "heavy": 7, "unknown": 10.5}


def defect_level(front, back, extra_findings=()):
    """Overall condition from the red/yellow findings on both sides (plus any surface findings)."""
    usable = [m for m in (front, back) if m and m.get("edges_reliable")]
    if not usable:
        return "unknown", {"red": 0, "yellow": 0}
    findings = [f for m in usable for f in m.get("findings", [])] + list(extra_findings)
    red = sum(f["severity"] == "red" for f in findings)
    yellow = sum(f["severity"] == "yellow" for f in findings)
    return _level(red, yellow), {"red": red, "yellow": yellow}


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


def _ladder(ladder, front_off, back_off, level):
    """First grade on the ladder whose centering limits and condition the card meets."""
    max_grade = MAX_GRADE_FOR_LEVEL[level]
    reasons = []
    for row in ladder:
        label, value, f_max, b_max = row[:4]
        ok_f = front_off is None or front_off <= f_max
        ok_b = back_off is None or back_off <= b_max
        defect_ok = value <= max_grade
        if ok_f and ok_b and defect_ok:
            return row, reasons
        if not ok_f:
            reasons.append(f"Not {label}: front centering {front_off:.1f}/{100 - front_off:.1f} is outside {f_max:g}/{100 - f_max:g}")
        if not ok_b:
            reasons.append(f"Not {label}: back centering {back_off:.1f}/{100 - back_off:.1f} is outside {b_max:g}/{100 - b_max:g}")
        if not defect_ok:
            reasons.append(f"Not {label}: corner/edge/surface findings ({level})")
    return None, reasons


def _company(ladder, f_off, b_off, level, counts, note):
    row, reasons = _ladder(ladder, f_off, b_off, level)
    # Cautious case: centering a point worse (rescan wobble) and each yellow counted twice.
    worse = lambda o: None if o is None else min(100.0, o + CENTERING_WOBBLE)
    cautious_level = level if level == "unknown" else _level(counts.get("red", 0), 2 * counts.get("yellow", 0))
    low_row, _ = _ladder(ladder, worse(f_off), worse(b_off), cautious_level)
    grade = row[0] if row else f"below {ladder[-1][0]}"
    low = low_row[0] if low_row else f"below {ladder[-1][0]}"
    if level == "unknown":
        reasons.insert(0, "Corners and edges not checked (needs a 600+ dpi scan): centering-only ceiling")
    out = {"grade": grade, "could_be": low if low != grade else None, "reasons": reasons, "note": note}
    if len(ladder[0]) > 4:
        hi = row[4][1] if row else 799
        lo = (low_row[4][0] if low_row else 700)
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
    cal = load_tag_calibration()
    tag_note = (f"Fitted from {cal.get('n_reports', '?')} TAG reports" if cal
                else "Provisional: from the public TAG reports collected so far")
    return {
        "defect_level": level,
        "counts": counts,
        "front_off": f_off,
        "back_off": b_off,
        "TAG": _company(cal.get("ladder", TAG_PROVISIONAL) if cal else TAG_PROVISIONAL, f_off, b_off, level, counts, tag_note),
        "PSA": _company(PSA, f_off, b_off, level, counts, "PSA's published centering limits"),
        "CGC": _company(CGC, f_off, b_off, level, counts, "CGC's published centering limits"),
    }
