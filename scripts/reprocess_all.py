"""Re-measure every saved scan from its original image with the current code, then rebuild each card's report.

Corner, edge and centering results are saved with each scan when it's taken, so a fix to how those are
measured only reaches cards scanned afterwards. This brings every saved card up to date. Each scan's previous
result is kept as <slot>.json.prev, so a change can be compared or undone.

Usage: .venv/bin/python scripts/reprocess_all.py [session ...]   (no sessions = all of them)
"""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import grade_app  # noqa: E402

SLOTS = grade_app.SLOTS


def _image_dpi(raw):
    """Older scans didn't record their resolution: read it from the image (None when it isn't a scanner one)."""
    from PIL import Image
    dpi = (Image.open(raw).info.get("dpi") or (None,))[0]
    return int(dpi) if dpi and dpi >= 150 else None


def main(only):
    client = grade_app.app.test_client()
    dirs = [grade_app.SCANS / s for s in only] if only else sorted(p for p in grade_app.SCANS.iterdir() if p.is_dir())
    for d in dirs:
        done = []
        for slot in SLOTS:
            raw, saved = d / f"{slot}_raw.jpg", d / f"{slot}.json"
            if not (raw.exists() and saved.exists()):
                continue
            ppi = json.loads(saved.read_text()).get("ppi") or _image_dpi(raw)
            shutil.copy(saved, d / f"{slot}.json.prev")
            try:
                grade_app._process(d.name, slot, raw.read_bytes(), ppi)
                done.append(slot)
            except Exception as e:  # e.g. a scan that no longer passes the which-way-up check
                print(f"  {d.name}/{slot}: kept the old result ({type(e).__name__}: {str(e)[:90]})", flush=True)
        if not done:
            continue
        r = client.get(f"/api/report/{d.name}").get_json()
        est = (r or {}).get("estimates") or {}
        grades = {k: est[k]["grade"] for k in ("TAG", "PSA", "CGC") if k in est and "grade" in est[k]}
        name = ((r or {}).get("meta") or {}).get("name") or ""
        print(f"{d.name} {name[:40]:40s} re-measured {len(done)} scans -> {grades}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
