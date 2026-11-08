"""PROTOTYPE, not used by the app: look for thin lines (scratches, print lines, fibres) on a card's solid border,
in the average of every scan of that side. The surface check compares scans lit from different sides, so it is blind
to a scratch that scatters light the same way from every side; this looks for thin bright lines present in all scans.

Status (Nov 8): finds real things (a ~1.5 mm curved line on the Charizard ex back, the faint hairline near its
top-right corner) but also 30-70 lines per card, mostly the cut edge itself and card-stock texture, so it is not
wired into the grade. Next steps: keep away from the cut edge (start ~0.8 mm in), require lines that are not parallel
to and hugging the edge, and calibrate the threshold on cards with known scratches.

Usage: .venv/bin/python scripts/border_lines_prototype.py <session>:<side> ...
"""
import sys, json, cv2, numpy as np
sys.path.insert(0, "/Users/jon/PokeBuy/PokeBuy")
import grade_app
from src.grading.relief import _grey, _aligned
from pathlib import Path

def line_response(g, mm):
    """Max over directions of a thin-line filter (bright line on darker surround), ~1 mm long."""
    L = int(round(1.0 * mm)) | 1
    best = np.zeros_like(g)
    for ang in range(0, 180, 15):
        k = np.zeros((L, L), np.float32)
        c = L // 2
        dx, dy = np.cos(np.radians(ang)), np.sin(np.radians(ang))
        for t in np.linspace(-c, c, 2 * L):
            x, y = int(round(c + t * dx)), int(round(c + t * dy))
            k[y, x] = 1
        k = cv2.GaussianBlur(k, (0, 0), 0.8)
        k /= k.sum()
        along = cv2.filter2D(g, -1, k)
        side = cv2.GaussianBlur(along, (0, 0), 0.15 * mm)  # local surround
        best = np.maximum(best, along - side)
    return best

def run(sid, side):
    d = Path(f"/Users/jon/PokeBuy/PokeBuy/data/scans/{sid}")
    first = cv2.imread(str(d / f"{side}_canon.png"))
    a = _grey(first)
    scans = {"0": a}
    if (d / f"{side}_rot_canon.png").exists():
        scans["180"] = _aligned(a, cv2.rotate(cv2.imread(str(d / f"{side}_rot_canon.png")), cv2.ROTATE_180))
    for q in ("r90", "r270"):
        f = d / f"{side}_{q}_canon.png"
        if f.exists():
            scans[q[1:]] = _aligned(a, grade_app._upright_like(cv2.imread(str(f)), first))
    h, w = a.shape; mm = w / 63.5
    c = json.loads((d / f"{side}.json").read_text())["centering"]["widths_mm"]
    # border band: 0.4 mm in from the cut edge to 0.35 mm short of the border's inner edge
    band = np.zeros((h, w), bool)
    o = int(0.4 * mm)
    L_, R_, T_, B_ = [int((c[k] - 0.35) * mm) if c.get(k) else 0 for k in ("left", "right", "top", "bottom")]
    band[o:T_, o:w - o] = True; band[h - B_:h - o, o:w - o] = True
    band[o:h - o, o:L_] = True; band[o:h - o, w - R_:w - o] = True
    # keep out the rounded corners
    rr = int(3.5 * mm)
    for cy, cx in ((0, 0), (0, w), (h, 0), (h, w)):
        band[max(0, cy - rr):cy + rr, max(0, cx - rr):cx + rr] = False
    resp = {k: line_response(v, mm) for k, v in scans.items()}
    sig = {k: 1.4826 * np.median(np.abs(r[band] - np.median(r[band]))) for k, r in resp.items()}
    mean = np.mean([resp[k] / sig[k] for k in resp], axis=0)
    hits = ((mean > 5) & band).astype(np.uint8)
    n, lab, st, cen = cv2.connectedComponentsWithStats(hits, 8)
    found = []
    for i in range(1, n):
        x, y, ww, hh, area = st[i]
        reg = lab == i
        pts = np.column_stack(np.where(reg))[:, ::-1].astype(np.float32)
        (_, _), (rw, rh), _ = cv2.minAreaRect(pts)
        length, width = max(rw, rh) / mm, max(1.0, min(rw, rh)) / mm
        if length < 0.6 or length / width < 3:
            continue
        seen = sum(float(resp[k][reg].max() / sig[k]) > 4 for k in resp)
        found.append((round(cen[i][0] / mm, 1), round(cen[i][1] / mm, 1), round(length, 2), round(float(mean[reg].max()), 1), f"{seen}/{len(resp)}"))
    found.sort(key=lambda f: -f[3])
    print(f"{sid[-6:]} {side}: scans {list(scans)}; {len(found)} line(s) on the border (x mm, y mm, length, strength, seen in):", found[:10], flush=True)

for arg in sys.argv[1:]:
    run(*arg.split(":"))
