"""Save harvested TAG reports (from scripts/tag_harvest.js) as a training card set.

Input: a JSON file {key: {card, url, pop, copies: {cert: {...}}}} from the harvester.
Output: data/tag_train/<key>/ladder.json (same shape as data/tag_compare) and each cert's FRONT_MAIN.jpg /
BACK_MAIN.jpg, downsized to about scanner resolution (TAG's photos are ~1630 ppi; 1200 is plenty for
centering and keeps the set small). ladder.json records the photos' ppi.

Usage: .venv/bin/python -I scripts/tag_ingest.py harvested.json
"""

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "tag_train"
TAG_PPI = 1628
PPI = 1200


def spots(surf):
    return [[m.group(1).lower(), m.group(2).strip(" /"), int(m.group(3)), int(m.group(4))]
            for m in re.finditer(r"\(VIEW\) (Front|Back) (.+?)\s*/?\s*(\d+),(\d+)", surf or "")]


def fetch(url, dst):
    if dst.exists():
        return True
    for attempt in range(3):
        try:
            data = urllib.request.urlopen(url, timeout=60).read()
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            s = PPI / TAG_PPI
            img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(dst), img, [cv2.IMWRITE_JPEG_QUALITY, 93])
            return True
        except Exception as e:  # noqa: BLE001
            print("   retry", dst.name, e)
            time.sleep(2 + attempt * 3)
    return False


def main(path):
    harvested = json.loads(Path(path).read_text())
    for key, h in harvested.items():
        if not h.get("copies"):
            print(key, "skipped:", h.get("error"))
            continue
        folder = OUT / key
        folder.mkdir(parents=True, exist_ok=True)
        ladder = {}
        for cert, c in h["copies"].items():
            if not c.get("img") or not c.get("centF"):
                continue
            (folder / cert).mkdir(exist_ok=True)
            ok = all(fetch(c["img"] + f"_{side}_MAIN.jpg", folder / cert / f"{side}_MAIN.jpg") for side in ("FRONT", "BACK"))
            if not ok:
                continue
            ladder[cert] = {k: c.get(k) for k in ("grade", "score", "centF", "centB", "dims", "dings", "img")}
            ladder[cert]["spots"] = spots(c.get("surf"))
        meta = {"card": h.get("card"), "url": h.get("url"), "pop": h.get("pop"), "ppi": PPI}
        (folder / "ladder.json").write_text(json.dumps(ladder, indent=1))
        (folder / "card.json").write_text(json.dumps(meta, indent=1))
        print(f"{key:12} {len(ladder):2} copies saved  pop {h.get('pop')}")


if __name__ == "__main__":
    main(sys.argv[1])
