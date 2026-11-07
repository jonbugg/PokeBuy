"""Graded prices: real eBay sales from CompsAPI when a key is set, else eBay asking prices.

Sold prices (last sale, 30-day average, every sale for the last 90 days) come from CompsAPI
(compsapi.com, COMPSAPI_API_KEY in .env), which reads completed eBay sales and tags each with its grader
and grade, TAG included. One lookup per grade per card; the free plan allows 100 lookups a month, so
results are cached for a day.

Without that key, the fallback below uses the PokeBuy eBay developer keys in .env.

eBay only shares *sold* prices through its Marketplace Insights API, which needs separate approval
(these keys don't have it). So this reads current Buy It Now listings through the Browse API, filtered by
eBay's own "Professional Grader" and "Grade" item details, and keeps only listings whose title carries
the card's number. Asking prices run a little above what cards sell for, so the estimate is the lower
quartile of the asking prices, not the average.
"""

import base64
import json
import re
import statistics
import time
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "ebay_cache.json"
CACHE_HOURS = 12
CATEGORY = "183454"  # Collectible Card Games > CCG Individual Cards
SEARCH = "https://api.ebay.com/buy/browse/v1/item_summary/search"
COMPS = "https://api.compsapi.com/v1/sold"
SOLD_DAYS = 90

GRADERS = {
    "PSA": "Professional Sports Authenticator (PSA)",
    "CGC": "Certified Guaranty Company (CGC)",
    "TAG": "Technical Authentication & Grading (TAG)",
}
# Value field in the "Is it worth grading?" panel -> (grader, eBay grade, keep Pristine 10s?)
FIELDS = {
    "psa10": ("PSA", "10", True),
    "tag10": ("TAG", "10", False),
    "cgc10": ("CGC", "10", False),
    "g9": ("PSA", "9", True),
    "g8": ("PSA", "8", True),
}
JUNK = re.compile(r"\b(lot|bundle|proxy|custom|replica|reprint|fake|orica|digital|cracked|empty|case only|jumbo|oversized?|xxl|"
                  r"no card|japanese|japan|jpn|chinese|korean|sgc|bgs|beckett)\b|\bx\s?\d\b|\d\s?x\b", re.I)

_token = {"value": None, "expires": 0}


def _keys():
    env = dotenv_values(ROOT / ".env")
    return (env.get("EBAY_APP_ID") or "").strip(), (env.get("EBAY_CERT_ID") or "").strip()


def available():
    return all(_keys())


def _comps_key():
    return (dotenv_values(ROOT / ".env").get("COMPSAPI_API_KEY") or "").strip()


def sold_available():
    return bool(_comps_key())


def _sold(q, grader, grade):
    params = {"q": q, "grader": grader, "grade": grade, "days": SOLD_DAYS, "size": 240,  # eBay results scanned (the max); matches come back after filtering
              "cards": 1, "exclude": "junk"}
    headers = {"X-API-Key": _comps_key(), "User-Agent": "GradeCheck/1.0 (personal card grading tool)"}
    for attempt in range(3):
        try:
            r = httpx.get(COMPS, params=params, headers=headers, timeout=60)
        except httpx.HTTPError:
            time.sleep(2 + attempt)
            continue
        try:
            body = r.json()
        except ValueError:
            body = {}
        if r.status_code == 200 and body.get("ok", True):
            return body.get("items") or []
        err = str(body.get("error") or f"HTTP {r.status_code}")
        if r.status_code == 429 and "quota" in err:
            raise RuntimeError("CompsAPI's monthly lookups are used up (they reset on the 1st). Showing eBay asking prices.")
        if r.status_code in (401, 403):
            raise RuntimeError(f"CompsAPI didn't accept the key in .env ({err}).")
        if r.status_code == 429:
            time.sleep(min(int(r.headers.get("Retry-After", "6") or 6), 20))
            continue
        if r.status_code == 400:
            raise RuntimeError(f"CompsAPI: {err}")
        time.sleep(2 + attempt)
    raise RuntimeError("CompsAPI didn't answer. Try again in a minute.")


def _when(iso):
    return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()


def _sold_summary(items, card, keep_pristine):
    """Last sale, 30-day average and the sale list, from completed eBay sales for one grader+grade."""
    sales = []
    for it in items:
        title = it.get("title") or ""
        if not _matches(title, card, keep_pristine, it.get("card")):
            continue
        try:
            price = float(it["price"])
            t = _when(it["last_sold"])
        except (KeyError, TypeError, ValueError):
            continue
        sales.append({"t": t, "price": round(price, 2), "title": title[:160], "url": it.get("url"),
                      "format": "Auction" if it.get("format") == "AUCTION" else "Buy It Now",
                      "shipping": it.get("shipping_cost")})
    sales.sort(key=lambda x: -x["t"])
    if not sales:
        return {"n90": 0, "sales": []}
    med = statistics.median(x["price"] for x in sales)
    for x in sales:  # mislabelled listings (wrong card, empty slab) sit far from everything else
        x["outlier"] = not (0.4 * med <= x["price"] <= 3 * med)
    ok = [x for x in sales if not x["outlier"]] or sales
    now = time.time()
    last30 = [x["price"] for x in ok if now - x["t"] <= 30 * 86400]
    return {
        "last": {k: ok[0][k] for k in ("t", "price", "url", "format", "title")},
        "avg30": round(statistics.mean(last30), 2) if last30 else None,
        "median30": round(statistics.median(last30), 2) if last30 else None,
        "n30": len(last30),
        "median90": round(statistics.median(x["price"] for x in ok), 2),
        "n90": len(ok),
        "sales": sales[:150],
    }


