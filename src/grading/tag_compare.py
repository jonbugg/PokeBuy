"""Compare a scanned card with TAG-graded copies of the same card.

TAG publishes a DIG report for every card it grades: centering, the DINGS (defects) that cost it points,
where each one is, and high-resolution photos. For a card with saved TAG copies
(data/tag_compare/<card id>/ladder.json plus each cert's FRONT_MAIN.jpg / BACK_MAIN.jpg), this lines your
scans up against them:

- centering: yours against the worst centering TAG still gave each grade on this card,
- defects: what TAG counted on the 9s and 8s, cropped next to the same spot on your card and a TAG 10,
- your own findings, cropped next to the same spot on TAG 10s,
- a grade read off those comparisons, with the reasons.
"""

import json
import re
from pathlib import Path

import cv2
import numpy as np

from src.grading import measure

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "tag_compare"
PPI = 1200          # everything is compared at the scan's resolution
TAG_PPI = 1628      # TAG's published photos, measured from the card's size in them
TAG_COORD_PPI = 1687  # TAG's DINGS coordinates (card-relative): 4185 px across a 2.48" card
CARD_PX = (3000, 4200)  # card at 1200 ppi
CROP_MM = 4.0       # side of each comparison crop (small enough to see a 0.2 mm speck)
GRADE_ORDER = ["10P", "10", "9", "8.5", "8", "7.5", "7", "6.5", "6"]  # 10P = Pristine 10


def available(card_id):
    return bool(card_id) and (DATA / card_id / "ladder.json").exists()


def _worst(cent):
    """'53.7L/46.3R 52.0T/48.0B' -> (53.7, 52.0): the larger share on each axis."""
    nums = [float(x) for x in re.findall(r"[\d.]+", cent or "")]
    if len(nums) < 4:
        return None
    return (max(nums[0], nums[1]), max(nums[2], nums[3]))


