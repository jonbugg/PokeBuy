"""QC: re-measure every saved scan with the current code and compare with an earlier snapshot.

Each scan's centering and findings (corners, edges) are written to data/qc/<name>.json. Given a second
snapshot name, lists every scan whose result changed, so a change to the grading code can be checked against
all real scans before it ships.

Usage:
  .venv/bin/python scripts/qc_scans.py snap NAME            # measure every scan, save as NAME
  .venv/bin/python scripts/qc_scans.py diff OLD NEW         # what changed between two snapshots
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.grading import closeups, measure  # noqa: E402

SCANS = ROOT / "data" / "scans"
OUT = ROOT / "data" / "qc"
SLOTS = ("front", "back", "front_rot", "back_rot", "front_r90", "front_r270", "back_r90", "back_r270")


def snapshot(name):
    OUT.mkdir(parents=True, exist_ok=True)
    res = {}
    for d in sorted(SCANS.iterdir()):
        if not d.is_dir():
            continue
        for slot in SLOTS:
            raw, saved = d / f"{slot}_raw.jpg", d / f"{slot}.json"
            if not (raw.exists() and saved.exists()):
                continue
            ppi = json.loads(saved.read_text()).get("ppi") or 1200
            key = f"{d.name}/{slot}"
            try:
                m = measure.measure_image(measure.load(raw.read_bytes()), ppi)
            except measure.CardNotFound as e:
                res[key] = {"error": str(e)}
                continue
            c = m.centering or {}
            res[key] = {
                "centering": [c.get("lr"), c.get("tb")],
                "confidence": c.get("confidence"),
                "findings": sorted(f"{f['region']}|{f['kind']}|{f['severity']}" for f in closeups.build_findings(m)),
            }
            print(key, res[key]["centering"], len(res[key]["findings"]), "findings", flush=True)
    (OUT / f"{name}.json").write_text(json.dumps(res, indent=1, default=float))
    print(f"saved {len(res)} scans to data/qc/{name}.json")


def diff(old, new):
    a = json.loads((OUT / f"{old}.json").read_text())
    b = json.loads((OUT / f"{new}.json").read_text())
    changed = 0
    for key in sorted(set(a) | set(b)):
        x, y = a.get(key), b.get(key)
        if x == y:
            continue
        changed += 1
        print(f"\n{key}")
        if not x or not y or "error" in x or "error" in y:
            print("  before:", x, "\n  after: ", y)
            continue
        if x["centering"] != y["centering"]:
            print(f"  centering {x['centering']} -> {y['centering']}")
        gone = sorted(set(x["findings"]) - set(y["findings"]))
        added = sorted(set(y["findings"]) - set(x["findings"]))
        if gone:
            print("  no longer flagged:", gone)
        if added:
            print("  newly flagged:   ", added)
    print(f"\n{changed} of {len(set(a) | set(b))} scans changed")


if __name__ == "__main__":
    if sys.argv[1] == "snap":
        snapshot(sys.argv[2])
    else:
        diff(sys.argv[2], sys.argv[3])
