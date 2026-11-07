"""Turn measurements into red/yellow findings and render TAG-style close-ups with boxes around them.

Red  = likely to cost grade.  Yellow = worth a look.  Thresholds are starting points (mm).
"""

import cv2
import numpy as np

from .measure import CORNER_NAMES, Measurement, _rolling_median, _runs

SIDES = ("top", "bottom", "left", "right")
RED, YELLOW, GREEN = (40, 40, 230), (0, 200, 255), (80, 190, 60)  # BGR

# Edge whitening: pale rim deeper than this edge's normal rim...
WHITE_YELLOW = (0.085, 0.15)   # (extra depth mm, min length mm)
WHITE_RED = (0.106, 0.30)
WHITE_RED_DEEP = (0.20, 0.15)
# Edge chips: outline dips inside the straight edge...
CHIP_YELLOW = (0.08, 0.25)
CHIP_RED = (0.15, 0.25)
# Corners: outline off a perfect rounded corner...
CORNER_YELLOW_MM = 0.12
CORNER_RED_MM = 0.20


def _sev_rank(s):
    return {"red": 2, "yellow": 1, "green": 0}[s]


def build_findings(m: Measurement):
    if not m.edges_reliable or getattr(m, "_outline", None) is None:
        return []
    pts, labels, rim, typical = m._outline
    sd = m._sd
    findings = []

    for side in SIDES:
        idx = np.where(labels == side)[0]
        if not len(idx):
            continue
        along = pts[idx, 0] if side in ("top", "bottom") else pts[idx, 1]
        idx = idx[np.argsort(along)]
        extra_mm = (rim[idx] - typical[side]) * m.mmpp
        dev = sd[idx]
        dent_mm = np.clip(dev - _rolling_median(dev, int(0.3 * m.ppi)), 0, None) * m.mmpp

        def runs(flags, min_mm):
            return _runs(flags, min_len=max(2, int(round(m.px(min_mm)))))

        taken = np.zeros(len(idx), dtype=bool)
        for sev, (depth, length) in (("red", WHITE_RED_DEEP), ("red", WHITE_RED), ("yellow", WHITE_YELLOW)):
            for a, b in runs((extra_mm > depth) & ~taken, length):
                taken[a:b] = True
                findings.append(_edge_finding(m, side, "whitening", sev, pts[idx[a:b]],
                                              size_mm=(b - a) * m.mmpp, depth_mm=float(extra_mm[a:b].max())))
        taken[:] = False
        for sev, (depth, length) in (("red", CHIP_RED), ("yellow", CHIP_YELLOW)):
            for a, b in runs((dent_mm > depth) & ~taken, length):
                taken[a:b] = True
                findings.append(_edge_finding(m, side, "chip / nick", sev, pts[idx[a:b]],
                                              size_mm=(b - a) * m.mmpp, depth_mm=float(dent_mm[a:b].max())))

    for name in CORNER_NAMES:
        idx = np.where(labels == name)[0]
        if not len(idx):
            continue
        dev_mm = sd[idx] * m.mmpp
        worst = float(np.abs(dev_mm).max())
        if worst > CORNER_YELLOW_MM:
            sev = "red" if worst > CORNER_RED_MM else "yellow"
            off = idx[np.abs(dev_mm) > CORNER_YELLOW_MM]
            kind = "corner wear (missing)" if dev_mm[np.argmax(np.abs(dev_mm))] > 0 else "corner bent / lifted"
            findings.append(_box_finding(m, name, kind, sev, pts[off], size_mm=worst, depth_mm=worst))
        side = "top" if name.startswith("top") else "bottom"
        extra_mm = (rim[idx] - typical[side]) * m.mmpp
        for a, b in _runs(extra_mm > WHITE_RED[0], min_len=max(2, int(round(m.px(0.2))))):
            sev = "red" if (b - a) * m.mmpp >= 0.5 else "yellow"
            findings.append(_box_finding(m, name, "corner whitening", sev, pts[idx[a:b]],
                                         size_mm=(b - a) * m.mmpp, depth_mm=float(extra_mm[a:b].max())))
    return findings


def _edge_finding(m, side, kind, sev, p, size_mm, depth_mm):
    return _box_finding(m, side, kind, sev, p, size_mm, depth_mm, inward_mm=max(0.4, depth_mm + 0.3))


def _box_finding(m, region, kind, sev, p, size_mm, depth_mm, inward_mm=0.6):
    pad = m.px(0.25)
    x0, y0 = p[:, 0].min(), p[:, 1].min()
    x1, y1 = p[:, 0].max(), p[:, 1].max()
    inward = m.px(inward_mm)
    if region == "top":
        y1 += inward
    elif region == "bottom":
        y0 -= inward
    elif region == "left":
        x1 += inward
    elif region == "right":
        x0 -= inward
    else:  # corners: grow toward the card centre
        x0 -= inward * 0.5; x1 += inward * 0.5; y0 -= inward * 0.5; y1 += inward * 0.5
    return {
        "region": region, "kind": kind, "severity": sev,
        "size_mm": round(float(size_mm), 2), "depth_mm": round(float(depth_mm), 3),
        "box": [int(max(0, x0 - pad)), int(max(0, y0 - pad)), int(min(m.cw - 1, x1 + pad)), int(min(m.ch - 1, y1 + pad))],
    }


