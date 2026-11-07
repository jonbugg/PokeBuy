#!/usr/bin/env python3
"""Grade Check: scan a card on the network scanner and estimate TAG / PSA / CGC grades."""

import io
import json
import threading
import time
import uuid
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, abort, jsonify, render_template, request, send_from_directory
from PIL import Image

from src.grading import closeups, locate, measure, standards, surface
from src.grading.scanner import DEFAULT_REGION, PLATEN_REGION, PREVIEW_DPI, Scanner

ROOT = Path(__file__).parent
SCANS = ROOT / "data" / "scans"
SCANS.mkdir(parents=True, exist_ok=True)
SLOTS = ("front", "back", "front_rot", "back_rot")
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
    return {"centering": m.centering, "edges": m.edges, "corners": m.corners,
            "warnings": m.warnings, "dims_in": m.dims_in, "edges_reliable": m.edges_reliable}


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


def _process(sid, slot, raw: bytes, src_ppi):
    d = _session_dir(sid)
    (d / f"{slot}_raw.jpg").write_bytes(raw)
    img = measure.load(raw)
    m = measure.measure_image(img, src_ppi=src_ppi)
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
    d = _session_dir(sid)
    meta = _meta(d)
    name = str((request.json or {}).get("name", ""))[:120].strip()
    meta["name"] = name
    (d / "meta.json").write_text(json.dumps(meta))
    return jsonify(meta)


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
        cards.append({
            "id": d.name, "name": meta.get("name") or "", "graded_at": meta.get("graded_at"),
            "thumb": thumb,
            "grades": {k: {"grade": est[k]["grade"], "score_range": est[k].get("score_range")} for k in ("TAG", "PSA", "CGC") if k in est},
            "counts": est.get("counts"), "centering": (front.get("centering") or {}).get("worst"),
            "dims": front.get("dims_in"), "surface_checked": r.get("surface_checked", False),
        })
    return jsonify(cards)


@app.route("/api/card/<sid>", methods=["DELETE"])
def delete_card(sid):
    d = _session_dir(sid)
    trash = SCANS / ".deleted"
    trash.mkdir(exist_ok=True)
    d.rename(trash / d.name)  # recoverable: moved aside, not erased
    return jsonify({"ok": True})


@app.route("/guide")
def guide():
    return render_template("guide.html")


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
    data["overlay"] = f"/scans/{sid}/{slot}_overlay.jpg?t={int(time.time())}"
    return jsonify(data)


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
        surf[side] = res
        surface_by_side[side] = closeups.surface_findings(res["marks"], canon.shape)

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
        if rot:
            ppi = data.get("ppi", 600)
            seen = closeups.match_in_rotated(findings, rot.get("findings", []), int(2.5 * ppi), int(3.5 * ppi), 25.4 / ppi)
            for f, b in zip(findings, seen):
                f["both"] = b
                f["cleared"] = f["severity"] == "yellow" and b is False
        # Redraw this side's close-ups so boxes and tile outlines reflect cleared findings and surface marks.
        outline_file = d / f"{side}_outline.npy"
        rendered = closeups.render(cv2.imread(str(d / f"{side}_view.jpg")), data.get("view_pad", 0),
                                   findings + surface_by_side.get(side, []), d, side, data.get("ppi", 600),
                                   np.load(outline_file) if outline_file.exists() else None)
        data["closeups"] = _closeup_urls(sid, rendered)
    surface_found = [f for found in surface_by_side.values() for f in found]
    est = standards.estimate_all(front, back, surface_found)
    out = {"front": front, "back": back, "surface": surf, "estimates": est,
           "surface_checked": bool(surf), "meta": _meta(d)}
    if not (d / "meta.json").exists():
        (d / "meta.json").write_text(json.dumps(out["meta"]))
    (d / "report.json").write_text(json.dumps(out))  # snapshot for the library
    return jsonify(out)


@app.route("/scans/<sid>/<path:name>")
def scan_file(sid, name):
    return send_from_directory(_session_dir(sid), name)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5055, debug=False, threaded=True)
