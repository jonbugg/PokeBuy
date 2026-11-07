"""Find the card (and the printed guide's black window, if used) in a low-res preview of the whole glass."""

import cv2
import numpy as np

UNITS = 300  # eSCL region units per inch
CARD_W, CARD_H = 2.5, 3.5


def locate(preview_bgr, dpi):
    """Return the scan region to use (1/300 in units), a mode, warnings, and an annotated preview."""
    gray = cv2.cvtColor(preview_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    per_in = dpi
    warnings = []
    annotated = preview_bgr.copy()

    window = _find_black_window(gray, per_in)
    if window is not None:
        x, y, ww, wh = window
        inside = preview_bgr[y:y + wh, x:x + ww]
        card = _find_card(inside, per_in, dark_bg=True)
        cv2.rectangle(annotated, (x, y), (x + ww, y + wh), (222, 117, 0), 2)
        if card is None:
            return _result(None, "guide", ["Found the guide's window but no card in it."], annotated)
        cx, cy, cw, ch = card
        cx, cy = cx + x, cy + y
        cv2.rectangle(annotated, (cx, cy), (cx + cw, cy + ch), (80, 180, 40), 2)
        gaps = {"left": cx - x, "right": x + ww - (cx + cw), "top": cy - y, "bottom": y + wh - (cy + ch)}
        tight = [k for k, v in gaps.items() if v < 0.12 * per_in]
        if tight:
            warnings.append(f"The card is close to the window's {' and '.join(tight)} edge. Nudge it toward the middle.")
        inset = int(0.06 * per_in)
        region = (x + inset, y + inset, ww - 2 * inset, wh - 2 * inset)
        return _result(_to_units(region, per_in), "guide", warnings, annotated, card_units=_to_units((cx, cy, cw, ch), per_in))

    card = _find_card(preview_bgr, per_in, dark_bg=False)
    if card is None:
        return _result(None, "none", ["Couldn't find a card on the glass. Is the lid closed and the card face down?"], annotated)
    cx, cy, cw, ch = card
    cv2.rectangle(annotated, (cx, cy), (cx + cw, cy + ch), (80, 180, 40), 2)
    m = int(0.3 * per_in)
    x0, y0 = max(0, cx - m), max(0, cy - m)
    x1, y1 = min(w, cx + cw + m), min(h, cy + ch + m)
    around = np.concatenate([gray[max(0, cy - m):cy, cx:cx + cw].ravel(), gray[cy + ch:min(h, cy + ch + m), cx:cx + cw].ravel()])
    if around.size and np.median(around) > 70:
        warnings.append("No black backdrop found. Use the printed guide (or black paper) for accurate edges and corners.")
    return _result(_to_units((x0, y0, x1 - x0, y1 - y0), per_in), "bare", warnings, annotated,
                   card_units=_to_units((cx, cy, cw, ch), per_in))


def _find_black_window(gray, per_in):
    dark = (gray < 70).astype(np.uint8) * 255
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    # The card inside the window is not dark; fill holes so the window is one solid blob.
    contours, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in contours:
        x, y, ww, wh = cv2.boundingRect(c)
        win, hin = ww / per_in, wh / per_in
        if not (2.7 <= min(win, hin) <= 4.8 and 3.7 <= max(win, hin) <= 6.0):
            continue
        if best is None or ww * wh > best[2] * best[3]:
            best = (x, y, ww, wh)
    return best


def _find_card(bgr, per_in, dark_bg):
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    hh, ww = lab.shape[:2]
    b = max(2, int(0.05 * per_in))
    frame = np.concatenate([lab[:b].reshape(-1, 3), lab[-b:].reshape(-1, 3),
                            lab[:, :b].reshape(-1, 3), lab[:, -b:].reshape(-1, 3)])
    if dark_bg:
        # The crop's edge can straddle the black block and the white paper beyond it; use only the black.
        dark = lab[..., 0] < 110
        bg = np.median(lab[dark], axis=0) if dark.mean() > 0.1 else np.median(frame, axis=0)
    else:
        bg = np.median(frame, axis=0)
    dist = np.linalg.norm(lab - bg, axis=2)
    thr = 25 if dark_bg else 18
    m = (dist > thr).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    # RETR_LIST: the guide's cut edge shows up as a white outline around the card, so the card
    # can be a contour *inside* another one.
    contours, _ = cv2.findContours(m, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in contours:
        (_, _), (rw, rh), _ = cv2.minAreaRect(c)
        if min(rw, rh) == 0:
            continue
        short, long_ = min(rw, rh) / per_in, max(rw, rh) / per_in
        if 2.2 <= short <= 2.8 and 3.2 <= long_ <= 3.8 and cv2.contourArea(c) > 0.85 * rw * rh:
            x, y, w, h = cv2.boundingRect(c)
            if best is None or w * h > best[2] * best[3]:
                best = (x, y, w, h)
    return best


def _to_units(box, per_in):
    x, y, w, h = box
    k = UNITS / per_in
    return [int(round(x * k)), int(round(y * k)), int(round(w * k)), int(round(h * k))]


def _result(region, mode, warnings, annotated, card_units=None):
    return {"region": region, "mode": mode, "warnings": warnings, "card": card_units}, annotated
