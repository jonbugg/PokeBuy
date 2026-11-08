"""Can the surface check still find real damage? Paint fake scratches and dents onto two clean scans of a card,
shaded the way real ones are (light on one side, dark on the other, flipping when the card is turned 180°),
and see which the check finds.

Usage: .venv/bin/python scripts/surface_fake_test.py <session> [side]
"""

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.grading import surface  # noqa: E402


def paint(img, cx, cy, length_px, angle, depth, width_px, flip):
    """A ridge-shaded mark: one side lighter, the other darker by `depth` grey levels."""
    out = img.astype(np.float32)
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ca, sa = np.cos(angle), np.sin(angle)
    u = (xx - cx) * ca + (yy - cy) * sa        # along the mark
    v = -(xx - cx) * sa + (yy - cy) * ca       # across it
    along = np.clip(1 - np.abs(u) / (length_px / 2 + 1e-6), 0, 1) ** 0.3 if length_px > 0 else 1.0
    profile = -v / width_px * np.exp(-(v / width_px) ** 2) * 2.3  # derivative of a Gaussian: light/dark pair
    if length_px == 0:  # a dent: round
        r = np.hypot(xx - cx, yy - cy)
        profile = -(yy - cy) / width_px * np.exp(-(r / width_px) ** 2) * 2.3
        along = 1.0
    shade = depth * profile * along * (-1 if flip else 1)
    return np.clip(out + shade[..., None], 0, 255).astype(np.uint8)


def main(sid, side="front"):
    d = ROOT / "data" / "scans" / sid
    a, b = cv2.imread(str(d / f"{side}_canon.png")), cv2.imread(str(d / f"{side}_rot_canon.png"))
    h, w = a.shape[:2]
    mm = w / 63.5
    base, _ = surface.compare(a, b)
    print(f"{sid} {side}: {len(base['marks'])} marks before painting")
    cases = [("scratch 5 mm", 5.0, 0.6), ("scratch 2 mm", 2.0, 0.3), ("dent 1 mm", 0.0, 1.0), ("dent 0.5 mm", 0.0, 0.5)]
    spots = [(0.30, 0.35), (0.70, 0.35), (0.30, 0.70), (0.70, 0.70)]
    for depth in (6, 10, 16, 25):
        found = []
        aa, bb = a.copy(), b.copy()
        for (name, length, wid), (fx, fy) in zip(cases, spots):
            cx, cy = fx * w, fy * h
            aa = paint(aa, cx, cy, length * mm, 0.4, depth, wid * mm / 2, flip=False)
            # the 180° scan is stored turned: the same spot sits at the opposite corner, shading flipped by the
            # turn itself (light now comes from the other side relative to the card)
            bb = paint(bb, w - 1 - cx, h - 1 - cy, length * mm, 0.4, depth, wid * mm / 2, flip=False)
        res, _ = surface.compare(aa, bb)
        for (name, length, wid), (fx, fy) in zip(cases, spots):
            hit = [m for m in res["marks"] if abs(m["x_pct"] - 100 * fx) < 2.5 and abs(m["y_pct"] - 100 * fy) < 2.5]
            set_aside = [m for m in res["debris"] if abs(m["x_pct"] - 100 * fx) < 2.5 and abs(m["y_pct"] - 100 * fy) < 2.5]
            found.append(f"{name}: " + (("red" if max(m["strength"] for m in hit) > surface.RED_STRENGTH else "yellow") if hit
                                        else ("set aside" if set_aside else "missed")))
        print(f"  shading ±{depth:>2} grey levels: " + " | ".join(found), flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
