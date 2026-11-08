/* Scan status bar, shown on every page while a scan runs and when one finishes, with a link back to the card.
   The scan itself runs on the server, so leaving the page doesn't stop it. A page can hide the bar for the
   card it is showing (it has its own progress there) by defining window.scanbarHide(job) -> true. */
(function () {
  const SLOT = {front: "Front", back: "Back", front_rot: "Front 180°", back_rot: "Back 180°",
                front_r90: "Front 90°", front_r270: "Front 270°", back_r90: "Back 90°", back_r270: "Back 270°"};
  const KEEP_DONE = 15 * 60; // seconds a finished scan stays on the bar
  const ACTIVE = ["scanning", "receiving", "measuring"];
  const STAGE = {scanning: "Scanning", receiving: "Receiving the image", measuring: "Measuring"};
  const css = document.createElement("style");
  css.textContent = `
    #scanbar { position: fixed; left: 50%; bottom: 16px; transform: translateX(-50%); z-index: 50;
      width: min(560px, calc(100% - 32px)); background: #02093a; color: #fff; border-radius: 14px;
      box-shadow: 0 10px 30px rgba(0,0,0,.25); padding: 12px 14px; display: none;
      font: 14px/1.4 "Inter", -apple-system, BlinkMacSystemFont, sans-serif; }
    #scanbar.on { display: block; }
    #scanbar .sb-row { display: flex; align-items: center; gap: 12px; }
    #scanbar .sb-text { flex: 1; min-width: 0; }
    #scanbar .sb-text b { font-weight: 600; }
    #scanbar .sb-sub { color: rgba(255,255,255,.65); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    #scanbar a.sb-open { color: #02093a; background: #fff; border-radius: 9999px; padding: 6px 14px;
      text-decoration: none; font-weight: 600; font-size: 13px; white-space: nowrap; }
    #scanbar button.sb-x { background: none; border: 0; color: rgba(255,255,255,.6); font-size: 18px; cursor: pointer; padding: 0 2px; }
    #scanbar .sb-track { height: 4px; background: rgba(255,255,255,.18); border-radius: 4px; margin-top: 10px; overflow: hidden; }
    #scanbar .sb-track i { display: block; height: 100%; width: 0; background: #62aef0; transition: width .6s linear; }
    #scanbar.err .sb-track i { background: #f64932; }`;
  document.head.appendChild(css);
  const bar = document.createElement("div");
  bar.id = "scanbar";
  bar.setAttribute("role", "status");
  document.body.appendChild(bar);

  const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const clock = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
  const dismissedKey = "scanbarDismissed";
  const dismissed = () => { try { return localStorage.getItem(dismissedKey); } catch (e) { return null; } };
  const dismiss = job => { try { localStorage.setItem(dismissedKey, String(job.started)); } catch (e) {} };

  function render(job) {
    const active = ACTIVE.includes(job.stage);
    const recent = job.finished && job.now - job.finished < KEEP_DONE;
    const hidden = !job.stage || (!active && !recent) || (!active && dismissed() === String(job.started))
      || (window.scanbarHide && window.scanbarHide(job));
    if (hidden) { bar.classList.remove("on"); return; }
    const card = job.name || "Card " + job.sid.slice(9, 15);
    const what = `${SLOT[job.slot] || job.slot} scan`;
    const href = "/?card=" + encodeURIComponent(job.sid);
    let title, sub, pct;
    if (active) {
      pct = job.progress || 0;
      title = `${STAGE[job.stage]}: ${esc(what)}`;
      sub = `about ${clock(job.eta || 0)} left · ${esc(card)}`;
    } else if (job.stage === "done") {
      pct = 100;
      title = `${esc(what)} is ready`;
      sub = esc(card);
    } else {
      pct = 100;
      title = `${esc(what)} didn't finish`;
      sub = esc(job.error || "Something went wrong.");
    }
    bar.classList.toggle("err", job.stage === "error");
    bar.innerHTML = `<div class="sb-row"><div class="sb-text"><b>${title}</b><div class="sb-sub">${sub}</div></div>
      <a class="sb-open" href="${href}">Open card</a>${active ? "" : `<button class="sb-x" aria-label="Hide">×</button>`}</div>
      ${active ? `<div class="sb-track"><i style="width:${pct}%"></i></div>` : ""}`;
    bar.classList.add("on");
    bar.querySelector(".sb-open").onclick = () => dismiss(job);
    const x = bar.querySelector(".sb-x");
    if (x) x.onclick = () => { dismiss(job); bar.classList.remove("on"); };
  }

  async function poll() {
    let job = {};
    try { job = await (await fetch("/api/scan-job", {cache: "no-store"})).json(); } catch (e) {}
    render(job);
    setTimeout(poll, ACTIVE.includes(job.stage) ? 1000 : 4000);
  }
  window.scanbarRefresh = () => fetch("/api/scan-job", {cache: "no-store"}).then(r => r.json()).then(render).catch(() => {});
  poll();
})();
