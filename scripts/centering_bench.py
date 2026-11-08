"""Centering benchmark: how close Grade Check's centering is to TAG's, and how consistent it is.

1. TAG copies (data/tag_compare/*): each photo is put on the matching guide colour, straightened and
   measured; the result is compared with the centering TAG printed on that card's report.
2. Your own scans: a card scanned upright and turned 180° should give mirrored numbers
   (left 52 one way = right 52 the other way). Any difference is measurement noise.

Usage: .venv/bin/python scripts/centering_bench.py
"""

import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.grading import measure  # noqa: E402
from src.grading.tag_compare import TAG_PPI  # noqa: E402
from validate_on_tag import on_guide, pad_like_scan, trim_bars  # noqa: E402
import os  # noqa: E402
MODE = os.environ.get("BACKDROP", "swap")  # swap = put photos on grey/black; orange = keep TAG's orange

DATA = ROOT / "data" / "tag_compare"
CACHE = ROOT / "data" / "tag_compare" / "_canon_cache"


def tag_cent(s):
    n = [float(x) for x in re.findall(r"[\d.]+", s or "")]
    return (n[0], n[2]) if len(n) >= 4 else None


def canon_for(path, src_ppi=TAG_PPI):
    """Straightened TAG photo with its margin (cached: straightening is the slow part)."""
    CACHE.mkdir(exist_ok=True)
    out = CACHE / (MODE + "_" + path.parent.parent.name + "_" + path.parent.name + "_" + path.stem + "_view.png")
    meta = out.with_suffix(".json")
    if out.exists() and meta.exists():
        return cv2.imread(str(out)), json.loads(meta.read_text())["pad"]
    img = cv2.imread(str(path))
    m = measure.find_and_straighten(on_guide(img) if MODE == "swap" else pad_like_scan(trim_bars(img)), src_ppi)
    cv2.imwrite(str(out), m.canon_view)
    meta.write_text(json.dumps({"pad": m.view_pad}))
    return m.canon_view, m.view_pad


def centering(view, ppi, pad=None):
    if pad is None:  # a plain straightened card with no margin
        m = measure.Measurement(canon=view, mask=None, corners_src=None, background_dark=True, ppi=ppi)
    else:
        canon = view[pad:view.shape[0] - pad, pad:view.shape[1] - pad]
        m = measure.Measurement(canon=canon, mask=None, corners_src=None, background_dark=True, ppi=ppi)
        m.canon_view, m.view_pad = view, pad
    return measure.measure_centering(m)


def worse(v):
    return max(v, 100 - v)


def main(verbose=True):
    diffs, fails, per = [], 0, []
    sets = sorted(DATA.glob("*/ladder.json")) + sorted((ROOT / "data" / "tag_train").glob("*/ladder.json"))
    for ladder in sets:
        card = ladder.parent.name
        meta = ladder.parent / "card.json"
        src_ppi = json.loads(meta.read_text()).get("ppi", TAG_PPI) if meta.exists() else TAG_PPI
        for cert, v in json.loads(ladder.read_text()).items():
            for side, key in (("FRONT", "centF"), ("BACK", "centB")):
                t = tag_cent(v.get(key))
                view, pad = canon_for(ladder.parent / cert / f"{side}_MAIN.jpg", src_ppi)
                c = centering(view, src_ppi, pad)
                if c.get("lr") is None or not t:
                    fails += 1
                    per.append((card, cert, side, None, t))
                    continue
                d = (worse(c["lr"]) - worse(t[0]), worse(c["tb"]) - worse(t[1]))
                diffs += list(d)
                per.append((card, cert, side, (round(c["lr"], 1), round(c["tb"], 1)), t, d))
    if verbose:
        for p in per:
            if p[3] is None:
                print(f"{p[0]:13} {p[1]} {p[2]:5} FAILED            TAG {p[4]}")
            else:
                print(f"{p[0]:13} {p[1]} {p[2]:5} ours {p[3]}  TAG {p[4]}  miss {p[5][0]:+.1f} {p[5][1]:+.1f}")
    a = np.abs(diffs)
    print(f"\nTAG copies: measured {len(per) - fails}/{len(per)} sides | median miss {np.median(a):.2f} | "
          f"mean signed {np.mean(diffs):+.2f} | within 1 pt {np.mean(a <= 1):.0%} | within 2 pts {np.mean(a <= 2):.0%} | worst {a.max():.1f}")

    # Self-consistency on your scans: upright vs turned 180° should mirror.
    gaps = []
    for d in sorted((ROOT / "data" / "scans").glob("2026*")):
        for side in ("front", "back"):
            a_, b_ = d / f"{side}_view.jpg", d / f"{side}_rot_view.jpg"
            ja, jb = d / f"{side}.json", d / f"{side}_rot.json"
            if a_.exists() and b_.exists() and ja.exists() and jb.exists():
                pa, pb = json.loads(ja.read_text()).get("view_pad", 0), json.loads(jb.read_text()).get("view_pad", 0)
                ca, cb = centering(cv2.imread(str(a_)), 1200, pa), centering(cv2.imread(str(b_)), 1200, pb)
                if ca.get("lr") is not None and cb.get("lr") is not None:
                    g = (abs(ca["lr"] - (100 - cb["lr"])), abs(ca["tb"] - (100 - cb["tb"])))
                    gaps += list(g)
                    print(f"your scan {d.name[-6:]} {side:5}: upright {ca['lr']:.1f}/{ca['tb']:.1f}  turned {100 - cb['lr']:.1f}/{100 - cb['tb']:.1f}  gap {g[0]:.2f} {g[1]:.2f}")
                else:
                    print(f"your scan {d.name[-6:]} {side:5}: FAILED")
    if gaps:
        print(f"Your scans: upright vs 180° gap median {np.median(gaps):.2f}, worst {max(gaps):.2f}")


if __name__ == "__main__":
    main()
