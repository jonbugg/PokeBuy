"""Measure a card image: find the card, straighten it, then measure centering, edges, corners.

The card is straightened at the scan's own resolution (600 or 1200 px per inch), so a finer scan
gives finer measurements. All thresholds are in millimetres and converted per scan.
"""

from dataclasses import dataclass, field

import cv2
import numpy as np

DEFAULT_PPI = 600  # used for photos and other images without a known scan resolution
CARD_W_IN, CARD_H_IN = 2.5, 3.5
VIEW_MARGIN_IN = 0.08  # background kept around the card for close-ups, so the edge itself is visible


class CardNotFound(Exception):
    pass


@dataclass
class Measurement:
    canon: np.ndarray
    mask: np.ndarray
    corners_src: np.ndarray
    background_dark: bool
    ppi: int
    dims_in: tuple = None
    centering: dict = field(default_factory=dict)
    edges: dict = field(default_factory=dict)
    corners: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    edges_reliable: bool = False
    canon_view: np.ndarray = None   # straightened card plus VIEW_MARGIN_IN of background on every side
    view_pad: int = 0

    @property
    def cw(self):
        return int(CARD_W_IN * self.ppi)

    @property
    def ch(self):
        return int(CARD_H_IN * self.ppi)

    @property
    def mmpp(self):
        return 25.4 / self.ppi

    @property
    def pad(self):
        return int(0.05 * self.ppi)

    def px(self, mm):
        return mm / self.mmpp


