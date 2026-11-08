"""Score a scan's backdrop: how well does the card stand out from it?

For a scan of one card on a backdrop (construction paper, guide sheet...), reports:
- size: the card's measured width x height (a real card is ~2.48 x 3.47 in)
- straightness: how far the traced outline wanders from straight lines along each side (px RMS)
- contrast: colour difference between the backdrop and the card's border, per side (Lab units)
- sharpness: how many px the step from backdrop to card takes (10%-90%)
- texture: how noisy the backdrop is (Lab spread) and how much of it looks "unlike backdrop"
  (fibres/specks that the chip and corner checks could mistake for card)
- centering and the corner/edge findings it produces (false flags show up here)

Usage: .venv/bin/python scripts/backdrop_test.py DPI scan.jpg [more scans...]
"""

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.grading import closeups, measure  # noqa: E402


def side_profiles(view, pad, ppi):
    """Profiles across each edge over the middle 60% of the side: 1 mm outside to 1 mm inside."""
    lab = cv2.cvtColor(view, cv2.COLOR_BGR2LAB).astype(np.float32)
    H, W = lab.shape[:2]
    r = int(1.0 * ppi / 25.4)
    cw, ch = W - 2 * pad, H - 2 * pad
    ys = slice(pad + int(0.2 * ch), pad + int(0.8 * ch))
    xs = slice(pad + int(0.2 * cw), pad + int(0.8 * cw))
    return {
        "left": lab[ys, pad - r:pad + r].mean(axis=0),
        "right": lab[ys, W - pad + r - 1:W - pad - r - 1:-1].mean(axis=0),
        "top": lab[pad - r:pad + r, xs].mean(axis=1),
        "bottom": lab[H - pad + r - 1:H - pad - r - 1:-1, xs].mean(axis=1),
    }, r


def score(path, dpi):
    img = cv2.imread(str(path))
    m = measure.measure_image(img, src_ppi=dpi)
    view, pad = m.canon_view, m.view_pad
    res = {"scan": Path(path).name, "size_in": m.dims_in, "warnings": m.warnings}

    pts, labels, _, _ = m._outline
    resid = []
    for side in ("top", "bottom", "left", "right"):
        p = pts[labels == side]
        if len(p) < 20:
            continue
        along, across = (p[:, 0], p[:, 1]) if side in ("top", "bottom") else (p[:, 1], p[:, 0])
        keep = (along > np.percentile(along, 15)) & (along < np.percentile(along, 85))
        a, b = np.polyfit(along[keep], across[keep], 1)
        resid.append(float(np.sqrt(np.mean((across[keep] - (a * along[keep] + b)) ** 2))))
    res["outline_wander_px"] = round(float(np.mean(resid)), 2)

    prof, r = side_profiles(view, pad, m.ppi)
    contrast, sharp = {}, {}
    for side, p in prof.items():
        bg, card = p[: r // 2].mean(axis=0), p[-r // 2:].mean(axis=0)
        contrast[side] = round(float(np.linalg.norm(card - bg)), 1)
        d = np.linalg.norm(p - bg, axis=1) / (np.linalg.norm(card - bg) + 1e-6)
        sharp[side] = int(np.argmax(d > 0.9)) - int(np.argmax(d > 0.1))
    res["contrast"] = contrast
    res["edge_px_10_90"] = sharp

    lab = cv2.cvtColor(view, cv2.COLOR_BGR2LAB).astype(np.float32)
    band = np.zeros(lab.shape[:2], bool)
    a0, a1 = max(1, int(pad * 0.15)), int(pad * 0.6)
    band[a0:a1, :] = True; band[-a1:-a0, :] = True; band[:, a0:a1] = True; band[:, -a1:-a0] = True
    bgpix = lab[band]
    bgc = np.median(bgpix, axis=0)
    dist = np.linalg.norm(bgpix - bgc, axis=1)
    res["backdrop_lab"] = bgc.round().tolist()
    res["backdrop_spread"] = round(float(np.median(dist)), 1)
    res["backdrop_specks_%"] = round(100 * float((dist > 25).mean()), 2)
    res["looks_like_backdrop_%"] = round(100 * float(closeups._backdrop_like(m)[band].mean()), 1)

    c = m.centering or {}
    res["centering"] = {k: round(float(c[k]), 1) for k in ("lr", "tb") if c.get(k) is not None}
    f = closeups.build_findings(m)
    res["findings"] = {"red": sum(x["severity"] == "red" for x in f), "yellow": sum(x["severity"] == "yellow" for x in f),
                       "kinds": sorted({x["kind"] for x in f})}
    return res


if __name__ == "__main__":
    dpi = int(sys.argv[1])
    for p in sys.argv[2:]:
        r = score(p, dpi)
        print(f"\n== {r.pop('scan')}")
        for k, v in r.items():
            print(f"  {k:22} {v}")