def surface_findings(marks, canon_shape):
    """Surface marks (from the 180° comparison) as findings in canonical pixel coordinates."""
    h, w = canon_shape[:2]
    mmpp = 63.5 / w
    out = []
    for mk in marks:
        cx, cy = mk["x_pct"] / 100 * w, mk["y_pct"] / 100 * h
        half = max(mk["length_mm"] / 2 + 0.4, 0.8) / mmpp
        out.append({
            "region": "surface", "kind": f"surface {mk['kind']}",
            "severity": "red" if mk["strength"] > 7 else "yellow",
            "size_mm": mk["length_mm"], "depth_mm": None,
            "box": [int(max(0, cx - half)), int(max(0, cy - half)), int(min(w - 1, cx + half)), int(min(h - 1, cy + half))],
        })
    return out


def render(view_img, pad, findings, out_dir, slot, ppi):
    """Write the whole-card map, corner tiles, edge strips and per-finding zooms. Returns their metadata.

    view_img is the straightened card with `pad` px of real background on every side, so every close-up
    shows a little past the card's edge. Finding boxes are in card coordinates and shifted by `pad` here.
    Boxes are drawn after each view is scaled, so even a 0.1 mm finding gets a clearly visible box.
    """
    canon = view_img
    H, W = view_img.shape[:2]
    w, h = W - 2 * pad, H - 2 * pad  # the card itself
    shifted = [{**f, "box": [f["box"][0] + pad, f["box"][1] + pad, f["box"][2] + pad, f["box"][3] + pad]} for f in findings]
    ordered = sorted(shifted, key=lambda f: _sev_rank(f["severity"]))

    def status(rect):
        x0, y0, x1, y1 = rect
        sev = [f["severity"] for f in shifted
               if not (f["box"][2] < x0 or f["box"][0] > x1 or f["box"][3] < y0 or f["box"][1] > y1)]
        return max(sev, key=_sev_rank) if sev else "green"

    def view(name, rect, width, rot=None, frame=None, thick=3, min_box=14):
        x0, y0, x1, y1 = rect
        img = canon[y0:y1, x0:x1]
        ch_, cw_ = img.shape[:2]
        if rot == "flip":
            img = img[::-1]
        elif rot == "cw":
            img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        elif rot == "ccw":
            img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        k = width / img.shape[1]
        img = np.ascontiguousarray(cv2.resize(img, (width, max(1, int(round(img.shape[0] * k)))), interpolation=cv2.INTER_AREA))

        def tf(x, y):
            x, y = x - x0, y - y0
            if rot == "flip":
                y = ch_ - 1 - y
            elif rot == "cw":
                x, y = ch_ - 1 - y, x
            elif rot == "ccw":
                x, y = y, cw_ - 1 - x
            return x * k, y * k

        for f in ordered:
            bx0, by0, bx1, by1 = f["box"]
            if bx1 < x0 or bx0 > x1 or by1 < y0 or by0 > y1:
                continue
            (ax, ay), (bx, by) = tf(bx0, by0), tf(bx1, by1)
            lx, hx, ly, hy = min(ax, bx), max(ax, bx), min(ay, by), max(ay, by)
            cx, cy = (lx + hx) / 2, (ly + hy) / 2
            half_w, half_h = max((hx - lx) / 2, min_box / 2), max((hy - ly) / 2, min_box / 2)
            cv2.rectangle(img, (int(cx - half_w), int(cy - half_h)), (int(cx + half_w), int(cy + half_h)),
                          RED if f["severity"] == "red" else YELLOW, thick)
        if frame:
            img = cv2.copyMakeBorder(img, 6, 6, 6, 6, cv2.BORDER_CONSTANT,
                                     value={"red": RED, "yellow": YELLOW, "green": GREEN}[frame])
        path = out_dir / f"{slot}_cu_{name}.jpg"
        cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return path.name

    result = {"full": view("full", (0, 0, W, H), 700, thick=4, min_box=22), "corners": {}, "edges": {}, "findings": []}

    c = int(0.32 * ppi)  # corner tile size on the card; each tile also shows the margin beyond the corner
    for name, rect in {"top_left": (0, 0, pad + c, pad + c), "top_right": (W - pad - c, 0, W, pad + c),
                       "bottom_left": (0, H - pad - c, pad + c, H), "bottom_right": (W - pad - c, H - pad - c, W, H)}.items():
        st = status(rect)
        result["corners"][name] = {"img": view(f"corner_{name}", rect, 360, frame=st), "status": st}

    depth = pad + int(0.15 * ppi)  # margin beyond the edge + 0.15 in of card
    # Full length of each side, corner to corner, plus the margin beyond both ends.
    strips = {"top": ((0, 0, W, depth), None), "bottom": ((0, H - depth, W, H), "flip"),
              "left": ((0, 0, depth, H), "cw"), "right": ((W - depth, 0, W, H), "ccw")}
    for side, (rect, rot) in strips.items():
        st = status(rect)
        result["edges"][side] = {"img": view(f"edge_{side}", rect, 1200, rot=rot, frame=st), "status": st}

    zoom = int(0.12 * ppi)
    ranked = sorted(range(len(findings)), key=lambda i: -_sev_rank(findings[i]["severity"]))
    for n, i in enumerate(ranked):
        x0, y0, x1, y1 = shifted[i]["box"]
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        half = max(zoom, (x1 - x0) // 2 + int(0.03 * ppi), (y1 - y0) // 2 + int(0.03 * ppi))
        rect = (max(0, cx - half), max(0, cy - half), min(W, cx + half), min(H, cy + half))
        result["findings"].append({**findings[i], "img": view(f"find_{n}", rect, 240, frame=findings[i]["severity"], min_box=20)})
    return result
