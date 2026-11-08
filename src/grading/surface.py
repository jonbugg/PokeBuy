"""Surface check from two scans of the same side, the second with the card turned 180°.

A flatbed lights the card from one side. Turning the card swaps which way the light rakes across it,
so dents, scratches and indents shade differently in the two scans while flat print stays the same.

Steps: rotate the second scan back, align it point by point (the scanner's motion isn't perfectly
even, so one rigid alignment leaves the print's outlines showing), remove the sensor's column/row
pattern, and down-weight places where the print itself has sharp edges (tiny leftover misalignment
shows up most there). What stands out after that is either real surface relief or debris. Debris
(dust, lint) is a bright speck present in only one of the two scans, so it's reported separately.
"""

import cv2
import numpy as np

from .measure import CARD_W_IN

YELLOW_STRENGTH = 4.5   # times this card's typical difference level
RED_STRENGTH = 7.0
HIGHPASS_PX = 12  # shading broader than about this (pixels at 1200 dpi) is removed before comparing
FLOW_SMOOTH_PX = 6  # how smooth the warp between the two scans must be (pixels at 1200 dpi)
GLARE_ONE_SIDED = False  # tried: catches a little more, but lets glare through on clean cards
PRINT_FROM_AVERAGE = False  # tried: print edges from the 2-scan average; more false marks where alignment is imperfect
FAINT_MM, FAINT_STRENGTH = 0.5, 6.0  # spots smaller and weaker than this are listed, not counted
SPARKLE_MM, SPARKLE_RISE = 0.3, 25  # a point this small and this much brighter than around it in both scans
COLOUR_EDGES = True       # count colour-only print edges (gold stripes) as print, not damage
COLOUR_EDGE_WEIGHT = 3.0  # a/b channels change ~3x less than lightness across a comparable edge
MIN_AREA_MM2 = 0.02


def _flow_maps(ga, gb):
    """Per-pixel maps that bring scan b into line with scan a."""
    s = 0.5
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    flow = dis.calc(cv2.resize(ga, None, fx=s, fy=s).astype(np.uint8),
                    cv2.resize(gb, None, fx=s, fy=s).astype(np.uint8), None)
    # Smooth the warp: the scanner's misalignment between two passes changes gradually over millimetres, while a
    # dent or scratch is under a millimetre. A warp free to bend around a single mark would line the mark up with
    # itself and hide it.
    flow = cv2.GaussianBlur(cv2.resize(flow, (ga.shape[1], ga.shape[0])) / s, (0, 0), FLOW_SMOOTH_PX)
    h, w = ga.shape
    xx, yy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    return xx + flow[..., 0], yy + flow[..., 1]


