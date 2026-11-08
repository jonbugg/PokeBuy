#!/usr/bin/env python3
"""Grade Check: scan a card on the network scanner and estimate TAG / PSA / CGC grades."""

import io
import json
import re
import threading
import time
import uuid
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, abort, jsonify, render_template, request, send_from_directory
from PIL import Image

from src.grading import cards, closeups, fees, locate, market, measure, relief, standards, surface, tag_compare
from src.grading.scanner import DEFAULT_REGION, PLATEN_REGION, PREVIEW_DPI, Scanner

ROOT = Path(__file__).parent
SCANS = ROOT / "data" / "scans"
SCANS.mkdir(parents=True, exist_ok=True)
SLOTS = ("front", "back", "front_rot", "back_rot", "front_r90", "front_r270", "back_r90", "back_r270")
QUARTER_SLOTS = ("front_r90", "front_r270", "back_r90", "back_r270")  # extra light directions for the surface check
LAST_REGION = SCANS / "last_region.json"

app = Flask(__name__)
_scan_lock = threading.Lock()
_scanner = None


def scanner():
    global _scanner
    if _scanner is None:
        _scanner = Scanner.discover()
    return _scanner


def _session_dir(sid):
    if not sid or not all(c.isalnum() or c == "-" for c in sid):
        abort(400, "bad session id")
    d = SCANS / sid
    d.mkdir(exist_ok=True)
    return d


def _measurement_json(m):
    art = float(getattr(m, "print_at_edge", 0.0))
    if m.edges_reliable and art > 0.1:
        m.warnings.append(f"Artwork reaches this card's edge along about {round(art * 100)}% of it, so edge and corner "
                          "findings are less certain. Check them in the zoom viewer, or add the 180° scan.")
    return {"centering": m.centering, "edges": m.edges, "corners": m.corners,
            "warnings": m.warnings, "dims_in": m.dims_in, "edges_reliable": m.edges_reliable,
            "dark_card": bool(getattr(m, "dark_card", False)), "art_at_edge": round(art, 3)}


def _closeup_urls(sid, rendered):
    base = f"/scans/{sid}/"
    t = f"?t={int(time.time())}"
    tile = lambda v: {**v, "img": base + v["img"] + t, "img_ann": base + v.get("img_ann", v["img"]) + t}
    return {
        "view_size": rendered.get("view_size"),
        "full": base + rendered["full"] + t,
        "corners": {k: tile(v) for k, v in rendered["corners"].items()},
        "edges": {k: tile(v) for k, v in rendered["edges"].items()},
        "findings": [{**f, "img": base + f["img"] + t} for f in rendered["findings"]],
    }


class WrongSide(Exception):
    pass


def _small(canon):
    v = cv2.resize(cv2.cvtColor(canon, cv2.COLOR_BGR2GRAY), (25, 35), interpolation=cv2.INTER_AREA).astype(np.float32).ravel()
    return (v - v.mean()) / (v.std() + 1e-6)


def _likeness(a, b):
    """How alike two straightened scans look, either way up (-1..1)."""
    sa = _small(a)
    return max(float(np.dot(sa, _small(b))) / len(sa), float(np.dot(sa, _small(cv2.rotate(b, cv2.ROTATE_180)))) / len(sa))


def _check_side(d, slot, canon):
    """Refuse a scan that shows the other side of the card (e.g. the back left face-down for a front scan)."""
    side = slot.split("_")[0]
    other = "back" if side == "front" else "front"
    load = lambda names: [cv2.imread(str(d / f"{n}_canon.png")) for n in names if (d / f"{n}_canon.png").exists()]
    same = load([n for n in (side, f"{side}_rot", f"{side}_r90", f"{side}_r270") if n != slot])
    opp = load([other, f"{other}_rot"])
    if not opp:
        return
    like_opp = max(_likeness(canon, x) for x in opp)
    like_same = max((_likeness(canon, x) for x in same), default=None)
    if like_opp > 0.8 and (like_same is None or like_opp > like_same + 0.1):
        raise WrongSide(f"This looks like the card's {other}, not its {side}. Flip the card over and scan again; "
                        f"nothing was saved.")


