"""Measure a card image: find the card, straighten it, then measure centering, edges, corners.

The card is straightened at the scan's own resolution (600 or 1200 px per inch), so a finer scan
gives finer measurements. All thresholds are in millimetres and converted per scan.
"""

from dataclasses import dataclass, field

import cv2
import numpy as np

DEFAULT_PPI = 600  # used for photos and other images without a known scan resolution
CARD_W_IN, CARD_H_IN = 2.5, 3.5
VIEW_MARGIN_IN = 0.16  # ~4 mm of background kept around the card, so the edge itself is visible


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

def window_backdrop(lab, edge_bg):
    """The backdrop right around the card when it differs from the scan's edge, e.g. the grey cover seen
    through the black frame's window: the most common neutral colour that isn't the edge colour."""
    neutral = (np.hypot(lab[..., 1] - 128, lab[..., 2] - 128) < 6) & (np.abs(lab[..., 0] - edge_bg[0]) > 30)
    if neutral.mean() < 0.1:
        return None
    vals = lab[..., 0][neutral]
    hist, edges = np.histogram(vals, bins=64, range=(0, 256))
    i = int(np.argmax(hist))
    near = neutral & (np.abs(lab[..., 0] - (edges[i] + edges[i + 1]) / 2) < 12)
    return np.median(lab[near], axis=0)


def _card_mask(img, scanned=True, bg=None):
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    h, w = lab.shape[:2]
    if bg is None:
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
    # On the guide's printed black (L ~65-75) a card is either lighter/more colourful, or - for
    # black-bordered cards - a much deeper black (L ~15-30). The guide's two sheets differ by only a few
    # levels and faint shadows along the card's edge by a little more, so "darker" needs a wide margin.
    if np.hypot(bg[1] - 128, bg[2] - 128) > 25:
        # A coloured guide (e.g. orange or magenta, like TAG's orange backdrop): nothing on a card's border
        # shares its colour, so "different colour or clearly different lightness" separates the card,
        # whatever its border - black, silver, white, yellow or the blue back.
        m = (chroma_dist > 16) | (np.abs(lab[..., 0] - bg[0]) > 40)
    elif bg[0] < 110:
        m = (chroma_dist > 10) | (lab[..., 0] - bg[0] > 28)
    elif bg[0] < 190:
        # Grey guide: the card's shadow beside its edge is darker than the grey, so "darker" needs a wide
        # margin. A black border (L ~20-45) still clears it easily against the grey (~150).
        m = (chroma_dist > 10) | (lab[..., 0] - bg[0] > 28) | (bg[0] - lab[..., 0] > 60)
    else:
        m = (chroma_dist > 10) | (np.abs(lab[..., 0] - bg[0]) > 28)
    m = m.astype(np.uint8) * 255
    if not scanned:
        # Photos (e.g. TAG slab shots) have reflections that pass the fixed rules; Otsu copes better there.
        dist8 = np.clip(np.linalg.norm(lab - bg, axis=2) * 2, 0, 255).astype(np.uint8)
        _, m = cv2.threshold(dist8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    k = max(3, int(min(h, w) * 0.004)) | 1
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((k * 3, k * 3), np.uint8))
    return m, float(bg[0]), np.asarray(bg, np.float32)  # backdrop lightness (OpenCV 8-bit L) and colour


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
        lines[name] = (np.array([x0, y0]), np.array([vx, vy]), pts[sel], L)
    return _square_up(lines)


def _square_up(lines):
    """Repair a side whose fit was pulled off by artwork, using the opposite side's angle.

    Fitting each side on its own lets artwork that matches the backdrop (a silver swoosh along the top
    of a black-bordered card on the grey guide) tilt that side by a degree or more, which skews the whole
    straightened image. Opposite sides of a card are parallel, and the scanner's own slight skew (about
    0.35 degrees between its across and along directions on the ENVY) affects both equally, so top must match
    bottom and left must match right. When a pair disagrees, the side whose points hug its line less
    is redrawn at its partner's angle, placed at the median of its own edge points.
    """
    info = {}
    for name, (p, v, sel, L) in lines.items():
        n = np.array([-v[1], v[0]])
        inl = float((np.abs((sel - p) @ n) < 0.002 * L).mean())  # share of points hugging the line
        info[name] = (np.arctan2(v[1], v[0]), inl)
    out = {name: (p, v) for name, (p, v, sel, L) in lines.items()}
    for a_name, b_name in (("top", "bottom"), ("left", "right")):
        diff = (info[a_name][0] - info[b_name][0] + np.pi / 2) % np.pi - np.pi / 2
        if abs(diff) < np.deg2rad(0.3):
            continue
        bad, good = (a_name, b_name) if info[a_name][1] < info[b_name][1] else (b_name, a_name)
        d = lines[good][1] / np.linalg.norm(lines[good][1])
        n = np.array([-d[1], d[0]])
        out[bad] = (n * float(np.median(lines[bad][2] @ n)), d)
    return out


