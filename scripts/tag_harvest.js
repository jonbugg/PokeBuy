// Harvest TAG DIG reports, run inside a my.taggrading.com page (same-origin iframes), in the background.
//
// 1. Open https://my.taggrading.com/card/Q4488780 in a browser tab (any TAG page works).
// 2. Paste this whole file into the page (a javascript tool call), then call:
//      startHarvest({key: {year, setPath, setName, match, number?, variation?, grades?}, ...})
//    e.g. startHarvest({"151-199": {year: 2023, setPath: "Pokémon Scarlet & Violet", setName: "151",
//                                    match: "Charizard ex", number: "199/165"}})
//    setPath/setName come from https://my.taggrading.com/pop-report/Pokémon/<year> (set links read
//    "/pop-report/Pokémon/<year>/<setPath>?setName=<setName>").
// 3. Check progress with harvestStatus(). Save results with harvestDump() (JSON for scripts/tag_ingest.py).
//
// It is deliberately slow (one page every GAP ms). TAG starts answering "NOTHING WAS FOUND" after ~20
// quick pages; after 3 of those in a row it stops itself (window._stop). Wait 20-30 minutes, then
// call resumeHarvest() to continue the queue. Never try to get around the limit.

window.GAP = window.GAP || 25000;

window.harvest = async function harvest(o) {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const load = async (url, ready, tries = 40) => {
    if (window._stop) return null;
    const f = document.createElement("iframe");
    f.style.cssText = "width:1400px;height:900px;position:fixed;left:-3000px";
    f.src = url; document.body.appendChild(f);
    let out = null, blocked = false;
    for (let i = 0; i < tries && !out && !blocked; i++) {
      await sleep(700);
      try {
        const d = f.contentDocument;
        if (d && d.body) {
          if (/NOTHING WAS FOUND/.test(d.body.innerText)) blocked = true;
          else if (ready(d)) out = d.body.innerText + "\u0000" + d.body.innerHTML;
        }
      } catch (e) {}
    }
    f.remove();
    if (blocked) { window._blocked = (window._blocked || 0) + 1; if (window._blocked >= 3) window._stop = true; }
    else if (out) window._blocked = 0;
    await sleep(window.GAP);
    return out;
  };
  const setUrl = `/pop-report/Pokémon/${o.year}/${o.setPath}?setName=${encodeURIComponent(o.setName).replace(/%20/g, "+")}`;
  const setPage = await load(setUrl, d => d.querySelectorAll("a[href*='grades=']").length > 0, 50);
  if (!setPage) return {error: window._stop ? "stopped" : "set page didn't load", setUrl};
  const doc = new DOMParser().parseFromString(setPage.split("\u0000")[1], "text/html");
  const links = [...doc.querySelectorAll("a")].map(a => a.getAttribute("href") || "").filter(h => /pop-report/.test(h) && !/grades=/.test(h));
  const norm = h => decodeURIComponent(h).toLowerCase();
  const want = links.filter(h => norm(h).includes("/" + o.match.toLowerCase()) &&
    (!o.number || norm(h).includes("/" + o.number.toLowerCase())) &&
    (!o.variation || norm(h).includes(o.variation.toLowerCase())));
  if (!want.length) return {error: "card not found on set page", setUrl,
    sample: [...new Set(links.filter(h => norm(h).includes(o.match.toLowerCase())))].slice(0, 8)};
  const cardUrl = want[0];
  const grades = o.grades || ["10P", "10", "9", "8.5", "8", "7", "6"];
  const copies = {}, pop = {};
  for (const g of grades) {
    const page = await load(cardUrl + "&grades=" + g, d => /CERT NUMBER/.test(d.body.innerText), 25);
    if (!page) continue;
    const t = page.split("\u0000")[0];
    // Only rows that show a score "(945)" have a full DIG report (centering, DINGS, photos).
    const rows = [...t.matchAll(/\n[\d ()T]+\t([\d.]+P?[^\t]*?)\s\((\d{3,4})\)\tView\t.*?\t(\d\d-\d\d-\d{4})\t([A-Z]\d{7})/g)].map(m => [m[4], m[1], +m[2]]);
    pop[g] = rows.length;
    const k = o.perGrade || 2;
    const pick = rows.length <= k ? rows : [rows[0], rows[rows.length - 1], ...rows.slice(1, -1)].slice(0, k);
    for (const [cert, , score] of pick) copies[cert] = {grade: g, score};
  }
  for (const cert of Object.keys(copies)) {
    const page = await load("/card/" + cert, d => /FRONT CORNERS/.test(d.body.innerText) && /_FRONT_MAIN/.test(d.body.innerHTML), 30);
    if (!page) { copies[cert].error = window._stop ? "stopped" : "report didn't load"; continue; }
    const [t, h] = page.split("\u0000");
    const cent = t.match(/CENTERING\nF:\n([^\n]+)\nB:\n([^\n]+)/) || [];
    const surf = (t.match(/\nID\n([\s\S]*?)CORNER DETAILS/) || ["", ""])[1].replace(/arrow_downward/g, "").replace(/\s+/g, " ").trim();
    const img = (h.match(/https:\/\/[^"']+?_FRONT_MAIN\.jpg/) || [""])[0].replace("_FRONT_MAIN.jpg", "");
    Object.assign(copies[cert], {
      centF: cent[1], centB: cent[2],
      dims: (t.match(/H:\n([\d.]+)"\nW:\n([\d.]+)"/) || []).slice(1),
      dings: (t.match(/CORNERS\nF:\n(\d+) DINGS\nB:\n(\d+) DINGS\nEDGES\nF:\n(\d+) DINGS\nB:\n(\d+) DINGS[\s\S]*?SURFACE\nF:\n(\d+) DINGS\nB:\n(\d+) DINGS/) || []).slice(1).map(Number),
      surf, img,
    });
  }
  return {card: o, url: cardUrl, pop, copies};
};

window.startHarvest = function (jobs) {
  window._h = window._h || {}; window._status = window._status || {};
  window._queue = (window._queue || []).concat(Object.entries(jobs));
  return window.resumeHarvest();
};

window.resumeHarvest = function () {
  window._stop = false; window._blocked = 0;
  if (window._running) return "already running";
  window._running = true;
  (async () => {
    while (window._queue.length && !window._stop) {
      const [k, o] = window._queue[0];
      window._status[k] = "running";
      let r;
      try { r = await harvest(Object.assign({perGrade: 2}, o)); } catch (e) { r = {error: String(e)}; }
      // keep partial results; a card cut short by a pause is retried from the start on resume
      const prev = window._h[k];
      if (r.copies) {
        const got = Object.fromEntries(Object.entries(r.copies).filter(([, v]) => v.centF));
        window._h[k] = Object.assign({}, r, {copies: Object.assign({}, prev && prev.copies, got)});
      } else if (!prev) window._h[k] = r;
      if (window._stop) { window._status[k] = "paused"; break; }
      window._status[k] = r.error ? "error: " + r.error : "done";
      window._queue.shift();
    }
    window._running = false;
  })();
  return "started";
};

window.harvestStatus = function () {
  return JSON.stringify({stopped: !!window._stop, running: !!window._running, queued: (window._queue || []).map(q => q[0]),
    status: window._status, copies: Object.fromEntries(Object.entries(window._h || {}).map(([k, r]) =>
      [k, r.error ? "ERR " + r.error + (r.sample ? " " + JSON.stringify(r.sample).slice(0, 200) : "") : Object.keys(r.copies || {}).length]))});
};

window.harvestDump = function (keys) {
  const out = {};
  for (const [k, r] of Object.entries(window._h || {})) {
    if ((!keys || keys.includes(k)) && r.copies && Object.keys(r.copies).length) out[k] = r;
  }
  return JSON.stringify(out);
};