def _access_token():
    if _token["value"] and time.time() < _token["expires"]:
        return _token["value"]
    app, cert = _keys()
    if not (app and cert):
        raise RuntimeError("No eBay keys in .env (EBAY_APP_ID, EBAY_CERT_ID).")
    r = httpx.post("https://api.ebay.com/identity/v1/oauth2/token",
                   headers={"Authorization": "Basic " + base64.b64encode(f"{app}:{cert}".encode()).decode(),
                            "Content-Type": "application/x-www-form-urlencoded"},
                   data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
                   timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"eBay sign-in failed (HTTP {r.status_code}). Check the keys in .env.")
    d = r.json()
    _token.update(value=d["access_token"], expires=time.time() + int(d.get("expires_in", 7200)) - 120)
    return _token["value"]


def _search(q, grader, grade):
    params = {"q": q, "category_ids": CATEGORY, "limit": 100, "filter": "buyingOptions:{FIXED_PRICE}",
              "aspect_filter": f"categoryId:{CATEGORY},Professional Grader:{{{GRADERS[grader]}}},Grade:{{{grade}}}"}
    for attempt in range(3):
        try:
            r = httpx.get(SEARCH, params=params, timeout=25, headers={
                "Authorization": f"Bearer {_access_token()}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"})
        except httpx.HTTPError:
            time.sleep(1 + attempt)
            continue
        if r.status_code == 200:
            return r.json().get("itemSummaries", []) or []
        if r.status_code == 401:
            _token["value"] = None
        time.sleep(1 + attempt)
    raise RuntimeError("eBay search didn't answer. Try again in a minute.")


def _matches(title, card, keep_pristine, tagged=None):
    if JUNK.search(title) or (not keep_pristine and re.search(r"pristine", title, re.I)):
        return False
    tagged = tagged or {}
    if not keep_pristine and re.search(r"pristine", str(tagged.get("grade_label") or ""), re.I):
        return False
    num = str(card.get("number", "")).lstrip("0") or "0"
    digits = re.sub(r"\D", "", num).lstrip("0")
    # The longest word of the name ("Charizard" in "Lance's Charizard V"): sellers vary the rest.
    name = max(re.findall(r"[a-zé]+", re.sub(r"\(.*?\)", "", card.get("name", "")).lower()) or [""], key=len)
    if name not in title.lower():
        return False
    # CompsAPI reads the number from the title; promos are often listed as "#133" instead of "SWSH133".
    tn = re.sub(r"\D", "", str(tagged.get("card_number") or "").split("/")[0]).lstrip("0")
    if digits and tn == digits:
        return True
    if digits and digits != num and re.search(rf"#\s*0*{digits}(?!\d)", title):
        return True
    # The number may be written "160/159", "#160", "160", or "SWSH133".
    if not re.search(rf"(?<![\d/]){re.escape(num)}(?!\d)|(?<![\d/])0*{re.escape(num)}\s*/", title, re.I):
        return False
    return True


def _summary(prices, url):
    prices = sorted(prices)
    if not prices:
        return {"n": 0, "estimate": None, "url": url}
    med = statistics.median(prices)
    kept = [p for p in prices if 0.5 * med <= p <= 3 * med] or prices  # drop stray mislisted items
    q1 = kept[0] if len(kept) < 4 else statistics.quantiles(kept, n=4)[0]
    return {"n": len(kept), "estimate": round(q1, 2), "low": kept[0], "median": round(statistics.median(kept), 2),
            "high": kept[-1], "url": url}


def _cache():
    try:
        return json.loads(CACHE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def graded_prices(card, refresh=False):
    """Asking-price summary per value field for an identified card (from cards.identify / cards.search)."""
    total = card.get("set_total")
    q = f"{re.sub(r'[()]', '', card['name'])} {card['number']}" + (f"/{total}" if total and str(card['number']).isdigit() else "")
    key = f"{card.get('id') or q}"
    cache = _cache()
    hit = cache.get(key)
    sold_on = sold_available()
    if hit and not refresh and time.time() - hit["t"] < CACHE_HOURS * 3600 and hit["data"].get("sold_enabled") == sold_on:
        return hit["data"]
    out, sold_error = {}, None
    for field, (grader, grade, keep_pristine) in FIELDS.items():
        items = _search(q, grader, grade)
        prices = []
        for it in items:
            try:
                if (it.get("price") or {}).get("currency") == "USD" and _matches(it.get("title", ""), card, keep_pristine):
                    prices.append(float(it["price"]["value"]))
            except (KeyError, ValueError):
                pass
        label = f"{grader} {grade}"
        url = "https://www.ebay.com/sch/i.html?" + httpx.QueryParams(
            {"_nkw": f"{q} {label}", "LH_Sold": "1", "LH_Complete": "1"}).__str__()
        info = dict(_summary(prices, url), label=label)
        info["value"], info["value_source"] = info["estimate"], "ask"
        if sold_on and not sold_error:
            try:
                sold = _sold_summary(_sold(q, grader, grade), card, keep_pristine)
                info["sold"] = sold
                if sold.get("avg30") is not None:
                    info["value"], info["value_source"] = sold["avg30"], "avg30"
                elif sold.get("n90"):
                    info["value"], info["value_source"] = sold["median90"], "median90"
            except RuntimeError as e:
                sold_error = str(e)
        out[field] = info
    data = {"fields": out, "query": q, "fetched_at": time.time(), "sold_enabled": sold_on, "sold_error": sold_error,
            "sold_days": SOLD_DAYS, "source": "eBay sales via CompsAPI" if sold_on and not sold_error
            else "eBay Buy It Now listings (asking prices)"}
    if not sold_error:  # don't keep a half-failed lookup for a day
        cache[key] = {"t": time.time(), "data": data}
    CACHE.write_text(json.dumps(cache))
    return data