def _intersect(l1, l2):
    (p, r), (q, s) = l1, l2
    A = np.array([r, -s]).T
    t = np.linalg.solve(A, q - p)
    return p + t[0] * r


def _trace_dark_card(img, ppi):
    """Outline of a dark (e.g. black-bordered) card on the guide's black backdrop.

    Brightness alone can't separate a black border from the backdrop and the shadow beside the card,
    but every card shows a thin bright line where the scanner catches its cut edge. Find the card
    roughly from that line, then at many points around it look across the edge (±3 mm) for the
    brightest pixel: inside that band is the dark border, outside is backdrop/shadow, so the peak is
    the edge itself.
    """
    L = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)[..., 0].astype(np.float32)
    rim = cv2.morphologyEx((L > 105).astype(np.uint8) * 255, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    contours, _ = cv2.findContours(rim, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    rough = None
    for c in contours:
        (cx, cy), (rw, rh), ang = cv2.minAreaRect(c)
        if 2.3 < min(rw, rh) / ppi < 2.7 and 3.3 < max(rw, rh) / ppi < 3.7:
            if rough is None or rw * rh > rough[1][0] * rough[1][1]:
                rough = ((cx, cy), (rw, rh), ang)
    if rough is None:
        raise CardNotFound("Couldn't find a card-shaped object. Check the card is fully inside the scan area.")
    (cx, cy), (rw, rh), ang = rough
    if rw > rh:  # make the long side the local y axis
        rw, rh, ang = rh, rw, ang + 90
    th = np.deg2rad(ang)
    ux, vy = np.array([np.cos(th), np.sin(th)]), np.array([-np.sin(th), np.cos(th)])
    hw, hh, r = rw / 2, rh / 2, 3.0 / 25.4 * ppi
    # sample the ideal rounded rectangle every ~0.2 mm, with outward normals
    step = 0.2 / 25.4 * ppi
    pts, normals = [], []
    straight = [((-hw + r, -hh), (hw - r, -hh), (0, -1)), ((hw, -hh + r), (hw, hh - r), (1, 0)),
                ((hw - r, hh), (-hw + r, hh), (0, 1)), ((-hw, hh - r), (-hw, -hh + r), (-1, 0))]
    centres = [(hw - r, -hh + r, -np.pi / 2, 0), (hw - r, hh - r, 0, np.pi / 2), (-hw + r, hh - r, np.pi / 2, np.pi), (-hw + r, -hh + r, np.pi, 1.5 * np.pi)]
    for (a, b, n), (ccx, ccy, t0, t1) in zip(straight, centres):
        length = np.hypot(b[0] - a[0], b[1] - a[1])
        for t in np.linspace(0, 1, max(2, int(length / step)), endpoint=False):
            pts.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)); normals.append(n)
        for t in np.linspace(t0, t1, max(2, int(r * (t1 - t0) / step)), endpoint=False):
            pts.append((ccx + r * np.cos(t), ccy + r * np.sin(t))); normals.append((np.cos(t), np.sin(t)))
    pts, normals = np.array(pts), np.array(normals)
    to_img = lambda p: np.array([cx, cy]) + p[..., :1] * ux + p[..., 1:2] * vy
    search = np.linspace(-3.0, 3.0, int(6.0 / 25.4 * ppi)) / 25.4 * ppi  # outward offsets in px
    sample = pts[:, None, :] + normals[:, None, :] * search[None, :, None]
    xy = to_img(sample).astype(np.float32)
    prof = cv2.remap(L, xy[..., 0], xy[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    prof = cv2.GaussianBlur(prof, (1, 5), 0)[:, ::-1]  # now ordered outside -> inside
    after = max(4, int(0.5 / 25.4 * ppi))  # the card's dark border must follow the edge line
    n_s = prof.shape[1]
    off = np.full(len(prof), np.nan)
    for i, row in enumerate(prof):
        bright = np.where(row > 95)[0]
        for j in bright:
            if j + after < n_s and row[j + 2:j + after].mean() < 60:
                k = j + int(np.argmax(row[j:j + 4]))  # the line's peak
                off[i] = search[::-1][k]
                break
    ok = ~np.isnan(off)
    if ok.mean() < 0.6:
        raise CardNotFound("Couldn't trace this card's edge. Try the scan again.")
    idx = np.arange(len(off))
    off = np.interp(idx, idx[ok], off[ok], period=len(off))
    # drop points that jump away from their neighbours (sparkle in a holo border), then fill and smooth
    win = max(5, int(1.0 / 0.2))
    local = np.median(np.stack([np.roll(off, k) for k in range(-win, win + 1)]), axis=0)
    good = np.abs(off - local) < 0.25 / 25.4 * ppi
    off = np.interp(idx, idx[good], off[good], period=len(off))
    off = np.median(np.stack([np.roll(off, k) for k in (-2, -1, 0, 1, 2)]), axis=0)
    edge = to_img(pts + normals * off[:, None])
    return np.round(edge).astype(np.int32).reshape(-1, 1, 2)


def find_and_straighten(img, src_ppi=None):
    mask, bg_light, bg_lab = _card_mask(img, scanned=bool(src_ppi))
    dark_bg = bg_light < 80
    traced = False
    if src_ppi and np.hypot(bg_lab[1] - 128, bg_lab[2] - 128) <= 25:
        # Coloured paper behind the card inside a black/grey guide frame: the scan's edge shows the frame,
        # but the card sits on the paper. Use the paper's colour when it fills a good part of the scan.
        from .locate import _paper_colour
        small = cv2.resize(img, None, fx=0.1, fy=0.1, interpolation=cv2.INTER_AREA)
        paper = _paper_colour(small)
        if paper is not None:
            p_mask, p_light, p_lab = _card_mask(img, scanned=True, bg=paper)
            try:
                contour = _find_card_contour(p_mask, src_ppi)
                mask, bg_light, bg_lab, dark_bg = p_mask, p_light, p_lab, False
            except CardNotFound:
                pass
    try:
        if "contour" not in locals():
            contour = _find_card_contour(mask, src_ppi)
    except CardNotFound:
        # Mixed guide (e.g. black frame with the grey cover in the window): retry against the colour
        # actually around the card.
        alt = window_backdrop(cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32), [bg_light]) if src_ppi else None
        contour = None
        if alt is not None:
            alt_mask, alt_light, alt_lab = _card_mask(img, scanned=True, bg=alt)
            try:
                contour = _find_card_contour(alt_mask, src_ppi)
                mask, bg_light, dark_bg, bg_lab = alt_mask, alt_light, alt_light < 80, alt_lab
            except CardNotFound:
                contour = None
        if contour is None:
            if not (src_ppi and dark_bg):
                raise
            contour = _trace_dark_card(img, src_ppi)  # black-bordered card on the black guide
            traced = True
            mask = np.zeros(mask.shape, np.uint8)
            cv2.drawContours(mask, [contour], -1, 255, cv2.FILLED)
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
    # A card is convex: inward notches in the detected outline come from artwork that matches the
    # backdrop (e.g. silver foil on the grey guide). Use the hull for geometry; real edge chips are found
    # directly in the image instead (closeups._edge_depths), and corner wear still pulls the hull inward.
    cmask = cv2.warpPerspective(_solid_mask(mask, cv2.convexHull(contour)), M_pad, (cw + 2 * pad, ch + 2 * pad), flags=cv2.INTER_LINEAR)
    # "background_dark" really means "a proper backdrop": the black or grey guide, not white paper or the lid.
    m = Measurement(canon=canon, mask=cmask, corners_src=quad, background_dark=bool(bg_light < 190), ppi=ppi)
    m.bg_light = bg_light
    m.bg_lab = bg_lab
    m.dark_card = traced
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


def _border_width_slices(lab_strip, min_px, max_px, hold, slice_px, settle_px=None):
    """lab_strip: positions-along-edge x depth, depth 0 is the card's outer edge.

    Finds where the border ends separately in each ~1 mm slice along the edge, then keeps the slices
    that agree. Artwork that cuts into the border (a silver swoosh, a full-art card's busy edge, a
    copyright line) only spoils the slices it touches, instead of dragging the whole edge's answer.
    Returns (width_px, agreement 0..1, border colour).
    """
    n = lab_strip.shape[0] // slice_px
    if n < 6:
        return None, 0.0, None
    prof = lab_strip[:n * slice_px].reshape(n, slice_px, -1, 3).mean(axis=1)  # slices x depth x 3
    prof = cv2.GaussianBlur(prof, (3, 1), 0)
    # The border's colour, sampled away from the cut edge (which carries shading, glare and blur).
    z0, z1 = int(min_px * 0.5), int(min_px * 0.95)
    refs = np.median(prof[:, z0:z1], axis=1)                      # each slice's border colour
    side_ref = np.median(refs, axis=0)
    # How much the border itself varies along this side (glare streaks, holo sparkle).
    side_noise = np.median(np.linalg.norm(prof[:, z0:z1] - side_ref, axis=2))
    widths = np.full(n, np.nan)
    for i in range(n):
        if np.linalg.norm(refs[i] - side_ref) > 18:               # artwork where the border should be
            continue
        dist = np.linalg.norm(prof[i] - refs[i], axis=1)
        noise = np.median(np.abs(dist[z0:z1] - np.median(dist[z0:z1]))) * 1.48
        thr = max(10.0, 5 * noise, 2.5 * side_noise)
        settle = settle_px or hold
        for x in range(min_px, min(max_px, len(dist) - settle)):
            # The art boundary stays changed; a line of small print inside the border (copyright, set
            # code) is ~1 mm tall and mostly gaps between letters, so it doesn't.
            if dist[x] > thr and dist[x:x + hold].min() > 0.6 * thr and (dist[x:x + settle] > 0.6 * thr).mean() >= 0.8:
                inner = float(np.median(dist[x:x + hold]))
                target = inner / 2                                 # half-way into the change = the edge
                x0 = x
                while x0 > min_px and dist[x0 - 1] > target:
                    x0 -= 1
                lo, hi = dist[x0 - 1], dist[x0]
                widths[i] = x0 - 1 + ((target - lo) / (hi - lo) if hi > lo else 1.0)
                break
    good = widths[~np.isnan(widths)]
    good = good[good > min_px + 2]                                 # "changed at once" = the colour sample was off
    if len(good) < max(4, 0.2 * n):
        return None, len(good) / n, side_ref
    med = np.median(good)
    tol = max(2.0, 0.15 * min_px)                                  # ~0.15 mm at 1200 dpi
    keep = good[np.abs(good - med) <= tol]
    if len(keep) < max(4, 0.2 * n):
        return None, len(keep) / n, side_ref
    return float(np.mean(keep)), len(keep) / n, side_ref


def _line_depth(lab_strip, min_px, max_px, slice_px, settle_px):
    """Where a long straight line runs parallel to the edge between min_px and max_px deep.

    The border's inner edge is printed as one straight line along the whole side. Even where it barely
    changes colour (a black holo border against dark art), it is a change at the *same depth* in every
    slice, while artwork changes land at random depths. Score each depth by the median, over ~1 mm
    slices, of how sharply that slice changes there (scaled by the slice's own noise), then take the
    first strong peak that isn't just a line of small print (after which the border colour returns).
    Returns (depth_px or None, strength).
    """
    n = lab_strip.shape[0] // slice_px
    if n < 6:
        return None, 0.0
    prof = lab_strip[:n * slice_px].reshape(n, slice_px, -1, 3).mean(axis=1)
    prof = cv2.GaussianBlur(prof, (3, 1), 0)
    g = np.linalg.norm(prof[:, 2:] - prof[:, :-2], axis=2)          # slices x (depth-2), centred at x+1
    g = np.pad(g, ((0, 0), (1, 1)))
    lo, hi = min_px, min(max_px, g.shape[1] - settle_px - 1)
    if hi <= lo + 4:
        return None, 0.0
    mad = np.median(np.abs(g[:, lo:hi] - np.median(g[:, lo:hi], axis=1, keepdims=True)), axis=1, keepdims=True) * 1.48 + 0.5
    z = (g - np.median(g[:, lo:hi], axis=1, keepdims=True)) / mad
    score = np.median(z, axis=0)
    score = np.convolve(score, [0.25, 0.5, 0.25], mode="same")
    z0, z1 = int(min_px * 0.35), int(min_px * 0.9)
    ref = np.median(prof[:, z0:z1], axis=1)                          # each slice's border colour
    within = np.linalg.norm(prof[:, z0:z1] - ref[:, None], axis=2)
    spread = np.median(within, axis=1) + 4
    best = None
    for x in range(lo + 1, hi - 1):
        if score[x] < 2.5 or score[x] < score[x - 1] or score[x] < score[x + 1]:
            continue
        a, b = x + max(2, settle_px // 4), x + settle_px
        away = np.linalg.norm(prof[:, a:b] - ref[:, None], axis=2).mean(axis=1)
        if (away > 1.5 * spread).mean() < 0.4:                        # the border colour comes back: small print
            continue
        den = score[x - 1] - 2 * score[x] + score[x + 1]
        best = (x + (0.5 * (score[x - 1] - score[x + 1]) / den if den < 0 else 0.0), float(score[x]))
        break
    return best if best else (None, 0.0)


def _edge_offset(view_lab, pad, side, a, b, slice_px):
    """How far inside the straightened image the card's real cut edge sits on one side (px; negative =
    the image starts inside the card). Uses the margin of backdrop kept around the straightened card."""
    win = max(4, int(pad * 0.8))
    H, W = view_lab.shape[:2]
    if side == "left":
        strip = view_lab[pad + a:pad + b, pad - win:pad + win]
    elif side == "right":
        strip = view_lab[pad + a:pad + b, W - pad + win - 1:W - pad - win - 1:-1]
    elif side == "top":
        strip = view_lab[pad - win:pad + win, pad + a:pad + b].transpose(1, 0, 2)
    else:
        strip = view_lab[H - pad + win - 1:H - pad - win - 1:-1, pad + a:pad + b].transpose(1, 0, 2)
    n = strip.shape[0] // slice_px
    if n < 6 or strip.shape[1] < 2 * win:
        return 0.0
    prof = strip[:n * slice_px].reshape(n, slice_px, -1, 3).mean(axis=1)
    g = np.linalg.norm(prof[:, 2:] - prof[:, :-2], axis=2)
    peaks = np.argmax(g, axis=1) + 1                                   # the backdrop -> card step
    return float(np.median(peaks)) - win


EDGE_OFFSETS = False  # measured edge offsets helped some scans but upset black-bordered fronts; off until fixed


def measure_centering(m: Measurement):
    lab = cv2.cvtColor(m.canon, cv2.COLOR_BGR2LAB).astype(np.float32)
    min_px, max_px = int(0.035 * m.ppi), int(0.32 * m.ppi)
    hold = max(6, int(round(m.px(0.25))))
    a, b = int(0.08 * m.ch), int(0.92 * m.ch)
    c, d = int(0.10 * m.cw), int(0.90 * m.cw)
    depth = max_px + max(hold, int(round(m.px(1.2)))) + 2
    strips = {
        "left": lab[a:b, :depth],
        "right": lab[a:b, ::-1][:, :depth],
        "top": lab[:depth, c:d].transpose(1, 0, 2),
        "bottom": lab[::-1][:depth, c:d].transpose(1, 0, 2),
    }
    widths, agreement, refs = {}, {}, {}
    slice_px = max(4, int(round(m.px(1.0))))
    settle_px = int(round(m.px(1.2)))
    for side, strip in strips.items():
        line, strength = _line_depth(strip, min_px, max_px, slice_px, settle_px)
        w_s, a_s, r_s = _border_width_slices(strip, min_px, max_px, hold, slice_px, settle_px=settle_px)
        refs[side] = r_s
        # The colour-change answer, where enough slices agree; the straight-line answer stands in where the
        # border barely differs from the art (black holo border against dark art).
        if w_s is not None and a_s >= 0.3:
            widths[side], agreement[side] = w_s, a_s
        elif line is not None and line > min_px + m.px(0.3):
            widths[side], agreement[side] = line, min(0.45, strength / 8)
        else:
            widths[side], agreement[side] = w_s, a_s
        if refs[side] is None or widths[side] is not None:
            if refs[side] is None:
                refs[side] = _border_width(strip, min_px, max_px, hold)[2]
            continue
        if widths[side] is None:
            # Fall back to the whole-edge method (kept for its border colour, used by the edge checks).
            w_old, a_old, r_old = _border_width(strip, min_px, max_px, hold)
            refs[side] = r_old
            if widths[side] is None and w_old is not None and 0 < w_old < max_px:
                widths[side], agreement[side] = w_old, min(a_old, 0.3)
    m._border_ref = refs
    if EDGE_OFFSETS and getattr(m, "canon_view", None) is not None and m.view_pad > 4:
        # Measure each border from where the card's edge really is, not where the straightening put it.
        view_lab = cv2.cvtColor(m.canon_view, cv2.COLOR_BGR2LAB).astype(np.float32)
        spans = {"left": (a, b), "right": (a, b), "top": (c, d), "bottom": (c, d)}
        m._edge_offsets = {}
        for side in widths:
            off = _edge_offset(view_lab, m.view_pad, side, *spans[side], slice_px)
            if abs(off) <= m.px(0.5):
                m._edge_offsets[side] = off
                if widths[side] is not None:
                    widths[side] -= off
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


def _rim_widths(m, lab, pts, refs, labels, centre_offset=0):
    """For each outline point, how many px of pale (whitened) material sit just inside the edge.

    NaN where the pale area carries on deep into the card: that's printed artwork reaching the edge
    (e.g. silver foil stripes), not wear."""
    n = len(pts)
    k = max(6, int(round(m.px(0.25))))
    samples_n = int(round(m.px(RIM_DEPTH_MM)))
    deep_a, deep_b = int(round(m.px(0.9))), int(round(m.px(1.3)))
    tang = pts[(np.arange(n) + k) % n] - pts[(np.arange(n) - k) % n]
    tang /= np.linalg.norm(tang, axis=1, keepdims=True) + 1e-9
    normal = np.stack([-tang[:, 1], tang[:, 0]], axis=1)
    centre = np.array([m.cw / 2, m.ch / 2]) + centre_offset
    normal[np.sum(normal * (centre - pts), axis=1) < 0] *= -1
    t = np.arange(deep_b, dtype=np.float32)
    sx = (pts[:, 0:1] + normal[:, 0:1] * t).astype(np.float32)
    sy = (pts[:, 1:2] + normal[:, 1:2] * t).astype(np.float32)
    samples = cv2.remap(lab, sx, sy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)  # n x T x 3
    side_of = {"top_left": "top", "top_right": "top", "bottom_left": "bottom", "bottom_right": "bottom"}
    ref = np.array([refs[side_of.get(l, l)] for l in labels], dtype=np.float32)
    near = samples[:, :samples_n]
    # Count only pale pixels (lighter and less colourful than the border): that's whitening.
    # Dark specks or print detail near the edge change the colour too, but aren't wear.
    ref_chroma = np.hypot(ref[:, 1] - 128, ref[:, 2] - 128)[:, None]
    chroma = np.hypot(near[..., 1] - 128, near[..., 2] - 128)
    lighter = near[..., 0] - ref[:, None, 0]
    pale = np.where(ref_chroma > 20, (lighter > 12) & (chroma < ref_chroma * 0.7), lighter > 25)
    if getattr(m, "border_texture", 0.0) > TEXTURED_BORDER:
        # Silver dot-mesh border: its lighter moire waves aren't wear. Exposed paper is near-white.
        pale = (lighter > 40) & (near[..., 0] > 190)
    bg_light = getattr(m, "bg_light", 0.0)
    dark_border = (ref[:, 0] < bg_light - 40) & (ref_chroma[:, 0] < 20)
    if dark_border.any():
        # Dark border on a lighter backdrop (black card on the grey guide): the blend from backdrop to
        # border is lighter than the border but isn't wear. Whitening is near-white, so it must also be
        # lighter than the backdrop.
        pale[dark_border] &= near[dark_border][..., 0] > bg_light + 10
    rim = pale.sum(axis=1).astype(np.float32)
    deep = samples[:, deep_a:deep_b]
    deep_off = np.linalg.norm(deep - ref[:, None, :], axis=2).mean(axis=1) > 22
    rim[deep_off & (rim > 0)] = np.nan  # artwork reaching the edge, not whitening
    return rim


def _border_texture(m):
    """How busy the card's border is at fine scale (median local spread of lightness in a band 0.4-1.6 mm in).
    Plain borders score ~3-6; silver borders printed as a halftone dot mesh over holo foil score 50+."""
    L = cv2.cvtColor(m.canon, cv2.COLOR_BGR2LAB)[..., 0].astype(np.float32)
    a, b = int(round(m.px(0.4))), int(round(m.px(1.6)))
    band = np.zeros(L.shape, bool)
    band[:, a:b] = True; band[:, -b:-a] = True; band[a:b, :] = True; band[-b:-a, :] = True
    k = max(3, int(round(m.px(0.1))) | 1)
    mean = cv2.blur(L, (k, k))
    std = np.sqrt(np.clip(cv2.blur(L * L, (k, k)) - mean * mean, 0, None))
    return float(np.median(std[band]))


TEXTURED_BORDER = 20  # above this, the border is a dot mesh / sparkle and is smoothed before the edge checks


def _artwork_at_edge(m, pts, refs, canon=None):
    """Outline points whose pale pixels belong to a pale shape that reaches more than 0.8 mm into the
    card: printed artwork (silver stripes, white panels) touching the edge, not edge wear. Whitening hugs
    the edge; artwork connects to something deeper."""
    lab = cv2.cvtColor(m.canon if canon is None else canon, cv2.COLOR_BGR2LAB).astype(np.float32)
    ref = np.median(np.array(list(refs.values()), dtype=np.float32), axis=0)
    ref_chroma = float(np.hypot(ref[1] - 128, ref[2] - 128))
    chroma = np.hypot(lab[..., 1] - 128, lab[..., 2] - 128)
    lighter = lab[..., 0] - ref[0]
    pale = (lighter > 12) & (chroma < ref_chroma * 0.7) if ref_chroma > 20 else (lighter > 25)
    if getattr(m, "border_texture", 0.0) > TEXTURED_BORDER:
        pale = (lighter > 40) & (lab[..., 0] > 190)
    inside = (m.mask[m.pad:m.pad + m.ch, m.pad:m.pad + m.cw] > 127).astype(np.uint8)
    # The image border is the card's edge too: without a zero frame, a card that fills the straightened
    # image has no edge for the distance to count from.
    depth = cv2.distanceTransform(cv2.copyMakeBorder(inside, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0),
                                  cv2.DIST_L2, 5)[1:-1, 1:-1]  # px from the card's edge
    band = pale & (depth < m.px(2.0)) & (inside > 0)
    n, comp = cv2.connectedComponents(band.astype(np.uint8), connectivity=8)
    if n <= 1:
        return np.zeros(len(pts), bool)
    deepest = np.zeros(n)
    np.maximum.at(deepest, comp.ravel(), depth.ravel())
    art = deepest > m.px(0.8)
    art[0] = False
    # Any artwork within ~0.35 mm of the point counts, in every direction: a thin diagonal stripe that
    # meets the edge at a slant sits beside the point, not straight in from it.
    near = max(3, int(round(m.px(0.35))))
    art_px = cv2.dilate(art[comp].astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * near + 1, 2 * near + 1)))
    xi = np.clip(np.round(pts[:, 0]).astype(int), 0, m.cw - 1)
    yi = np.clip(np.round(pts[:, 1]).astype(int), 0, m.ch - 1)
    return art_px[yi, xi] > 0


