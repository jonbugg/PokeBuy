"""Run Grade Check's measurements on TAG's own photos of graded cards and compare with TAG's grades.

For every saved TAG copy (data/tag_compare/<card>/<cert>/FRONT_MAIN.jpg, BACK_MAIN.jpg), this measures
both sides exactly as a scan would be measured, estimates the grades, and lines them up against what TAG
gave the card: centering (ours vs TAG's numbers), defects (ours vs TAG's DINGS) and the grade itself.

TAG's photos are not scanner images: different lighting, an orange backdrop, and no 180° second pass,
so surface checks and the "cleared by the 180° scan" step can't run. Centering is a like-for-like test;
edges and corners are a rougher one.

Usage: .venv/bin/python scripts/validate_on_tag.py
Writes data/tag_compare/validation.json and prints a table.
"""

import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.grading import closeups, measure, standards  # noqa: E402
from src.grading.tag_compare import TAG_PPI  # noqa: E402

DATA = ROOT / "data" / "tag_compare"


def tag_cent(s):
    n = [float(x) for x in re.findall(r"[\d.]+", s or "")]
    return (n[0], n[2]) if len(n) >= 4 else None  # left share, top share


def trim_bars(img):
    """TAG's photos can carry solid black bars along their edges: trim them off."""
    L0 = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)[..., 0]
    cols = np.where((L0 > 45).mean(axis=0) > 0.2)[0]
    rows = np.where((L0 > 45).mean(axis=1) > 0.2)[0]
    if len(cols) and len(rows):
        img = img[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
    return img


def on_guide(img):
    """Make a TAG photo look like a scan on the matching guide: TAG's orange backdrop and the black bars at
    the photo's edges become the guide's colour, so the card is measured against the backdrop the code
    expects. Like at home: the grey guide for black-bordered cards, the black guide for the rest."""
    img = trim_bars(img)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    h, w = lab.shape[:2]
    band = np.zeros((h, w), bool)
    k = max(4, int(0.01 * min(h, w)))  # TAG's orange margin is only ~1.5% of the photo
    band[:k], band[-k:], band[:, :k], band[:, -k:] = True, True, True, True
    chroma = np.hypot(lab[..., 1] - 128, lab[..., 2] - 128)
    vivid = band & (lab[..., 0] > 60) & (chroma > 45)  # the orange, not the black bars or the card
    ref = np.median(lab[vivid], axis=0)
    orange = (np.abs(lab[..., 1] - ref[1]) < 22) & (np.abs(lab[..., 2] - ref[2]) < 28) & (lab[..., 0] > 35)
    black = lab[..., 0] < 30
    cand = (orange | black).astype(np.uint8)
    n, comp = cv2.connectedComponents(cand, connectivity=4)
    edge_ids = set(np.unique(np.concatenate([comp[0], comp[-1], comp[:, 0], comp[:, -1]]))) - {0}
    bg = np.isin(comp, list(edge_ids))
    bg = cv2.morphologyEx(bg.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)) > 0
    # The card's own border colour, from a thin ring just inside the backdrop.
    ring = cv2.dilate(bg.astype(np.uint8), np.ones((25, 25), np.uint8)).astype(bool) & ~cv2.dilate(bg.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
    dark_border = float(np.median(lab[..., 0][ring])) < 90
    level = 150 if dark_border else 62  # grey guide / printed black guide
    fill = np.clip(np.random.default_rng(0).normal(level, 6, img.shape), 0, 255).astype(np.uint8)
    out = img.copy()
    out[bg] = fill[bg]
    edge = cv2.dilate(bg.astype(np.uint8), np.ones((5, 5), np.uint8)) & ~cv2.erode(bg.astype(np.uint8), np.ones((5, 5), np.uint8))
    blur = cv2.GaussianBlur(out, (5, 5), 0)
    out[edge > 0] = blur[edge > 0]
    return pad_like_scan(out, level)


def pad_like_scan(img, level=None):
    """TAG crops tightly; a scan always has a wide margin of guide around the card. Add one, so the
    backdrop is read from the guide and not from the card's own border."""
    k = int(0.06 * max(img.shape[:2]))
    if level is None:  # keep the photo's own backdrop colour (TAG's orange)
        edge = np.concatenate([img[:4].reshape(-1, 3), img[-4:].reshape(-1, 3), img[:, :4].reshape(-1, 3), img[:, -4:].reshape(-1, 3)])
        colour = np.median(edge, axis=0)
    else:
        colour = np.array([level] * 3, float)
    canvas = np.clip(np.random.default_rng(1).normal(0, 6, (img.shape[0] + 2 * k, img.shape[1] + 2 * k, 3)) + colour, 0, 255).astype(np.uint8)
    canvas[k:k + img.shape[0], k:k + img.shape[1]] = img
    return canvas


def side(path):
    img = on_guide(cv2.imread(str(path)))
    m = measure.measure_image(img, src_ppi=TAG_PPI)
    data = {"centering": m.centering, "edges": m.edges, "corners": m.corners, "warnings": m.warnings,
            "dims_in": m.dims_in, "edges_reliable": m.edges_reliable,
            "dark_card": bool(getattr(m, "dark_card", False))}
    data["findings"] = closeups.build_findings(m)
    return data


def num(g):
    g = str(g).upper()
    return 10.5 if "P" in g or "PRISTINE" in g else float((re.findall(r"\d+(?:\.\d)?", g) or ["0"])[0])


def main():
    rows = []
    for ladder_file in sorted(DATA.glob("*/ladder.json")):
        card = ladder_file.parent.name
        for cert, v in json.loads(ladder_file.read_text()).items():
            folder = ladder_file.parent / cert
            try:
                f, b = side(folder / "FRONT_MAIN.jpg"), side(folder / "BACK_MAIN.jpg")
            except Exception as e:  # noqa: BLE001 - report and carry on
                rows.append({"card": card, "cert": cert, "tag": v["grade"], "error": str(e)})
                continue
            est = standards.estimate_all(f, b, [])
            ours = {s: (d["centering"].get("lr"), d["centering"].get("tb")) for s, d in (("front", f), ("back", b))}
            theirs = {"front": tag_cent(v.get("centF")), "back": tag_cent(v.get("centB"))}
            counts = {"red": 0, "yellow": 0}
            for d in (f, b):
                for x in d["findings"]:
                    counts[x["severity"]] += 1
            rows.append({
                "card": card, "cert": cert, "tag": v["grade"], "tag_score": v.get("score"),
                "tag_dings": sum(v.get("dings") or []), "tag_spots": [s[1] for s in v.get("spots", [])],
                "ours_tag": est["TAG"]["grade"], "ours_could_be": est["TAG"].get("could_be"),
                "ours_odds": est["TAG"].get("odds"), "psa": est["PSA"]["grade"],
                "our_findings": counts, "level": est["defect_level"],
                "cent_ours": ours, "cent_tag": theirs,
                "warnings": f["warnings"] + b["warnings"],
            })
            r = rows[-1]
            print(f"{card:14} {cert} TAG {v['grade']:>4}  ours {r['ours_tag']:<16} "
                  f"cent F ours {fmt(ours['front'])} tag {fmt(theirs['front'])} | B ours {fmt(ours['back'])} tag {fmt(theirs['back'])} "
                  f"| TAG dings {r['tag_dings']} ours {counts['red']}r/{counts['yellow']}y | size {f['dims_in']}", flush=True)
    (DATA / "validation.json").write_text(json.dumps(rows, indent=1, default=float))
    summarise(rows)


def fmt(c):
    return "  —  " if not c or c[0] is None else f"{c[0]:4.1f}/{c[1]:4.1f}"


def summarise(rows):
    ok = [r for r in rows if "error" not in r]
    print(f"\n{len(ok)} of {len(rows)} measured")
    errs = []
    for r in ok:
        for s in ("front", "back"):
            o, t = r["cent_ours"][s], r["cent_tag"][s]
            if o and t and o[0] is not None and o[1] is not None:
                errs += [abs(o[0] - t[0]), abs(o[1] - t[1])]
    if errs:
        errs.sort()
        print(f"Centering vs TAG: median difference {errs[len(errs) // 2]:.2f} points, "
              f"90% within {errs[int(len(errs) * 0.9)]:.2f}, worst {errs[-1]:.2f} ({len(errs)} numbers)")
    exact = sum(1 for r in ok if num(r["ours_tag"]) == num(r["tag"]))
    within = sum(1 for r in ok if abs(num(r["ours_tag"]) - num(r["tag"])) <= 0.5)
    print(f"Grade: exact {exact}/{len(ok)}, within half a grade {within}/{len(ok)}")
    over = [r for r in ok if num(r["ours_tag"]) > num(r["tag"]) + 0.25]
    under = [r for r in ok if num(r["ours_tag"]) < num(r["tag"]) - 0.25]
    print(f"Too generous: {len(over)}  ({', '.join(r['cert'] + ' ' + r['tag'] + '->' + r['ours_tag'] for r in over)})")
    print(f"Too harsh:    {len(under)}  ({', '.join(r['cert'] + ' ' + r['tag'] + '->' + r['ours_tag'] for r in under)})")


if __name__ == "__main__":
    main()
