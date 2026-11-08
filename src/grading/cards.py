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
# Promo numbers: "SWSH133", "SM-210", and the Scarlet & Violet style "SVP EN 074" (set code, language, number).
PROMO = re.compile(r"\b(SWSH|SVP|SV|SM|XY|BW|TG|GG|HGSS|DP)\s?(?:EN\s?)?-?(\d{1,3})\b")


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


PROMO_SETS = {"svp": "SVP", "swshp": "", "smp": "", "xyp": "", "bwp": "", "dpp": "", "hsp": "", "np": "", "basep": ""}


def _display_number(c):
    """The number as printed on the card: Scarlet & Violet promos read 'SVP 074' (the database stores '74')."""
    n, set_id = str(c["number"]), c["set"]["id"]
    if set_id == "svp" and n.isdigit():
        return f"SVP {int(n):03d}"
    return n


def _card(c):
    prices = (c.get("tcgplayer") or {}).get("prices") or {}
    variants = {k: v.get("market") for k, v in prices.items() if v.get("market")}
    market = max(variants.values()) if variants else None
    return {
        "id": c["id"], "name": c["name"], "number": _display_number(c),
        "set": c["set"]["name"], "set_total": None if c["set"]["id"] in PROMO_SETS else c["set"].get("printedTotal"),
        "series": c["set"].get("series"),
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


CLAUDE_MODEL = "claude-opus-5-5"
CLAUDE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "The card's name as printed, e.g. 'Charizard ex', 'Lance's Charizard V'"},
        "number": {"type": "string", "description": "Collector number exactly as printed, e.g. '160/159', 'SWSH133', 'SVP EN 074', 'TG05/TG30'"},
        "set_name": {"type": "string", "description": "The set or promo series if you can tell, else empty"},
        "language": {"type": "string", "description": "Card language, e.g. 'English', 'Japanese'"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["name", "number", "set_name", "language", "confidence"],
    "additionalProperties": False,
}


def _claude_key():
    import os
    return (dotenv_values(ROOT / ".env").get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def claude_read(canon_bgr):
    """Ask Claude to read the card from the front scan (name, printed number, set). Used when OCR can't:
    stylised titles and small promo codes like 'SVP EN 074' defeat Tesseract. Returns a dict or None."""
    key = _claude_key()
    if not key:
        return None
    try:
        import anthropic
    except ImportError:
        return None
    import base64
    h, w = canon_bgr.shape[:2]
    s = 1100 / max(h, w)
    small = cv2.resize(canon_bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else canon_bgr
    ok, jpg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        return None
    client = anthropic.Anthropic(api_key=key, max_retries=2, timeout=60.0)
    request = dict(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.standard_b64encode(jpg.tobytes()).decode()}},
            {"type": "text", "text": "This is a flatbed scan of the front of a trading card. Read it: the card's name, "
                                     "its collector number exactly as printed (bottom corner, e.g. '160/159', 'SWSH133', "
                                     "'SVP EN 074'), the set or promo series, and the language. Report only what the card "
                                     "shows; if something isn't legible, give your best reading and set confidence to low."},
        ]}],
        extra_body={"output_config": {"effort": "low", "format": {"type": "json_schema", "schema": CLAUDE_SCHEMA}},
                    "fallbacks": "default"},
        extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
    )
    try:
        r = client.messages.create(**request)
    except anthropic.APIStatusError as e:
        if e.status_code == 400:  # e.g. an account without the fallback beta: retry plainly once
            request["extra_body"].pop("fallbacks", None)
            request.pop("extra_headers", None)
            try:
                r = client.messages.create(**request)
            except anthropic.APIError:
                return None
        else:
            return None
    except anthropic.APIError:
        return None
    if r.stop_reason == "refusal":
        return None
    text = next((b.text for b in r.content if getattr(b, "type", "") == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _claude_queries(c):
    """Pokémon TCG API searches for what Claude read."""
    qs = []
    num = (c.get("number") or "").upper().replace(" EN ", " ").replace("-", " ")
    name = (c.get("name") or "").strip()
    m = NUM_TOTAL.search(num)
    p = re.search(r"\b(SVP|SWSH|SM|XY|BW|DP|HGSS)\s?(\d{1,3})\b", num)
    if m:
        qs.append(f"number:{m.group(1).lstrip('0') or '0'} set.printedTotal:{m.group(2)}")
    elif p:
        series, n = p.group(1), p.group(2).lstrip("0") or "0"
        qs.append(f"number:{n} set.id:svp" if series == "SVP" else f"number:{series}{n}")
    if name:
        clean = re.sub(r'["*]', "", name)
        qs.append(f'name:"{clean}"' + (f" number:{m.group(1).lstrip('0')}" if m else ""))
    return qs


def identify(canon_bgr):
    read = read_scan(canon_bgr)
    candidates = []
    for n in read["numbers"][:4]:
        q = f"number:{n[0]} set.printedTotal:{n[1]}" if isinstance(n, tuple) else f"number:{n}"
        for c in _query(q):
            if c["id"] not in {x["id"] for x in candidates}:
                candidates.append(c)
    if not candidates:
        # The text reader found no usable number: let Claude read the card instead.
        cr = claude_read(canon_bgr)
        if cr:
            read["claude"] = cr
            read["name_words"] = sorted(set(read["name_words"]) | set(re.findall(r"[a-zé']{4,}", cr.get("name", "").lower())))
            for q in _claude_queries(cr):
                try:
                    found = _query(q)
                except RuntimeError:
                    found = []
                for c in found:
                    if c["id"] not in {x["id"] for x in candidates}:
                        candidates.append(c)
                if candidates and q.startswith("number:"):
                    break
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