def _whitening_runs(m, rim_px, typical):
    return _runs(rim_px > typical + m.px(RIM_EXTRA_MM), min_len=max(2, int(round(m.px(SPOT_MIN_MM)))))


def measure_edges_corners(m: Measurement):
    # Silver borders are printed as a fine dot mesh over holo foil: up close, a field of bright and dark
    # dots that would all read as "pale" (whitening or artwork). Whitening is a continuous pale strip along
    # the cut edge, so on such borders blur away the dots (at about their spacing) before looking for it.
    m.border_texture = _border_texture(m)
    canon, view = m.canon, m.canon_view
    if m.border_texture > TEXTURED_BORDER:
        sigma = m.px(0.06)
        canon = cv2.GaussianBlur(m.canon, (0, 0), sigma)
        view = cv2.GaussianBlur(m.canon_view, (0, 0), sigma) if m.canon_view is not None else None
    lab = cv2.cvtColor(canon, cv2.COLOR_BGR2LAB).astype(np.float32)
    pts = _outline(m)
    r = _fit_radius(m, pts)
    labels = _classify(m, pts, r)
    sd = _rounded_rect_sdist(pts, r, m.cw, m.ch)
    refs = {k: v for k, v in (getattr(m, "_border_ref", None) or {}).items() if v is not None}
    if m.border_texture > TEXTURED_BORDER:
        # Compare like with like: the border colour from the same smoothed image (a dot mesh's median dot
        # is darker than its average, so the unsmoothed colour would make the whole border look pale).
        a, b = int(round(m.px(0.45))), int(round(m.px(0.95)))
        y0, y1, x0, x1 = int(0.1 * m.ch), int(0.9 * m.ch), int(0.1 * m.cw), int(0.9 * m.cw)
        refs = {"left": np.median(lab[y0:y1, a:b].reshape(-1, 3), axis=0),
                "right": np.median(lab[y0:y1, -b:-a].reshape(-1, 3), axis=0),
                "top": np.median(lab[a:b, x0:x1].reshape(-1, 3), axis=0),
                "bottom": np.median(lab[-b:-a, x0:x1].reshape(-1, 3), axis=0)}
    if len(refs) < 4:
        med = np.median(lab[int(0.1 * m.ppi):int(0.12 * m.ppi), :].reshape(-1, 3), axis=0)
        refs = {s: refs.get(s, med) for s in ("top", "bottom", "left", "right")}
    # Sample from the view with real background around the card: outline points can sit a little past the
    # ideal straight edge, where the plain straightened image has no real pixels.
    if view is not None:
        lab_view = cv2.cvtColor(view, cv2.COLOR_BGR2LAB).astype(np.float32)
        rim = _rim_widths(m, lab_view, pts + m.view_pad, refs, labels, centre_offset=m.view_pad)
    else:
        rim = _rim_widths(m, lab, pts, refs, labels)
    # Points where artwork reaches the edge (NaN) get their edge's typical rim, so they never read as wear.
    side_of = {"top_left": "top", "top_right": "top", "bottom_left": "bottom", "bottom_right": "bottom"}
    typ0 = {}
    for s_ in ("top", "bottom", "left", "right"):
        vals = rim[labels == s_]
        typ0[s_] = float(np.nanmedian(vals)) if np.any(~np.isnan(vals)) else 0.0
    rim[_artwork_at_edge(m, pts, refs, canon) & (rim > 0)] = np.nan
    nan_idx = np.where(np.isnan(rim))[0]
    rim[nan_idx] = [typ0[side_of.get(labels[i], labels[i])] for i in nan_idx]
    m.print_at_edge = len(nan_idx) / max(1, len(rim))

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
    m._radius_px = r
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
    m.edges_reliable = bool(src_ppi and src_ppi >= 500) and not getattr(m, "dark_card", False)
    if getattr(m, "dark_card", False):
        m.warnings.append("Black-bordered card: size and centering are measured, but corners and edges can't be "
                          "judged against the black guide, so they aren't scored. Rescan it on the grey guide for "
                          "corner and edge checks.")
    elif not m.edges_reliable:
        m.warnings.append("Not a 600+ dpi scan: centering only. Corners and edges need a scanner image.")
    elif not m.background_dark:
        m.warnings.append("Light background detected. Put black paper behind the card for accurate edge and corner checks.")
    measure_centering(m)
    measure_edges_corners(m)
    return m