def _tag_view(card_id, cert, side):
    """TAG's photo straightened and scaled to 1200 ppi with a margin, cached next to it."""
    folder = DATA / card_id / cert
    cached, meta = folder / f"{side.upper()}_view{PPI}.jpg", folder / f"{side.upper()}_view{PPI}.json"
    if cached.exists() and meta.exists():
        return cv2.imread(str(cached)), json.loads(meta.read_text())["pad"]
    img = cv2.imread(str(folder / f"{side.upper()}_MAIN.jpg"))
    if img is None:
        return None, 0
    m = measure.find_and_straighten(img, TAG_PPI)
    s = PPI / m.ppi
    view = cv2.resize(m.canon_view, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    pad = int(round(m.view_pad * s))
    cv2.imwrite(str(cached), view, [cv2.IMWRITE_JPEG_QUALITY, 92])
    # TAG's DINGS positions are in its photo's pixels: keep the mapping to card coordinates.
    H = cv2.getPerspectiveTransform(m.corners_src, np.float32([[0, 0], [m.cw - 1, 0], [m.cw - 1, m.ch - 1], [0, m.ch - 1]]))
    meta.write_text(json.dumps({"pad": pad, "H": H.tolist(), "scale": s}))
    return view, pad


def _tag_point(card_id, cert, side, x, y):
    """A DINGS location from TAG's report -> card coordinates at 1200 ppi.

    TAG gives each DING's position in pixels from the card's own top-left corner, at its capture
    resolution (~1690 ppi: corner DINGS sit ~50 px in from each corner, and the far corners are near
    4185 x 5900). They are not positions in the published photo, which has a margin around the card.
    """
    s = PPI / TAG_COORD_PPI
    return min(max(x * s, 0), CARD_PX[0] - 1), min(max(y * s, 0), CARD_PX[1] - 1)


def _crop(view, pad, x, y, out_px=300):
    r = int(round(CROP_MM / 2 / 25.4 * PPI))
    big = cv2.copyMakeBorder(view, r, r, r, r, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    xi, yi = int(round(x)) + pad + r, int(round(y)) + pad + r
    c = big[yi - r:yi + r, xi - r:xi + r]
    c = cv2.resize(c, (out_px, out_px), interpolation=cv2.INTER_CUBIC)
    cv2.circle(c, (out_px // 2, out_px // 2), int(out_px * 0.22), (40, 40, 230), 2, cv2.LINE_AA)
    return c


def _strip(tiles, labels):
    out = []
    for t, lab in zip(tiles, labels):
        t = cv2.copyMakeBorder(t, 34, 0, 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        cv2.putText(t, lab, (4, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (30, 30, 30), 1, cv2.LINE_AA)
        out += [t, np.full((t.shape[0], 10, 3), 255, np.uint8)]
    return np.hstack(out[:-1])


def _name(g, plural=False):
    n = {"10P": "Pristine 10", "10": "10", "9": "9", "8.5": "8.5", "8": "8"}.get(g, g)
    return n + ("s" if plural else "")


def _grade_key(g):
    g = re.sub(r"[^\d.P]", "", str(g).upper())
    return GRADE_ORDER.index(g) if g in GRADE_ORDER else len(GRADE_ORDER)


def build(session_dir, card_id, report):
    """The comparison for one scanned card, writing its crop images into the session folder."""
    ladder = json.loads((DATA / card_id / "ladder.json").read_text())
    d = Path(session_dir)
    sid = d.name
    stamp = int((d / "report.json").stat().st_mtime) if (d / "report.json").exists() else 0
    views = {}
    for side in ("front", "back"):
        f = d / f"{side}_view.jpg"
        if f.exists() and report.get(side):
            views[side] = (cv2.imread(str(f)), report[side].get("view_pad", 0))
    copies = sorted(ladder.items(), key=lambda kv: (_grade_key(kv[1]["grade"]), -(kv[1].get("score") or 1000)))
    tens = [c for c, v in copies if v["grade"] == "10"] or [c for c, v in copies if v["grade"] == "10P"]

    # --- centering
    yours = {}
    for side in ("front", "back"):
        c = (report.get(side) or {}).get("centering") or {}
        if c.get("lr") is not None and c.get("tb") is not None:
            yours[side] = (max(c["lr"], 100 - c["lr"]), max(c["tb"], 100 - c["tb"]))
    rows = []
    for cert, v in copies:
        dg = v.get("dings") or [0] * 6
        rows.append({"cert": cert, "grade": v["grade"], "score": v.get("score"),
                     "front": _worst(v.get("centF")), "back": _worst(v.get("centB")),
                     "corners": dg[0] + dg[1], "edges": dg[2] + dg[3], "surface": dg[4] + dg[5],
                     "spots": [{"side": s[0], "kind": s[1].title()} for s in v.get("spots", [])],
                     "url": f"https://my.taggrading.com/card/{cert}"})

    # Worst centering TAG still gave each grade (or better) on this card.
    def ceiling(grade):
        ok = [r for r in rows if _grade_key(r["grade"]) <= _grade_key(grade) and r["front"] and r["back"]]
        if not ok:
            return None
        return {"front": max(max(r["front"]) for r in ok), "back": max(max(r["back"]) for r in ok)}

    # --- crops: each spot TAG counted, next to your card and a TAG 10
    tag_spots = []
    i = 0
    for cert, v in copies:
        for side, kind, px, py in v.get("spots", []):
            x, y = _tag_point(card_id, cert, side, px, py)
            tv, tp = _tag_view(card_id, cert, side)
            tiles, labels = [_crop(tv, tp, x, y)], [f"TAG {v['grade']} {cert}"]
            if side in views:
                tiles.append(_crop(*views[side], x, y)); labels.append("Your card, same spot")
            if tens:
                rv, rp = _tag_view(card_id, tens[0], side)
                tiles.append(_crop(rv, rp, x, y)); labels.append(f"TAG 10 {tens[0]}")
            name = f"tagcmp_spot_{i}.jpg"
            cv2.imwrite(str(d / name), _strip(tiles, labels), [cv2.IMWRITE_JPEG_QUALITY, 88])
            tag_spots.append({"cert": cert, "grade": v["grade"], "side": side, "kind": kind.title(),
                              "img": f"/scans/{sid}/{name}?t={stamp}"})
            i += 1

    # --- your findings that still count, next to the same spot on TAG 10s
    counted = []
    for side in ("front", "back"):
        data = report.get(side) or {}
        for f in data.get("findings", []):
            if f.get("cleared"):
                continue
            counted.append((side, f))
    for f in report.get("surface_findings", []):
        counted.append((f["side"], f))
    your_spots = []
    for j, (side, f) in enumerate(counted):
        if side not in views or not f.get("box"):
            continue
        x0, y0, x1, y1 = f["box"]
        x, y = (x0 + x1) / 2, (y0 + y1) / 2
        tiles, labels = [_crop(*views[side], x, y)], [f"Yours: {f['kind']} ({f['severity']})"]
        for cert in tens[:2]:
            tv, tp = _tag_view(card_id, cert, side)
            tiles.append(_crop(tv, tp, x, y)); labels.append(f"TAG 10 {cert}")
        name = f"tagcmp_yours_{j}.jpg"
        cv2.imwrite(str(d / name), _strip(tiles, labels), [cv2.IMWRITE_JPEG_QUALITY, 88])
        your_spots.append({"side": side, "kind": f["kind"], "severity": f["severity"], "region": f.get("region"),
                           "img": f"/scans/{sid}/{name}?t={stamp}"})

    # --- the grade these comparisons point to
    red = sum(1 for _, f in counted if f["severity"] == "red")
    yellow = sum(1 for _, f in counted if f["severity"] == "yellow")
    missing = [s for s in ("front", "back") if s not in yours]
    lines, call = [], None
    if not missing:
        for grade in [g for g in GRADE_ORDER if any(r["grade"] == g for r in rows)]:
            cap = ceiling(grade)
            same = [r for r in rows if r["grade"] == grade]
            most_dings = max(r["corners"] + r["edges"] + r["surface"] for r in same)
            cent_ok = cap and max(yours["front"]) <= cap["front"] + 0.5 and max(yours["back"]) <= cap["back"] + 0.5
            dings_ok = red <= most_dings
            if cent_ok and dings_ok:
                call = grade
                lines.append(f"Centering: your worst front {max(yours['front']):.1f}/{100 - max(yours['front']):.1f} and back "
                             f"{max(yours['back']):.1f}/{100 - max(yours['back']):.1f} are within what TAG gave a {_name(grade)} on this card "
                             f"(as far as {cap['front']:.0f}/{100 - cap['front']:.0f} front, {cap['back']:.0f}/{100 - cap['back']:.0f} back).")
                lines.append(f"Defects: TAG's {_name(grade, True)} of this card had up to {most_dings} counted DINGS; your card has {red} "
                             f"clear (red) finding{'s' if red != 1 else ''} after the 180° check"
                             + (f", plus {yellow} borderline (yellow) to check by eye." if yellow else "."))
                break
            why = []
            if not cent_ok and cap:
                why.append(f"centering is outside the {_name(grade, True)}' range ({cap['front']:.0f}/{100 - cap['front']:.0f} front, "
                           f"{cap['back']:.0f}/{100 - cap['back']:.0f} back)")
            if not dings_ok:
                why.append(f"{red} clear finding{'s' if red != 1 else ''} vs at most {most_dings} on TAG's {_name(grade, True)}")
            lines.append(f"Not {_name(grade)}: " + " and ".join(why) + ".")
    return {"card_id": card_id, "copies": rows, "yours": {k: list(v) for k, v in yours.items()},
            "counted": {"red": red, "yellow": yellow}, "tag_spots": tag_spots, "your_spots": your_spots,
            "call": call, "lines": lines, "missing": missing,
            "ceilings": {g: ceiling(g) for g in GRADE_ORDER if any(r["grade"] == g for r in rows)}}
