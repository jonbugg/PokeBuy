"""A TAG-style surface relief map from four scans of the same side, lit from four directions.

The scanner's light comes from one fixed direction, so turning the card 0°, 90°, 180° and 270° lights it from
four sides, like TAG's four-light rig with the light moved instead of the card. With the four scans lined
up on the first:

- Opposite pairs give the surface slope: where the surface tilts toward the light it looks brighter, away
  from it darker, and the effect flips when the light comes from the other side. (A - B) / (A + B) is that
  difference divided by the total brightness, which cancels the printed colour (artwork, ink, holo base
  colour) and leaves the tilt. The 0°/180° pair gives slope along the card, the 90°/270° pair across it.
- Shading those slopes with one virtual light gives a grey relief image like TAG's surface map: flat
  card is even grey, dents, creases, scratches and roller lines stand out as light/dark relief.
- The slope strength map highlights where the surface isn't flat.

Holo foil and silver ink reflect like mirrors rather than paper, so they don't follow this rule and show up
as busy texture on the relief; read those areas with care.
"""

import cv2
import numpy as np

from src.grading.surface import _flow_maps


def _grey(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2LAB)[..., 0].astype(np.float32) + 1.0


def _aligned(ref_g, img):
    g = _grey(img)
    if g.shape != ref_g.shape:
        g = cv2.resize(g, (ref_g.shape[1], ref_g.shape[0]), interpolation=cv2.INTER_AREA)
    mx, my = _flow_maps(ref_g, g)
    return cv2.remap(g, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def slopes(first, turned180_upright, q90_upright, q270_upright, ppi):
    """Slope maps (along, across) from four canons already turned to the first scan's way up."""
    a = _grey(first)
    b = _aligned(a, turned180_upright)
    c = _aligned(a, q90_upright)
    e = _aligned(a, q270_upright)
    blur = lambda x: cv2.GaussianBlur(x, (0, 0), max(0.6, ppi / 1200))  # tame leftover misalignment

    def ratio(p, q):
        d = (blur(p) - blur(q)) / (blur(p) + blur(q))
        # remove broad shading (light falloff, a slightly bowed card): keep relief finer than ~3 mm
        return d - cv2.GaussianBlur(d, (0, 0), 3.0 / 25.4 * ppi)

    return ratio(a, b), ratio(c, e)


def from_scans(first, ppi, turned180=None, q90=None, q270=None):
    """Slope maps from whichever scans exist, all already turned to the first scan's way up.

    Returns (along, across, directions). Opposite pairs give a slope directly (0°/180° along the card, 90°/270°
    across it). A single quarter turn without its opposite still gives the across slope, more roughly, by
    comparing it with the average of the 0°/180° pair (light from neither side). A missing slope is left flat,
    so a 0°/180°-only map is lit along the card only: marks running across the card show, marks running
    along it barely do."""
    a = _grey(first)
    blur = lambda x: cv2.GaussianBlur(x, (0, 0), max(0.6, ppi / 1200))
    hp = 3.0 / 25.4 * ppi

    def ratio(p, q):
        d = (blur(p) - blur(q)) / (blur(p) + blur(q))
        return d - cv2.GaussianBlur(d, (0, 0), hp)

    b = _aligned(a, turned180) if turned180 is not None else None
    c = _aligned(a, q90) if q90 is not None else None
    e = _aligned(a, q270) if q270 is not None else None
    zero = np.zeros_like(a)
    along = ratio(a, b) if b is not None else zero
    if c is not None and e is not None:
        across = ratio(c, e)
    elif (c is not None or e is not None) and b is not None:
        mid = (a + b) / 2
        across = 2 * ratio(c, mid) if c is not None else -2 * ratio(e, mid)
    else:
        across = zero
    directions = 1 + sum(x is not None for x in (b, c, e))
    return along, across, directions


def render(along, across, ppi, gain=10.0):
    """(relief image, slope-strength image) as 8-bit grey/heat images the size of the card."""
    gy, gx = along * gain, across * gain
    # one virtual light from the upper left, fairly low, like a raking lamp
    lx, ly, lz = -0.55, -0.55, 0.63
    shade = (-gx * lx - gy * ly + lz) / np.sqrt(gx * gx + gy * gy + 1.0)
    # Like TAG's surface map: flat card sits at mid grey, ridges and dips go evenly lighter and darker. (A plain
    # min-max stretch put flat card near white, which washed the relief out.)
    dev = shade - np.median(shade)
    spread = np.percentile(np.abs(dev), 99.5) + 1e-6
    relief = np.clip(128 + dev / spread * 110, 0, 255).astype(np.uint8)
    strength = np.hypot(along, across)
    strength = cv2.GaussianBlur(strength, (0, 0), max(1.0, ppi / 600))
    s_hi = np.percentile(strength, 99.5)
    heat = cv2.applyColorMap(np.clip(strength / (s_hi + 1e-6) * 255, 0, 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
    return relief, heat