def _align(ga, gb):
    mx, my = _flow_maps(ga, gb)
    return cv2.remap(gb, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def _pair(a, b, cx, cy, size_mm, mmpp, colour, labels=("First scan", "180 deg scan, turned back")):
    """Same spot in both scans side by side, zoomed, with the spot circled."""
    half = int(max(1.2, size_mm / 2 + 0.6) / mmpp)
    h, w = a.shape[:2]
    x0, y0, x1, y1 = max(0, cx - half), max(0, cy - half), min(w, cx + half), min(h, cy + half)
    tiles = []
    for img, label in zip((a, b), labels):
        t = cv2.resize(img[y0:y1, x0:x1], (260, int(260 * (y1 - y0) / max(1, x1 - x0))), interpolation=cv2.INTER_CUBIC)
        k = 260 / max(1, x1 - x0)
        r = int(max(size_mm / 2 + 0.25, 0.35) / mmpp * k)
        cv2.circle(t, (int((cx - x0) * k), int((cy - y0) * k)), r, colour, 2)
        t = cv2.copyMakeBorder(t, 26, 0, 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        cv2.putText(t, label, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (60, 60, 60), 1, cv2.LINE_AA)
        tiles.append(t)
    gap = np.full((tiles[0].shape[0], 6, 3), 255, np.uint8)
    return np.hstack([tiles[0], gap, tiles[1]])


def _sparkle(ga, gb, region, mmpp):
    """Is this spot a bright point (well above its surroundings) in both scans?"""
    ys, xs = np.where(region)
    r = int(0.6 / mmpp)
    y0, y1, x0, x1 = max(0, ys.min() - r), ys.max() + r + 1, max(0, xs.min() - r), xs.max() + r + 1
    around_a, around_b = np.median(ga[y0:y1, x0:x1]), np.median(gb[y0:y1, x0:x1])
    return float(ga[region].max()) - around_a > SPARKLE_RISE and float(gb[region].max()) - around_b > SPARKLE_RISE


def compare(canon_a, canon_b_rotated, pair_labels=("First scan", "180 deg scan, turned back")):
    if canon_b_rotated.shape != canon_a.shape:  # e.g. one scan at 600 dpi, the other at 1200
        canon_b_rotated = cv2.resize(canon_b_rotated, (canon_a.shape[1], canon_a.shape[0]), interpolation=cv2.INTER_AREA)
    mmpp = CARD_W_IN * 25.4 / canon_a.shape[1]
    k = 0.0212 / mmpp  # blur sizes below were tuned at 1200 dpi
    ga = cv2.cvtColor(canon_a, cv2.COLOR_BGR2GRAY).astype(np.float32)
    b_colour = cv2.rotate(canon_b_rotated, cv2.ROTATE_180)
    gb = cv2.cvtColor(b_colour, cv2.COLOR_BGR2GRAY).astype(np.float32)
    mx, my = _flow_maps(ga, gb)
    gb = cv2.remap(gb, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    b_aligned = cv2.remap(b_colour, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    hp = lambda g: g - cv2.GaussianBlur(g, (0, 0), HIGHPASS_PX * k)
    ha, hb = hp(ga), hp(gb)
    diff = ha - hb
    diff -= np.median(diff, axis=0, keepdims=True)  # scanner sensor column pattern
    diff -= np.median(diff, axis=1, keepdims=True)
    # Print edges come from the average of the two aligned scans: a dent or scratch shades light-then-dark in one
    # scan and dark-then-light in the other, so it cancels out of the average while the printing stays. (Taken
    # from one scan alone, a dent's own shading looked like a print edge and turned the dent itself down.)
    print_grey = (ga + gb) / 2 if PRINT_FROM_AVERAGE else ga
    blur = cv2.GaussianBlur(print_grey, (0, 0), 1.5 * k)
    grad = cv2.GaussianBlur(np.hypot(cv2.Sobel(blur, cv2.CV_32F, 1, 0), cv2.Sobel(blur, cv2.CV_32F, 0, 1)), (0, 0), 3 * k)
    strength_map = cv2.GaussianBlur(np.abs(diff), (0, 0), 2 * k) / (6 + 0.15 * grad)

    margin = int(1.0 / mmpp)
    inner = np.zeros(strength_map.shape, dtype=bool)
    inner[margin:-margin, margin:-margin] = True

    # Holo foil and silver ink reflect differently when the light comes from the other side, so whole
    # patches of them differ between the two scans, often with a colour shift too. A dent or scratch is a
    # narrow mark on otherwise matching print. Damp places where differences are spread over the
    # surrounding few millimetres, or where the colour itself changed.
    sd = float(np.median(np.abs(diff[inner]))) * 1.48 + 1e-3
    busy = cv2.GaussianBlur((np.abs(diff) > 3 * sd).astype(np.float32), (0, 0), 70 * k)  # ~1.5 mm
    lab_a = cv2.cvtColor(canon_a, cv2.COLOR_BGR2LAB).astype(np.float32)
    lab_b = cv2.cvtColor(b_aligned, cv2.COLOR_BGR2LAB).astype(np.float32)
    hue_shift = cv2.GaussianBlur(np.hypot(lab_a[..., 1] - lab_b[..., 1], lab_a[..., 2] - lab_b[..., 2]), (0, 0), 15 * k)
    strength_map /= 1 + 12 * busy + np.clip(hue_shift - 6, 0, None) / 4
    typical = float(np.median(strength_map[inner])) or 1.0
    strength_map /= typical
    if COLOUR_EDGES:
        # Print edges that are mostly a change of colour, not brightness (the stripes on an etched gold card,
        # gold against yellow) are raised or etched too, and shade differently from each side just like a
        # dent would. Damp them like brightness edges. Done after the card's typical level is set, so this only
        # ever turns marks down.
        lab_blur = cv2.GaussianBlur((lab_a + lab_b) / 2 if PRINT_FROM_AVERAGE else lab_a, (0, 0), 1.5 * k)
        cgrad = np.zeros_like(grad)
        for ch in (1, 2):
            c = lab_blur[..., ch]
            cgrad = np.maximum(cgrad, COLOUR_EDGE_WEIGHT * np.hypot(cv2.Sobel(c, cv2.CV_32F, 1, 0), cv2.Sobel(c, cv2.CV_32F, 0, 1)))
        cgrad = cv2.GaussianBlur(cgrad, (0, 0), 3 * k)
        strength_map *= (6 + 0.15 * grad) / (6 + 0.15 * np.maximum(grad, cgrad))

    raw = gb - ga  # aligned, so the print cancels; lint makes one scan uniformly brighter here
    hits = ((strength_map > YELLOW_STRENGTH) & inner).astype(np.uint8)
    n, labels, stats, cents = cv2.connectedComponentsWithStats(hits, 8)
    marks, debris = [], []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area * mmpp * mmpp < MIN_AREA_MM2:
            continue
        region = cv2.dilate((labels == i).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        vals = raw[region]
        peak_up, peak_down = float(vals.max()), float(-vals.min())
        # Lint/dust: a strong bright peak in one scan, much bigger than any dark dip beside it.
        # A dark speck on light print (dust in the first pass) is much fainter than lint on a dark border,
        # but just as one-sided, so the one-sidedness matters more than the size of the peak.
        in_b = (peak_up > 80 and peak_up > 2 * peak_down) or (peak_up > 30 and peak_up > 3 * peak_down)
        in_a = (peak_down > 80 and peak_down > 2 * peak_up) or (peak_down > 30 and peak_down > 3 * peak_up)
        entry = {
            "x_pct": round(100 * cents[i][0] / strength_map.shape[1], 1),
            "y_pct": round(100 * cents[i][1] / strength_map.shape[0], 1),
            "length_mm": round(max(w, h) * mmpp, 2),
            "kind": "line" if max(w, h) > 4 * min(w, h) else "spot",
            "strength": round(float(strength_map[region].max()), 1),
        }
        # Glare: a near-white highlight in one scan only (silver ink or foil catching the light from one
        # side). Real damage doesn't turn white in one pass and stay dark in the other.
        ma, mb = float(ga[region].max()), float(gb[region].max())
        glare = max(ma, mb) > 225 and min(ma, mb) < max(ma, mb) - 45
        # ...and only one-sided: glare brightens one scan with nothing matching in the other, while a dent or
        # scratch on light print is bright on one side in one scan and dark on that side in the other.
        glare = glare and (not GLARE_ONE_SIDED or peak_up > 2 * peak_down or peak_down > 2 * peak_up)
        if glare and not (in_a or in_b):
            entry["only_in"] = ("180° scan" if mb > ma else "first scan") + " (glare)"
            debris.append(entry)
            continue
        if in_a or in_b:
            # Something sitting on the card or glass for one pass. A dent or scratch shades one side
            # light and the other dark by similar amounts instead.
            entry["only_in"] = "180° scan" if in_b else "first scan"
            debris.append(entry)
        elif entry["kind"] == "spot" and entry["length_mm"] < SPARKLE_MM and _sparkle(ga, gb, region, mmpp):
            # A holo/glitter sparkle: a bright point in BOTH scans, just brighter in one. A dent or scratch
            # shades light on one side and dark on the other instead of making the same bright point twice.
            entry["sparkle"] = True
            debris.append(entry)
        elif entry["kind"] == "spot" and entry["length_mm"] < FAINT_MM and entry["strength"] < FAINT_STRENGTH:
            # Tiny and barely over the line: on halftone print (the blue back, light art) the dot pattern
            # lines up a hair differently between two scans and leaves specks like this. Listed, not counted.
            entry["faint"] = True
            debris.append(entry)
        else:
            marks.append(entry)
    marks.sort(key=lambda m: -m["strength"])
    debris.sort(key=lambda m: -m["strength"])
    pairs = []  # (entry, image) — the app saves these and puts a URL on each entry
    for entry, colour in [(m, (40, 40, 230) if m["strength"] > RED_STRENGTH else (0, 200, 255)) for m in marks[:20]] + \
                         [(d, (150, 150, 150)) for d in debris[:20]]:
        cx = int(entry["x_pct"] / 100 * canon_a.shape[1])
        cy = int(entry["y_pct"] / 100 * canon_a.shape[0])
        pairs.append((entry, _pair(canon_a, b_aligned, cx, cy, entry["length_mm"], mmpp, colour, pair_labels)))

    heat = cv2.applyColorMap(np.clip(strength_map / 8 * 255, 0, 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
    for m, colour in [(m, (0, 0, 255) if m["strength"] > RED_STRENGTH else (0, 200, 255)) for m in marks[:20]] + \
                     [(d, (200, 200, 200)) for d in debris[:20]]:
        cx, cy = int(m["x_pct"] / 100 * heat.shape[1]), int(m["y_pct"] / 100 * heat.shape[0])
        cv2.circle(heat, (cx, cy), int(40 * k), colour, max(2, int(4 * k)))
    return {
        "noise": round(typical, 2),
        "marks": marks[:20],
        "debris": debris[:20],
        "flagged": any(m["strength"] > RED_STRENGTH for m in marks),
        "_pairs": pairs,
    }, heat
