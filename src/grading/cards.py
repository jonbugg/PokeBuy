"""Identify a card from its scan (OCR of the collector number) and look it up in the Pokémon TCG API.

The collector number ("160/159", "SWSH133", "TG05") is printed small but in plain type, so OCR reads it
reliably; the set size in "160/159" narrows it to one or two cards. Names are stylised and OCR poorly,
so they're only used to rank candidates. Results come with TCGplayer market prices (ungraded).
"""

import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

import cv2
import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "card_cache.json"
API = "https://api.pokemontcg.io/v2/cards"
TESSERACT = "tesseract"

NUM_TOTAL = re.compile(r"(\d{1,3})\s*/\s*(\d{2,3})")
PROMO = re.compile(r"\b(SWSH|SVP|SV|SM|XY|BW|TG|GG|HGSS|DP)\s?-?(\d{1,3})\b")


def _api_key():
    return dotenv_values(ROOT / ".env").get("POKEMON_TCG_API_KEY", "")


def _ocr(gray, psm):
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        cv2.imwrite(f.name, gray)
        try:
            out = subprocess.run([TESSERACT, f.name, "-", "--psm", str(psm)], capture_output=True, text=True, timeout=30)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return ""
    return out.stdout


def _prep(gray, scale=0.8, invert=False):
    g = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    g = cv2.createCLAHE(2.0, (8, 8)).apply(g)
    _, t = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return 255 - t if invert else t


def read_scan(canon_bgr):
    """OCR the front scan: collector numbers found (most-read first), and words that might be the name."""
    g = cv2.cvtColor(canon_bgr, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    votes = {}

    def collect(text):
        for a, b in NUM_TOTAL.findall(text):
            if int(a) > 0:
                key = (a.lstrip("0") or "0", b)
                votes[key] = votes.get(key, 0) + 1
        for prefix, n in PROMO.findall(text.upper()):
            votes[f"{prefix}{n}"] = votes.get(f"{prefix}{n}", 0) + 1

    bottom = g[int(.87 * h):int(.985 * h), :]
    for scale in (0.45, 0.6, 0.8):
        collect(_ocr(cv2.resize(bottom, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA), 6))
    for x0, x1 in ((.03, .42), (.58, .97)):
        for y0, y1 in ((.92, .98), (.88, .94)):  # number sits at the very bottom on most cards, a little higher on promos
            crop = g[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
            for scale in (0.6, 0.8, 1.0):
                for inv in (False, True):
                    collect(_ocr(_prep(crop, scale, inv), 6))
    numbers = [k for k, _ in sorted(votes.items(), key=lambda kv: -kv[1])]
    words = []
    top = g[int(.02 * h):int(.10 * h), int(.10 * w):int(.78 * w)]
    for scale in (0.4, 0.5, 0.7):
        text = _ocr(cv2.resize(top, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA), 7)
        words += [x.lower() for x in re.findall(r"[A-Za-zé']{4,}", text) if x.lower() not in {"basic", "stage", "evolves"}]
    return {"numbers": numbers, "votes": {str(k): v for k, v in votes.items()}, "name_words": sorted(set(words))}


def _cache():
    try:
        return json.loads(CACHE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _query(q, page_size=12):
    """Search the Pokémon TCG API (it's flaky: retry, and cache answers for a week)."""
    cache = _cache()
    hit = cache.get(q)
    if hit and time.time() - hit["t"] < 7 * 86400:
        return hit["data"]
    last = None
    for attempt in range(4):
        try:
            r = httpx.get(API, params={"q": q, "pageSize": page_size, "orderBy": "-set.releaseDate"},
                          headers={"X-Api-Key": _api_key()}, timeout=45)
            if r.status_code == 200:
                data = [_card(c) for c in r.json().get("data", [])]
                cache[q] = {"t": time.time(), "data": data}
                CACHE.write_text(json.dumps(cache))
                return data
            last = f"HTTP {r.status_code}"
        except httpx.HTTPError as e:
            last = type(e).__name__
        time.sleep(2 + attempt * 2)
    raise RuntimeError(f"Card lookup service didn't answer ({last}). Try again in a minute.")


def _card(c):
    prices = (c.get("tcgplayer") or {}).get("prices") or {}
    variants = {k: v.get("market") for k, v in prices.items() if v.get("market")}
    market = max(variants.values()) if variants else None
    return {
        "id": c["id"], "name": c["name"], "number": c["number"],
        "set": c["set"]["name"], "set_total": c["set"].get("printedTotal"), "series": c["set"].get("series"),
        "released": c["set"].get("releaseDate"), "rarity": c.get("rarity"),
        "image": c["images"]["small"], "image_large": c["images"]["large"],
        "market": market, "market_variants": variants,
        "tcgplayer_url": (c.get("tcgplayer") or {}).get("url"),
    }


def _image_similarity(canon_bgr, url):
    """How alike the scan and the card's official image look (colour layout), -1..1."""
    try:
        r = httpx.get(url, timeout=20)
        if r.status_code != 200:
            return -1.0
        import numpy as np
        ref = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
        if ref is None:
            return -1.0
        size = (24, 34)
        a = cv2.cvtColor(cv2.resize(canon_bgr, size, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2LAB).astype(np.float32).ravel()
        b = cv2.cvtColor(cv2.resize(ref, size, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2LAB).astype(np.float32).ravel()
        a -= a.mean(); b -= b.mean()
        return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
    except Exception:
        return -1.0


def identify(canon_bgr):
    read = read_scan(canon_bgr)
    candidates = []
    for n in read["numbers"][:4]:
        q = f"number:{n[0]} set.printedTotal:{n[1]}" if isinstance(n, tuple) else f"number:{n}"
        for c in _query(q):
            if c["id"] not in {x["id"] for x in candidates}:
                candidates.append(c)
    seen = " ".join(read["name_words"])
    def name_score(c):  # "Lance's Charizard" may OCR as "anescharizard": match the card's words inside it
        return sum(1 for t in re.findall(r"[a-zé]{4,}", c["name"].lower()) if t in seen)
    candidates = candidates[:8]
    if len(candidates) > 1:  # several cards share a number: the one that looks like the scan wins
        for c in candidates:
            c["match"] = round(_image_similarity(canon_bgr, c["image"]), 3)
    candidates.sort(key=lambda c: (-name_score(c), -c.get("match", 0)))
    return {"read": read, "candidates": candidates}


def search(text):
    """Free-text search: a name, optionally followed by a number like 160/159 or SWSH133."""
    text = text.strip()
    num = NUM_TOTAL.search(text)
    promo = PROMO.search(text.upper())
    name = NUM_TOTAL.sub("", text)
    name = PROMO.sub("", name.upper()).strip() if promo else name.strip()
    parts = []
    if name:
        parts.append(f'name:"{name.strip()}*"')
    if num:
        parts.append(f"number:{num.group(1).lstrip('0') or '0'} set.printedTotal:{num.group(2)}")
    elif promo:
        parts.append(f"number:{promo.group(1)}{promo.group(2)}")
    if not parts:
        return []
    return _query(" ".join(parts))