def _upside_down(d, slot, canon):
    """True when this scan is the same way up as its 180° partner (or the opposite way up from its
    first-scan partner), i.e. the card went on the glass the wrong way round for this slot."""
    if slot in QUARTER_SLOTS:  # a quarter turn: either way up works, it's matched to the first scan later
        return False
    side = slot.split("_")[0]
    partner = f"{side}_rot" if slot == side else side
    f = d / f"{partner}_canon.png"
    if not f.exists():
        return False
    ref = cv2.imread(str(f))
    sa = _small(canon)
    same_way = float(np.dot(sa, _small(ref))) / len(sa)
    turned = float(np.dot(sa, _small(cv2.rotate(ref, cv2.ROTATE_180)))) / len(sa)
    return same_way > turned + 0.2  # partners should match only once one is turned 180°


def _process(sid, slot, raw: bytes, src_ppi):
    d = _session_dir(sid)
    img = measure.load(raw)
    m = measure.measure_image(img, src_ppi=src_ppi)
    _check_side(d, slot, m.canon)
    if _upside_down(d, slot, m.canon):
        # Same way up as this side's other scan. The 180° pair only works when the card was physically
        # turned under the scanner's light, so turning the image afterwards won't do: say so instead.
        side = slot.split("_")[0]
        partner = f"{side} 180°" if slot == side else side
        raise WrongSide(f"This scan is the same way up as the {partner} scan already saved. If it's meant to be "
                        f"the {partner} scan, scan it into that step; otherwise turn the card 180° and scan again. "
                        f"Nothing was saved.")
    for old in d.glob(f"{slot}_cu_*.jpg"):  # close-ups from an earlier pass of this slot
        old.unlink()
    (d / f"{slot}_raw.jpg").write_bytes(raw)
    cv2.imwrite(str(d / f"{slot}_canon.png"), m.canon)
    cv2.imwrite(str(d / f"{slot}_overlay.jpg"), measure.overlay(m), [cv2.IMWRITE_JPEG_QUALITY, 88])
    data = _measurement_json(m)
    data["ppi"] = m.ppi
    data["findings"] = closeups.build_findings(m)
    cv2.imwrite(str(d / f"{slot}_view.jpg"), m.canon_view, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if slot.endswith("_rot"):
        # Turned upright again, so it lines up with the first scan of this side for side-by-side zooming.
        cv2.imwrite(str(d / f"{slot[:-4]}_view_r180.jpg"), cv2.rotate(m.canon_view, cv2.ROTATE_180), [cv2.IMWRITE_JPEG_QUALITY, 95])
    data["view_pad"] = m.view_pad
    vw = 900
    small = cv2.resize(m.canon_view, (vw, int(m.canon_view.shape[0] * vw / m.canon_view.shape[1])), interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(d / f"{slot}_center.jpg"), small, [cv2.IMWRITE_JPEG_QUALITY, 90])
    data["center_view"] = {"img": f"/scans/{sid}/{slot}_center.jpg?t={int(time.time())}",
                           "margin_mm": round(m.view_pad * m.mmpp, 3), "card_mm": [63.5, 88.9]}
    data["subscores"] = closeups.subscores(m)
    outline = m._outline[0] if getattr(m, "_outline", None) is not None else None
    if outline is not None:
        np.save(d / f"{slot}_outline.npy", outline.astype(np.float32))
    data["closeups"] = _closeup_urls(sid, closeups.render(m.canon_view, m.view_pad, data["findings"], d, slot, m.ppi, outline))
    (d / f"{slot}.json").write_text(json.dumps(data))
    return data


@app.route("/")
def index():
    return render_template("grade.html")


@app.route("/api/scanner")
def scanner_status():
    try:
        s = scanner()
        return jsonify({"ok": True, "state": s.status(), "url": s.base_url, "located": LAST_REGION.exists()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/session", methods=["POST"])
def new_session():
    sid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    _session_dir(sid)
    return jsonify({"session": sid})


def _meta(d):
    f = d / "meta.json"
    if f.exists():
        return json.loads(f.read_text())
    # Older sessions: the folder name starts with the date and time it was created.
    try:
        created = time.mktime(time.strptime(d.name[:15], "%Y%m%d-%H%M%S"))
    except ValueError:
        created = d.stat().st_mtime
    return {"name": "", "graded_at": created}


@app.route("/api/meta/<sid>", methods=["POST"])
def save_meta(sid):
    """Merge edits into a card's saved details: name, identified card, sale values, actual grade result."""
    d = _session_dir(sid)
    meta = _meta(d)
    body = request.json or {}
    if "name" in body:
        meta["name"] = str(body["name"])[:120].strip()
    if "card" in body and (body["card"] is None or isinstance(body["card"], dict)):
        meta["card"] = body["card"]
        meta.pop("market", None)  # eBay prices belonged to the previous card
        if body["card"] and not meta.get("name"):
            c = body["card"]
            total = f"/{c['set_total']}" if c.get("set_total") and str(c.get("number", "")).isdigit() else ""
            meta["name"] = f"{c.get('name', '')} · {c.get('set', '')} {c.get('number', '')}{total}".strip()
    if isinstance(body.get("values"), dict):
        before = meta.get("values") or {}
        meta["values"] = {k: (None if v in ("", None) else float(v)) for k, v in body["values"].items()
                          if k in ("raw", "psa10", "tag10", "cgc10", "g9", "g8", "shipping")}
        # A value the person changed is theirs now: price refreshes leave it alone.
        meta["auto_fields"] = [k for k in meta.get("auto_fields", [])
                               if meta["values"].get(k) is not None and before.get(k) == meta["values"].get(k)]
    if "ignore" in body:
        # The person looked at a finding and disagrees: keep it on the report, leave it out of the grade.
        ignored = set(meta.get("ignored") or [])
        key = str(body["ignore"])[:200]
        if body.get("ignored", True):
            ignored.add(key)
        else:
            ignored.discard(key)
        meta["ignored"] = sorted(ignored)
    if "actual" in body:
        a = body["actual"]
        meta["actual"] = None if not a else {
            "company": str(a.get("company", ""))[:10], "grade": str(a.get("grade", ""))[:20],
            "score": int(a["score"]) if str(a.get("score", "")).isdigit() else None,
            "cert": str(a.get("cert", ""))[:20], "recorded_at": time.time()}
    (d / "meta.json").write_text(json.dumps(meta))
    return jsonify(meta)


@app.route("/api/market/<sid>", methods=["POST"])
def market_prices(sid):
    """Look up graded asking prices on eBay for the identified card and fill the empty value fields."""
    d = _session_dir(sid)
    meta = _meta(d)
    card = meta.get("card")
    if not card:
        return jsonify({"error": "Identify the card first."}), 400
    body = request.json or {}
    try:
        data = market.graded_prices(card, refresh=bool(body.get("refresh")))
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 502
    values = dict(meta.get("values") or {})
    if values.get("raw") is None and card.get("market"):
        values["raw"] = card["market"]
    auto = set(meta.get("auto_fields") or [])
    for field, info in data["fields"].items():
        # Fill empty boxes, and update ones this lookup filled before; never overwrite a typed value.
        if info.get("value") is not None and (body.get("overwrite") or values.get(field) is None or field in auto):
            values[field] = round(info["value"])
            auto.add(field)
    meta["auto_fields"] = sorted(auto)
    meta["values"], meta["market"] = values, data
    (d / "meta.json").write_text(json.dumps(meta))
    return jsonify(meta)


@app.route("/api/market-status")
def market_status():
    return jsonify({"listings": market.available(), "sold": market.sold_available()})


@app.route("/api/fees")
def fee_table():
    return jsonify(fees.all_fees())


@app.route("/api/identify/<sid>", methods=["POST"])
def identify_card(sid):
    d = _session_dir(sid)
    canon = d / "front_canon.png"
    if not canon.exists():
        return jsonify({"error": "Scan the front first."}), 400
    try:
        return jsonify(cards.identify(cv2.imread(str(canon))))
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/cards")
def card_search():
    q = request.args.get("q", "")[:80]
    try:
        return jsonify({"candidates": cards.search(q)})
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 502


@app.route("/library")
def library_page():
    return render_template("library.html")


@app.route("/api/library")
def library():
    cards = []
    for d in sorted(SCANS.iterdir(), reverse=True):
        snap = d / "report.json"
        if not (d.is_dir() and snap.exists()):
            continue
        r = json.loads(snap.read_text())
        meta = _meta(d)
        est = r.get("estimates", {})
        front = r.get("front") or {}
        thumb = f"/scans/{d.name}/front_center.jpg" if (d / "front_center.jpg").exists() else (
            f"/scans/{d.name}/back_center.jpg" if (d / "back_center.jpg").exists() else None)
        missing = [side for side in ("front", "back") if not r.get(side)]
        cards.append({
            "id": d.name, "name": meta.get("name") or "", "graded_at": meta.get("graded_at"),
            "missing": missing, "card_id": (meta.get("card") or {}).get("id"), "fp": _fingerprint(d),
            "thumb": thumb,
            "grades": {k: {"grade": est[k]["grade"], "score_range": est[k].get("score_range")} for k in ("TAG", "PSA", "CGC") if k in est},
            "counts": est.get("counts"), "centering": (front.get("centering") or {}).get("worst"),
            "dims": front.get("dims_in"), "surface_checked": r.get("surface_checked", False),
            "card": meta.get("card"), "values": meta.get("values"), "actual": meta.get("actual"),
            "odds": {k: est[k].get("odds") for k in ("TAG", "PSA", "CGC") if k in est},
        })
    # The same card scanned more than once (a rescan, or another copy): show the newest, with the
    # earlier scans listed under it.
    groups = []
    for c in cards:  # newest first
        home = next((g for g in groups if _same_card(g, c)), None)
        if home:
            home["earlier"].append({k: c[k] for k in ("id", "name", "graded_at", "missing", "grades", "thumb")})
        else:
            c["earlier"] = []
            groups.append(c)
    for g in groups:
        g.pop("fp", None)
    return jsonify(groups)


@app.route("/api/library.csv")
def library_csv():
    import csv as _csv
    import io as _io
    rows = library().get_json()
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["id", "name", "checked", "set", "number", "raw_value", "TAG_est", "PSA_est", "CGC_est",
                "red", "yellow", "centering_worst", "actual_company", "actual_grade", "actual_score", "cert"])
    for c in rows:
        card, act, g = c.get("card") or {}, c.get("actual") or {}, c.get("grades") or {}
        w.writerow([c["id"], c["name"], time.strftime("%Y-%m-%d", time.localtime(c["graded_at"] or 0)),
                    card.get("set", ""), card.get("number", ""), (c.get("values") or {}).get("raw") or card.get("market") or "",
                    g.get("TAG", {}).get("grade", ""), g.get("PSA", {}).get("grade", ""), g.get("CGC", {}).get("grade", ""),
                    (c.get("counts") or {}).get("red", ""), (c.get("counts") or {}).get("yellow", ""), c.get("centering") or "",
                    act.get("company", ""), act.get("grade", ""), act.get("score") or "", act.get("cert", "")])
    return app.response_class(buf.getvalue(), mimetype="text/csv",
                              headers={"Content-Disposition": "attachment; filename=grade-check-library.csv"})


@app.route("/api/card/<sid>", methods=["DELETE"])
def delete_card(sid):
    d = _session_dir(sid)
    trash = SCANS / ".deleted"
    trash.mkdir(exist_ok=True)
    d.rename(trash / d.name)  # recoverable: moved aside, not erased
    return jsonify({"ok": True})


GUIDE_GREY = "#8c8c8c"  # mid-grey: well clear of black borders below and white edge wear above


@app.route("/guide")
def guide():
    tone = "grey" if request.args.get("tone") == "grey" else "black"
    return render_template("guide.html", tone=tone, block=GUIDE_GREY if tone == "grey" else "#000")


def _locked_scan(**kw):
    if not _scan_lock.acquire(blocking=False):
        raise RuntimeError("A scan is already running.")
    try:
        return scanner().scan(**kw)
    finally:
        _scan_lock.release()


@app.route("/api/locate/<sid>", methods=["POST"])
def locate_card(sid):
    d = _session_dir(sid)
    try:
        raw = _locked_scan(dpi=PREVIEW_DPI, region=PLATEN_REGION)
    except Exception as e:
        return jsonify({"error": f"Scanner: {e}"}), 502
    (d / "preview_raw.jpg").write_bytes(raw)
    info, annotated = locate.locate(measure.load(raw), PREVIEW_DPI)
    cv2.imwrite(str(d / "preview.jpg"), annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
    info["preview"] = f"/scans/{sid}/preview.jpg?t={int(time.time())}"
    if info["region"]:
        (d / "region.json").write_text(json.dumps(info["region"]))
        LAST_REGION.write_text(json.dumps(info["region"]))
    return jsonify(info)


@app.route("/api/scan/<sid>/<slot>", methods=["POST"])
def scan(sid, slot):
    if slot not in SLOTS:
        abort(400)
    dpi = int((request.json or {}).get("dpi", 600))
    if dpi not in (300, 600, 1200):
        abort(400, "dpi must be 300, 600 or 1200")
    region_file = _session_dir(sid) / "region.json"
    if not region_file.exists():
        region_file = LAST_REGION
    region = tuple(json.loads(region_file.read_text())) if region_file.exists() else DEFAULT_REGION
    try:
        raw = _locked_scan(dpi=dpi, region=region)
    except Exception as e:
        return jsonify({"error": f"Scanner: {e}"}), 502
    return _measure_response(sid, slot, raw, dpi)


@app.route("/api/upload/<sid>/<slot>", methods=["POST"])
def upload(sid, slot):
    if slot not in SLOTS or "file" not in request.files:
        abort(400)
    raw = request.files["file"].read()
    try:
        dpi = Image.open(io.BytesIO(raw)).info.get("dpi", (None,))[0]
        dpi = int(dpi) if dpi and dpi >= 150 else None
    except Exception:
        dpi = None
    return _measure_response(sid, slot, raw, dpi)


def _measure_response(sid, slot, raw, dpi):
    try:
        data = _process(sid, slot, raw, dpi)
    except measure.CardNotFound as e:
        d = _session_dir(sid)
        (d / f"{slot}_raw.jpg").write_bytes(raw)
        return jsonify({"error": str(e), "raw": f"/scans/{sid}/{slot}_raw.jpg"}), 422
    except WrongSide as e:
        return jsonify({"error": str(e), "wrong_side": True}), 409
    data["overlay"] = f"/scans/{sid}/{slot}_overlay.jpg?t={int(time.time())}"
    return jsonify(data)


def _auto_identify(d):
    """Name the card from its front scan the first time a report is built, when the match is clear."""
    meta = _meta(d)
    canon = d / "front_canon.png"
    if meta.get("card") or meta.get("identify_tried") or not canon.exists():
        return
    meta["identify_tried"] = True
    try:
        res = cards.identify(cv2.imread(str(canon)))
    except Exception:  # lookup service down: the "Identify from scan" button is still there
        res = {"candidates": []}
    cands = res.get("candidates") or []
    words = " ".join(res.get("read", {}).get("name_words", []))
    top = cands[0] if cands else None
    named = top and any(t in words for t in re.findall(r"[a-zé]{4,}", top["name"].lower()))
    if top and (len(cands) == 1 or named or top.get("match", 0) >= 0.85):
        meta["card"] = top
        if not meta.get("name"):
            meta["name"] = f"{top['name']} · {top['set']} {top['number']}" + (f"/{top['set_total']}" if top.get("set_total") and str(top["number"]).isdigit() else "")
        values = dict(meta.get("values") or {})
        if values.get("raw") is None and top.get("market"):
            values["raw"] = top["market"]
        meta["values"] = values
    (d / "meta.json").write_text(json.dumps(meta))


def _fingerprint(d):
    """A tiny normalised greyscale of the front (or back) scan, to spot the same card scanned twice."""
    f = d / "fingerprint.npy"
    if f.exists():
        return np.load(f)
    for side in ("front", "back"):
        img = cv2.imread(str(d / f"{side}_canon.png"), cv2.IMREAD_GRAYSCALE)
        if img is not None:
            v = cv2.resize(img, (25, 35), interpolation=cv2.INTER_AREA).astype(np.float32).ravel()
            v = (v - v.mean()) / (v.std() + 1e-6)
            fp = np.concatenate([[0.0 if side == "front" else 1.0], v])
            np.save(f, fp)
            return fp
    return None


def _same_card(a, b):
    if a["card_id"] and b["card_id"]:
        return a["card_id"] == b["card_id"]
    fa, fb = a["fp"], b["fp"]
    if fa is None or fb is None or fa[0] != fb[0]:
        return False
    return float(np.dot(fa[1:], fb[1:]) / (len(fa) - 1)) > 0.9


def _upright_like(canon, ref):
    """A quarter-turn scan, straightened, can come out either way up: pick the way that matches the first scan."""
    if canon.shape != ref.shape:
        canon = cv2.resize(canon, (ref.shape[1], ref.shape[0]), interpolation=cv2.INTER_AREA)
    turned = cv2.rotate(canon, cv2.ROTATE_180)
    sr = _small(ref)
    same = float(np.dot(_small(canon), sr)) / len(sr)
    flip = float(np.dot(_small(turned), sr)) / len(sr)
    return canon if same >= flip else turned


def _merge_marks(first, second, shape, tol_mm=1.5):
    """Combine marks from the two light pairs; a mark both pairs saw is kept once, tagged with both."""
    h, w = shape[:2]
    mm_x, mm_y = 63.5 / 100, 88.9 / 100  # mm per percent across / down
    out = [dict(m) for m in first]
    for m in second:
        m = dict(m, light=["90/270"])
        near = next((o for o in out if np.hypot((o["x_pct"] - m["x_pct"]) * mm_x, (o["y_pct"] - m["y_pct"]) * mm_y) <= tol_mm), None)
        if near is not None:
            near["light"] = sorted(set(near.get("light", [])) | {"90/270"})
            near["strength"] = max(near["strength"], m["strength"])
            near.setdefault("pair_q", m.get("pair"))
        else:
            out.append(m)
    out.sort(key=lambda m: -m["strength"])
    return out


@app.route("/api/report/<sid>")
def report(sid):
    d = _session_dir(sid)
    load = lambda s: json.loads((d / f"{s}.json").read_text()) if (d / f"{s}.json").exists() else None
    front, back = load("front"), load("back")
    if not front and not back:
        return jsonify({"error": "Scan at least one side first."}), 400
    surf = {}
    surface_by_side = {}
    for side, data in (("front", front), ("back", back)):
        a, b = d / f"{side}_canon.png", d / f"{side}_rot_canon.png"
        if not (data and a.exists() and b.exists()):
            continue
        canon = cv2.imread(str(a))
        res, heat = surface.compare(canon, cv2.imread(str(b)))
        cv2.imwrite(str(d / f"{side}_surface.jpg"), heat, [cv2.IMWRITE_JPEG_QUALITY, 85])
        res["heatmap"] = f"/scans/{sid}/{side}_surface.jpg?t={int(time.time())}"
        for i, (entry, img) in enumerate(res.pop("_pairs")):
            cv2.imwrite(str(d / f"{side}_spot_{i}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
            entry["pair"] = f"/scans/{sid}/{side}_spot_{i}.jpg?t={int(time.time())}"
        for m in res["marks"] + res["debris"]:
            m["light"] = ["0/180"]
        # Second light pair: the card turned 90° and 270°, lit across it instead of along it. Marks that run
        # along one light direction barely shade in that pair, but stand out in the other.
        q90, q270 = d / f"{side}_r90_canon.png", d / f"{side}_r270_canon.png"
        res["light_pairs"] = 1
        if q90.exists() and q270.exists():
            a90, a270 = _upright_like(cv2.imread(str(q90)), canon), _upright_like(cv2.imread(str(q270)), canon)
            res2, heat2 = surface.compare(a90, cv2.rotate(a270, cv2.ROTATE_180))
            cv2.imwrite(str(d / f"{side}_surface_q.jpg"), heat2, [cv2.IMWRITE_JPEG_QUALITY, 85])
            res["heatmap_q"] = f"/scans/{sid}/{side}_surface_q.jpg?t={int(time.time())}"
            for i, (entry, img) in enumerate(res2.pop("_pairs")):
                cv2.imwrite(str(d / f"{side}_qspot_{i}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
                entry["pair"] = f"/scans/{sid}/{side}_qspot_{i}.jpg?t={int(time.time())}"
            res["light_pairs"] = 2
            # TAG-style relief map: slopes from both light pairs, shaded with one virtual light.
            along, across = relief.slopes(canon, cv2.rotate(cv2.imread(str(b)), cv2.ROTATE_180), a90, a270,
                                          data.get("ppi", 1200))
            relief_img, slope_heat = relief.render(along, across, data.get("ppi", 1200))
            cv2.imwrite(str(d / f"{side}_relief.jpg"), relief_img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            cv2.imwrite(str(d / f"{side}_slope.jpg"), slope_heat, [cv2.IMWRITE_JPEG_QUALITY, 85])
            res["relief"] = f"/scans/{sid}/{side}_relief.jpg?t={int(time.time())}"
            res["slope"] = f"/scans/{sid}/{side}_slope.jpg?t={int(time.time())}"
            res["marks"] = _merge_marks(res["marks"], res2["marks"], canon.shape)
            res["debris"] = _merge_marks(res["debris"], res2["debris"], canon.shape)
        surf[side] = res
        surface_by_side[side] = closeups.surface_findings(res["marks"], canon.shape)

    _auto_identify(d)
    ignored = set(_meta(d).get("ignored") or [])

    def parse_key(k):
        try:
            sd, region, kind, box = k.split("|")
            return sd, region, kind, [int(v) for v in box.split(",")]
        except ValueError:
            return None

    ignored_parsed = [(k, parse_key(k)) for k in ignored]

    def mark(side, f):
        f["key"] = f"{side}|{f.get('region')}|{f.get('kind')}|{','.join(str(int(v)) for v in f.get('box', []))}"
        f["ignored"] = f["key"] in ignored
        if not f["ignored"] and f.get("box"):
            # Re-measured scans move a finding by a few pixels: an ignore still applies within ~1 mm.
            cx, cy = (f["box"][0] + f["box"][2]) / 2, (f["box"][1] + f["box"][3]) / 2
            for k, pk in ignored_parsed:
                if pk and pk[0] == side and pk[1] == f.get("region") and pk[2] == f.get("kind") and len(pk[3]) == 4:
                    if np.hypot((pk[3][0] + pk[3][2]) / 2 - cx, (pk[3][1] + pk[3][3]) / 2 - cy) <= 50:
                        f["key"], f["ignored"] = k, True  # keep the saved key so Undo still finds it
                        break

    for side, found in surface_by_side.items():
        for f in found:
            mark(side, f)
    t = int(time.time())
    for side, data in (("front", front), ("back", back)):
        if not data:
            continue
        r180 = d / f"{side}_view_r180.jpg"
        data["zoom"] = {"view": f"/scans/{sid}/{side}_view.jpg?t={t}",
                        "view_r180": f"/scans/{sid}/{side}_view_r180.jpg?t={t}" if r180.exists() else None}
        # Check each corner/edge finding against the 180° scan. A yellow it didn't see is "cleared".
        rot = load(f"{side}_rot")
        findings = data.get("findings", [])
        for f in findings:
            f.pop("both", None)
            f["cleared"] = False
            mark(side, f)
        # Check each corner/edge finding against every other scan of this side: the 180° turn and, when
        # scanned, the 90° and 270° turns (light from the other two directions).
        ppi = data.get("ppi", 600)
        cw, ch, mmpp = int(2.5 * ppi), int(3.5 * ppi), 25.4 / ppi
        first = cv2.imread(str(d / f"{side}_canon.png"))
        checks = []
        for slot, label in ((f"{side}_rot", "180°"), (f"{side}_r90", "90°"), (f"{side}_r270", "270°")):
            other = rot if slot.endswith("_rot") else load(slot)
            if not other:
                continue
            ofl = [x for x in other.get("findings", []) if x.get("box")]
            if not slot.endswith("_rot"):
                c = cv2.imread(str(d / f"{slot}_canon.png"))
                if first is None or c is None:
                    continue
                if _upright_like(c, first) is c:
                    # same way up as the first scan: pre-turn its boxes so the 180° matcher lines them up
                    ofl = [dict(x, box=[cw - 1 - x["box"][2], ch - 1 - x["box"][3], cw - 1 - x["box"][0], ch - 1 - x["box"][1]]) for x in ofl]
            checks.append((label, closeups.match_in_rotated(findings, ofl, cw, ch, mmpp)))
        for i, f in enumerate(findings):
            if f.get("was_red"):
                f["severity"] = "red"  # rebuilt report: judge the original call again
            f.pop("was_red", None)
            f.pop("seen_in", None)
            seen = [(label, s[i]) for label, s in checks if s[i] is not None]
            if not seen:
                continue
            n, hits = len(seen), sum(1 for _, v in seen if v)
            confirmed = hits * 2 > n if n > 1 else hits == 1  # a majority of the other scans saw it
            f["both"] = confirmed
            if n > 1:
                f["seen_in"] = {label: bool(v) for label, v in seen}
            # A clear (red) call the other scans don't back up is more likely lighting or shadow than damage
            # (a real bent corner or chip shows whichever way the light falls): count it as borderline.
            if f["severity"] == "red" and not confirmed:
                f["severity"], f["was_red"] = "yellow", True
            f["cleared"] = f["severity"] == "yellow" and hits == 0 and not f.get("was_red")
        # Redraw this side's close-ups so boxes and tile outlines reflect cleared findings and surface marks.
        outline_file = d / f"{side}_outline.npy"
        rendered = closeups.render(cv2.imread(str(d / f"{side}_view.jpg")), data.get("view_pad", 0),
                                   findings + surface_by_side.get(side, []), d, side, data.get("ppi", 600),
                                   np.load(outline_file) if outline_file.exists() else None)
        data["closeups"] = _closeup_urls(sid, rendered)
    surface_found = [f for found in surface_by_side.values() for f in found]
    est = standards.estimate_all(front, back, surface_found)
    out = {"front": front, "back": back, "surface": surf, "estimates": est,
           "surface_checked": bool(surf), "meta": _meta(d),
           "surface_findings": [dict(f, side=side) for side, fs in surface_by_side.items() for f in fs]}
    if not (d / "meta.json").exists():
        (d / "meta.json").write_text(json.dumps(out["meta"]))
    (d / "report.json").write_text(json.dumps(out))  # snapshot for the library
    return jsonify(out)


@app.route("/api/tag-compare/<sid>")
def tag_comparison(sid):
    """Your scans against TAG-graded copies of the same card (when copies are saved for it)."""
    d = _session_dir(sid)
    snap = d / "report.json"
    card_id = (_meta(d).get("card") or {}).get("id")
    if not snap.exists() or not tag_compare.available(card_id):
        return jsonify({"available": False, "card_id": card_id})
    cache = d / "tagcmp.json"
    if cache.exists() and cache.stat().st_mtime >= snap.stat().st_mtime:
        return jsonify(json.loads(cache.read_text()))
    res = dict(tag_compare.build(d, card_id, json.loads(snap.read_text())), available=True)
    cache.write_text(json.dumps(res))
    return jsonify(res)


@app.route("/scans/<sid>/<path:name>")
def scan_file(sid, name):
    return send_from_directory(_session_dir(sid), name)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5055, debug=False, threaded=True)