def load(path_or_bytes) -> np.ndarray:
    if isinstance(path_or_bytes, (bytes, bytearray)):
        img = cv2.imdecode(np.frombuffer(path_or_bytes, np.uint8), cv2.IMREAD_COLOR)
    else:
        img = cv2.imread(str(path_or_bytes), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not read image")
    return img


# ---------- finding and straightening the card ----------

def _card_mask(img, scanned=True):
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    h, w = lab.shape[:2]
    b = max(4, int(min(h, w) * 0.02))
    frame = np.concatenate([lab[:b].reshape(-1, 3), lab[-b:].reshape(-1, 3),
                            lab[:, :b].reshape(-1, 3), lab[:, -b:].reshape(-1, 3)])
    dark = frame[:, 0] < 110
    # A frame that's mostly black (scan guide) but catches some white paper at a corner: trust the black.
    bg = np.median(frame[dark], axis=0) if dark.mean() > 0.4 else np.median(frame, axis=0)
    # Card = anything clearly more colourful than the background, or clearly lighter/darker.
    # Fixed rules rather than Otsu: Otsu splits on the card's own artwork when it has both bright and
    # dark areas (a dark-blue back with a bright Poké Ball), and the scan guide's two sheets are
    # slightly different blacks that must both count as background.
    chroma_dist = np.hypot(lab[..., 1] - bg[1], lab[..., 2] - bg[2])
    # On a black background nothing on the card is darker than the background, and the guide's cover
    # sheet can be a slightly deeper black than the frame, so only count lighter pixels there.
    light_dist = (lab[..., 0] - bg[0]) if bg[0] < 110 else np.abs(lab[..., 0] - bg[0])
    m = ((chroma_dist > 10) | (light_dist > 28)).astype(np.uint8) * 255
    if not scanned:
        # Photos (e.g. TAG slab shots) have reflections that pass the fixed rules; Otsu copes better there.
        dist8 = np.clip(np.linalg.norm(lab - bg, axis=2) * 2, 0, 255).astype(np.uint8)
        _, m = cv2.threshold(dist8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    k = max(3, int(min(h, w) * 0.004)) | 1
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((k * 3, k * 3), np.uint8))
    return m, bg[0] < 80  # OpenCV 8-bit L runs 0..255


def _find_card_contour(mask, src_ppi=None):
    # RETR_LIST so a card inside another outline (e.g. the scan guide's cut edge) is still found.
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    h, w = mask.shape
    best = None
    for c in contours:
        area = cv2.contourArea(c)
        if area < 0.03 * h * w:
            continue
        (_, _), (rw, rh), _ = cv2.minAreaRect(c)
        if min(rw, rh) == 0:
            continue
        aspect = min(rw, rh) / max(rw, rh)
        fill = area / (rw * rh)
        if not (0.62 <= aspect <= 0.80 and fill > 0.93):
            continue
        if src_ppi and not (2.2 <= min(rw, rh) / src_ppi <= 2.8 and 3.2 <= max(rw, rh) / src_ppi <= 3.8):
            continue
        # A card's printed border makes the band just inside its outline solid; an outline such as
        # the guide's cut edge is only a thin line with black inside it.
        inside = np.zeros_like(mask)
        cv2.drawContours(inside, [c], -1, 255, thickness=cv2.FILLED)
        band_px = max(3, int(min(rw, rh) * 0.02))  # ~1.3 mm on a card
        core = cv2.erode(inside, np.ones((2 * band_px + 1, 2 * band_px + 1), np.uint8))
        ring = (inside > 0) & (core == 0)
        if (mask[ring] > 0).mean() < 0.8:
            continue
        if best is None or area > best[0]:
            best = (area, c)
    if best is None:
        raise CardNotFound("Couldn't find a card-shaped object. Check the card is fully inside the scan area.")
    return best[1]


def _side_lines(pts):
    """Fit a straight line to each side of the contour, ignoring the rounded corners."""
    rect = cv2.minAreaRect(pts.astype(np.float32))
    box = cv2.boxPoints(rect)
    center = np.array(rect[0])
    s, d = box.sum(1), np.diff(box, axis=1).ravel()
    tl, br = box[np.argmin(s)], box[np.argmax(s)]
    tr, bl = box[np.argmin(d)], box[np.argmax(d)]
    sides = {"top": (tl, tr), "right": (tr, br), "bottom": (br, bl), "left": (bl, tl)}
    lines = {}
    for name, (a, b) in sides.items():
        ab = b - a
        L = np.linalg.norm(ab)
        u = ab / L
        n = np.array([-u[1], u[0]])
        if np.dot(center - a, n) > 0:
            n = -n
        t = (pts - a) @ u
        off = (pts - a) @ n
        sel = (t > 0.15 * L) & (t < 0.85 * L) & (np.abs(off) < 0.05 * L)
        if sel.sum() < 20:
            raise CardNotFound("Card edges are unclear.")
        vx, vy, x0, y0 = cv2.fitLine(pts[sel].astype(np.float32), cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
        lines[name] = (np.array([x0, y0]), np.array([vx, vy]))
    return lines


def _intersect(l1, l2):
    (p, r), (q, s) = l1, l2
    A = np.array([r, -s]).T
    t = np.linalg.solve(A, q - p)
    return p + t[0] * r


def find_and_straighten(img, src_ppi=None):
    mask, dark_bg = _card_mask(img, scanned=bool(src_ppi))
    contour = _find_card_contour(mask, src_ppi)
    pts = contour.reshape(-1, 2).astype(np.float64)
    lines = _side_lines(pts)
    quad = np.array([
        _intersect(lines["top"], lines["left"]),
        _intersect(lines["top"], lines["right"]),
        _intersect(lines["bottom"], lines["right"]),
        _intersect(lines["bottom"], lines["left"]),
    ], dtype=np.float32)
    w_px = (np.linalg.norm(quad[1] - quad[0]) + np.linalg.norm(quad[2] - quad[3])) / 2
    h_px = (np.linalg.norm(quad[3] - quad[0]) + np.linalg.norm(quad[2] - quad[1])) / 2
    if w_px > h_px:  # card lying sideways: rotate corner order so the long side is vertical
        quad = np.roll(quad, -1, axis=0)
        w_px, h_px = h_px, w_px
    ppi = int(src_ppi) if src_ppi and src_ppi >= 500 else DEFAULT_PPI
    cw, ch, pad = int(CARD_W_IN * ppi), int(CARD_H_IN * ppi), int(0.05 * ppi)
    dst = np.array([[0, 0], [cw - 1, 0], [cw - 1, ch - 1], [0, ch - 1]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(quad, dst)
    canon = cv2.warpPerspective(img, M, (cw, ch), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    # Card mask in canonical space, with a margin so we can see the true edge outline.
    M_pad = cv2.getPerspectiveTransform(quad, dst + pad)
    cmask = cv2.warpPerspective(_solid_mask(mask, contour), M_pad, (cw + 2 * pad, ch + 2 * pad), flags=cv2.INTER_LINEAR)
    m = Measurement(canon=canon, mask=cmask, corners_src=quad, background_dark=bool(dark_bg), ppi=ppi)
    vp = int(VIEW_MARGIN_IN * ppi)
    M_view = cv2.getPerspectiveTransform(quad, dst + vp)
    m.canon_view = cv2.warpPerspective(img, M_view, (cw + 2 * vp, ch + 2 * vp), flags=cv2.INTER_CUBIC,
                                       borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
    m.view_pad = vp
    if src_ppi:
        m.dims_in = (round(float(w_px) / src_ppi, 3), round(float(h_px) / src_ppi, 3))
    return m


def _solid_mask(mask, contour):
    """The card's own outline, filled, so dark artwork can't punch holes and nothing else gets in."""
    solid = np.zeros_like(mask)
    cv2.drawContours(solid, [contour], -1, 255, thickness=cv2.FILLED)
    return solid


# ---------- centering ----------

def _border_width(lab_strip, min_px, max_px, hold):
    """lab_strip: positions-along-edge x depth, depth 0 is the card's outer edge.

    Returns (width_px, sharpness, ref_color). The inner border is the first depth at which
    most of the edge's length stops matching the border colour; small print inside the
    border (copyright lines, set codes) covers too little of the length to trigger it.
    """
    ref_zone = lab_strip[:, int(min_px * 0.4):int(min_px * 0.9)]
    ref = np.median(ref_zone.reshape(-1, 3), axis=0)
    dist = np.linalg.norm(lab_strip - ref, axis=2)
    noise = np.median(np.linalg.norm(ref_zone - ref, axis=2))
    thr = max(14.0, 6 * noise)
    frac = (dist > thr).mean(axis=0)
    frac = np.convolve(frac, np.ones(3) / 3, mode="same")
    for x in range(min_px, min(max_px, len(frac) - hold)):
        if frac[x] >= 0.6 and frac[x:x + hold].min() >= 0.5:
            x0 = x  # back up to the 50% crossing for sub-pixel accuracy
            while x0 > min_px and frac[x0 - 1] >= 0.5:
                x0 -= 1
            lo, hi = frac[x0 - 1], frac[x0]
            sub = x0 - 1 + (0.5 - lo) / (hi - lo) if hi > lo else float(x0)
            sharp = float(frac[min(x0 + hold, len(frac) - 1)] - frac[max(x0 - hold, 0)])
            return sub, sharp, ref
    return None, 0.0, ref


def measure_centering(m: Measurement):
    lab = cv2.cvtColor(m.canon, cv2.COLOR_BGR2LAB).astype(np.float32)
    min_px, max_px = int(0.035 * m.ppi), int(0.32 * m.ppi)
    hold = max(6, int(round(m.px(0.25))))
    a, b = int(0.08 * m.ch), int(0.92 * m.ch)
    c, d = int(0.10 * m.cw), int(0.90 * m.cw)
    depth = max_px + hold + 2
    strips = {
        "left": lab[a:b, :depth],
        "right": lab[a:b, ::-1][:, :depth],
        "top": lab[:depth, c:d].transpose(1, 0, 2),
        "bottom": lab[::-1][:depth, c:d].transpose(1, 0, 2),
    }
    widths, agreement, refs = {}, {}, {}
    for side, strip in strips.items():
        widths[side], agreement[side], refs[side] = _border_width(strip, min_px, max_px, hold)
    m._border_ref = refs
    if any(v is None for v in widths.values()):
        m.warnings.append("Couldn't find the inner border on every side (borderless or full-bleed art?).")
        m.centering = {"widths_mm": {k: (None if v is None else round(v * m.mmpp, 3)) for k, v in widths.items()}}
        return m.centering
    L, R, T, B = widths["left"], widths["right"], widths["top"], widths["bottom"]
    lr = 100 * L / (L + R)
    tb = 100 * T / (T + B)
    conf = min(agreement.values())
    if conf < 0.5:
        m.warnings.append("Border detection was inconsistent on at least one side; centering is approximate.")
    m.centering = {
        "lr": round(lr, 2), "tb": round(tb, 2),
        "worst": round(max(abs(lr - 50), abs(tb - 50)) + 50, 2),
        "widths_mm": {k: round(v * m.mmpp, 3) for k, v in widths.items()},
        "confidence": round(conf, 2),
    }
    return m.centering


# ---------- edges and corners ----------
#
# Works on the card's real outline in straightened coordinates. Every scan shows a thin bright rim at
# the cut edge (paper core + scanner sharpening), so whitening is judged *relative to this card's own
# rim*: a spot where the rim gets wider than usual along that edge. Chips/dents are where the outline
# dips inside the ideal rounded rectangle.

CORNER_NAMES = ("top_left", "top_right", "bottom_left", "bottom_right")
RIM_DEPTH_MM = 0.68     # how far inward to sample from the outline
CHIP_MM = 0.15          # outline dip that counts as a chip...
CHIP_MIN_MM = 0.25      # ...sustained along the edge for at least this long
RIM_EXTRA_MM = 0.106    # pale rim this much deeper than the edge's typical rim = whitening...
SPOT_MIN_MM = 0.3       # ...for at least this long


def _outline(m: Measurement):
    contours, _ = cv2.findContours((m.mask > 127).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    return max(contours, key=cv2.contourArea).reshape(-1, 2).astype(np.float64) - m.pad


def _rounded_rect_sdist(p, r, cw, ch):
    """Signed distance from points to the ideal card outline; positive = inside the card."""
    x, y = p[:, 0], p[:, 1]
    cx = np.clip(x, r, cw - 1 - r)
    cy = np.clip(y, r, ch - 1 - r)
    in_corner = (np.abs(x - cx) > 0) & (np.abs(y - cy) > 0)
    d_corner = r - np.hypot(x - cx, y - cy)
    d_side = np.minimum.reduce([x, cw - 1 - x, y, ch - 1 - y])
    return np.where(in_corner, d_corner, d_side)


def _fit_radius(m, pts):
    best_r, best_err = None, None
    for r_mm in np.arange(1.5, 4.01, 0.05):
        r = m.px(r_mm)
        near = ((pts[:, 0] < r) | (pts[:, 0] > m.cw - 1 - r)) & ((pts[:, 1] < r) | (pts[:, 1] > m.ch - 1 - r))
        if near.sum() < 20:
            continue
        err = np.median(np.abs(_rounded_rect_sdist(pts[near], r, m.cw, m.ch)))
        if best_err is None or err < best_err:
            best_r, best_err = r, err
    return best_r or m.px(2.6)


def _classify(m, pts, r):
    """Label each outline point with a side name or a corner name."""
    x, y = pts[:, 0], pts[:, 1]
    zone = r * 1.15
    left, right = x < zone, x > m.cw - 1 - zone
    top, bottom = y < zone, y > m.ch - 1 - zone
    d = np.stack([x, m.cw - 1 - x, y, m.ch - 1 - y], axis=1)
    labels = np.array(["left", "right", "top", "bottom"], dtype=object)[d.argmin(axis=1)]
    labels[top & left] = "top_left"
    labels[top & right] = "top_right"
    labels[bottom & left] = "bottom_left"
    labels[bottom & right] = "bottom_right"
    return labels


def _rim_widths(m, lab, pts, refs, labels):
    """For each outline point, how many px inward until the colour settles to the border colour."""
    n = len(pts)
    k = max(6, int(round(m.px(0.25))))
    samples_n = int(round(m.px(RIM_DEPTH_MM)))
    tang = pts[(np.arange(n) + k) % n] - pts[(np.arange(n) - k) % n]
    tang /= np.linalg.norm(tang, axis=1, keepdims=True) + 1e-9
    normal = np.stack([-tang[:, 1], tang[:, 0]], axis=1)
    centre = np.array([m.cw / 2, m.ch / 2])
    normal[np.sum(normal * (centre - pts), axis=1) < 0] *= -1
    t = np.arange(samples_n, dtype=np.float32)
    sx = (pts[:, 0:1] + normal[:, 0:1] * t).astype(np.float32)
    sy = (pts[:, 1:2] + normal[:, 1:2] * t).astype(np.float32)
    samples = cv2.remap(lab, sx, sy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)  # n x T x 3
    side_of = {"top_left": "top", "top_right": "top", "bottom_left": "bottom", "bottom_right": "bottom"}
    ref = np.array([refs[side_of.get(l, l)] for l in labels], dtype=np.float32)
    # Count only pale pixels (lighter and less colourful than the border): that's whitening.
    # Dark specks or print detail near the edge change the colour too, but aren't wear.
    ref_chroma = np.hypot(ref[:, 1] - 128, ref[:, 2] - 128)[:, None]
    chroma = np.hypot(samples[..., 1] - 128, samples[..., 2] - 128)
    lighter = samples[..., 0] - ref[:, None, 0]
    pale = np.where(ref_chroma > 20, (lighter > 12) & (chroma < ref_chroma * 0.7), lighter > 25)
    return pale.sum(axis=1).astype(np.float32)


def _whitening_runs(m, rim_px, typical):
    return _runs(rim_px > typical + m.px(RIM_EXTRA_MM), min_len=max(2, int(round(m.px(SPOT_MIN_MM)))))


def measure_edges_corners(m: Measurement):
    lab = cv2.cvtColor(m.canon, cv2.COLOR_BGR2LAB).astype(np.float32)
    pts = _outline(m)
    r = _fit_radius(m, pts)
    labels = _classify(m, pts, r)
    sd = _rounded_rect_sdist(pts, r, m.cw, m.ch)
    refs = getattr(m, "_border_ref", None) or {}
    if len(refs) < 4:
        med = np.median(lab[int(0.1 * m.ppi):int(0.12 * m.ppi), :].reshape(-1, 3), axis=0)
        refs = {s: refs.get(s, med) for s in ("top", "bottom", "left", "right")}
    rim = _rim_widths(m, lab, pts, refs, labels)

    m.edges, m.corners = {}, {}
    side_typical = {}
    for side in ("top", "bottom", "left", "right"):
        sel = labels == side
        dev = sd[sel]
        base = _rolling_median(dev, int(0.3 * m.ppi))
        dent_mm = np.clip(dev - base, 0, None) * m.mmpp
        chips = _runs(dent_mm > CHIP_MM, min_len=max(2, int(round(m.px(CHIP_MIN_MM)))))
        rw = rim[sel]
        typical = float(np.median(rw)) if len(rw) else 0.0
        side_typical[side] = typical
        spots = _whitening_runs(m, rw, typical)
        m.edges[side] = {
            "max_chip_mm": round(float(dent_mm.max()), 3) if len(dent_mm) else 0.0,
            "chip_count": len(chips),
            "chip_len_mm": round(sum(e - s for s, e in chips) * m.mmpp, 2),
            "whitening_pct": round(100 * float((rw > typical + m.px(RIM_EXTRA_MM)).mean()), 2) if len(rw) else 0.0,
            "whitening_spots": len(spots),
            "rim_mm": round(typical * m.mmpp, 3),
        }
    for name in CORNER_NAMES:
        sel = labels == name
        dev_mm = sd[sel] * m.mmpp
        typical = side_typical["top" if name.startswith("top") else "bottom"]
        white = rim[sel] > typical + m.px(RIM_EXTRA_MM)
        m.corners[name] = {
            "missing_pct": round(100 * float((dev_mm > 0.12).mean()), 2) if sel.any() else 0.0,
            "bulge_pct": round(100 * float((dev_mm < -0.12).mean()), 2) if sel.any() else 0.0,
            "max_dev_mm": round(float(np.abs(dev_mm).max()), 3) if sel.any() else 0.0,
            "whitening_pct": round(100 * float(white.mean()), 1) if sel.any() else 0.0,
        }
    m.corners["_radius_mm"] = round(r * m.mmpp, 3)
    m._outline = (pts, labels, rim, side_typical)
    m._sd = sd
    return m.edges, m.corners


def _rolling_median(x, win):
    if len(x) == 0:
        return x
    win = max(3, win | 1)
    padded = np.pad(x, win // 2, mode="edge")
    view = np.lib.stride_tricks.sliding_window_view(padded, win)
    return np.median(view, axis=1)


def _runs(flags, min_len=2):
    runs, start = [], None
    for i, f in enumerate(flags):
        if f and start is None:
            start = i
        elif not f and start is not None:
            if i - start >= min_len:
                runs.append((start, i))
            start = None
    if start is not None and len(flags) - start >= min_len:
        runs.append((start, len(flags)))
    return runs


def overlay(m: Measurement) -> np.ndarray:
    """Draw what was measured on the straightened card."""
    out = m.canon.copy()
    s = m.ppi / 600
    thick = max(2, int(3 * s))
    w = m.centering.get("widths_mm") or {}
    px = {k: (None if v is None else int(round(m.px(v)))) for k, v in w.items()}
    cyan = (255, 255, 0)
    if px.get("left") is not None:
        cv2.line(out, (px["left"], 0), (px["left"], m.ch), cyan, thick)
    if px.get("right") is not None:
        cv2.line(out, (m.cw - 1 - px["right"], 0), (m.cw - 1 - px["right"], m.ch), cyan, thick)
    if px.get("top") is not None:
        cv2.line(out, (0, px["top"]), (m.cw, px["top"]), cyan, thick)
    if px.get("bottom") is not None:
        cv2.line(out, (0, m.ch - 1 - px["bottom"]), (m.cw, m.ch - 1 - px["bottom"]), cyan, thick)
    box = int(0.25 * m.ppi)
    for name, (x, y) in {"top_left": (0, 0), "top_right": (m.cw - box, 0),
                         "bottom_left": (0, m.ch - box), "bottom_right": (m.cw - box, m.ch - box)}.items():
        c = m.corners.get(name, {})
        bad = c.get("missing_pct", 0) >= 3 or c.get("whitening_pct", 0) >= 10
        cv2.rectangle(out, (x, y), (x + box, y + box), (0, 0, 255) if bad else (0, 200, 0), int(4 * s))
    if getattr(m, "_outline", None) is not None:
        pts, labels, rim, side_typical = m._outline
        for side in ("top", "bottom", "left", "right"):
            sel = np.where(labels == side)[0]
            for a, b in _whitening_runs(m, rim[sel], side_typical[side]):
                x, y = pts[sel[(a + b) // 2]]
                cv2.circle(out, (int(x), int(y)), int(34 * s), (0, 0, 255), int(5 * s))
    return out


def measure_image(img, src_ppi=None) -> Measurement:
    m = find_and_straighten(img, src_ppi=src_ppi)
    m.edges_reliable = bool(src_ppi and src_ppi >= 500)
    if not m.edges_reliable:
        m.warnings.append("Not a 600+ dpi scan: centering only. Corners and edges need a scanner image.")
    elif not m.background_dark:
        m.warnings.append("Light background detected. Put black paper behind the card for accurate edge and corner checks.")
    measure_centering(m)
    measure_edges_corners(m)
    return m
