/* ContestLogger Frontend – reines Vanilla-JS, keine Abhängigkeiten (offline-fähig). */
(() => {
  "use strict";

  // ------------------------------------------------------------ Zustand
  const S = {
    nick: localStorage.getItem("cl.nick") || "",
    adminToken: localStorage.getItem("cl.admin") || "",
    stationTokens: JSON.parse(localStorage.getItem("cl.stationTokens") || "{}"),
    contests: [],
    contestId: Number(localStorage.getItem("cl.contest")) || null,
    stationId: Number(localStorage.getItem("cl.station")) || null,
    qsos: [],
    ws: null,
    suggestions: [],
    suggestSel: -1,
    editingId: null,
    info: {},
  };
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));
  const el = (tag, attrs = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") n.className = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else if (v !== null && v !== undefined) n.setAttribute(k, v);
    }
    for (const k of kids.flat()) if (k !== null && k !== undefined) n.append(k.nodeType ? k : document.createTextNode(String(k)));
    return n;
  };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const save = () => {
    localStorage.setItem("cl.nick", S.nick);
    localStorage.setItem("cl.admin", S.adminToken);
    localStorage.setItem("cl.stationTokens", JSON.stringify(S.stationTokens));
    if (S.contestId) localStorage.setItem("cl.contest", S.contestId);
    if (S.stationId) localStorage.setItem("cl.station", S.stationId);
  };

  // ------------------------------------------------------------ API
  async function api(method, url, body, opts = {}) {
    const headers = { "X-Nick": S.nick };
    if (S.adminToken) headers["X-Admin-Token"] = S.adminToken;
    const sid = opts.stationId ?? S.stationId;
    if (sid && S.stationTokens[sid]) headers["X-Station-Token"] = S.stationTokens[sid];
    let payload = body;
    if (body && !(body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
    const r = await fetch(url, { method, headers, body: payload });
    if (!r.ok) {
      let msg = r.statusText;
      try { msg = (await r.json()).detail || msg; } catch (_) { /* ignore */ }
      throw new Error(msg);
    }
    return r.json();
  }
  const GET = (u) => api("GET", u);

  // ------------------------------------------------------------ UI-Helfer
  let toastTimer;
  function toast(msg, kind = "") {
    const t = $("#toast");
    t.textContent = msg; t.className = `toast ${kind}`;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.add("hidden"), 3500);
  }
  function modal(content, { closable = true } = {}) {
    const m = $("#modal"), box = $("#modal-box");
    box.innerHTML = "";
    box.append(content);
    m.classList.remove("hidden");
    box.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", closeModal));
    m.onclick = (e) => { if (e.target === m && closable) closeModal(); };
    const f = box.querySelector("[autofocus], input");
    if (f) setTimeout(() => f.focus(), 30);
    return box;
  }
  function closeModal() { $("#modal").classList.add("hidden"); $("#modal-box").innerHTML = ""; }
  const fromTpl = (id) => document.getElementById(id).content.cloneNode(true);
  const fmtTime = (ts) => ts ? ts.slice(11, 16) : "";
  const fmtDate = (ts) => ts ? `${ts.slice(8, 10)}.${ts.slice(5, 7)}.${ts.slice(0, 4)}` : "";
  const pad3 = (n) => String(n ?? "").padStart(3, "0");
  const station = () => S.contests.flatMap((c) => c.stations).find((s) => s.id === S.stationId);
  const contest = () => S.contests.find((c) => c.id === S.contestId);
  const canLog = () => !!(S.stationId && (S.stationTokens[S.stationId] || S.adminToken));

  // ------------------------------------------------------------ Uhr
  function tickClock() {
    const d = new Date();
    $("#utc-time").textContent = d.toISOString().slice(11, 19);
    $("#utc-date").textContent = d.toISOString().slice(0, 10);
  }
  setInterval(tickClock, 500); tickClock();

  // ------------------------------------------------------------ Tabs
  $$(".tabs button").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
  function showView(v) {
    $$(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
    $$(".view").forEach((s) => s.classList.toggle("active", s.id === `view-${v}`));
    if (v === "stats") renderStats();
    if (v === "fulllog") renderFullLog();
    if (v === "admin") renderAdmin();
    if (v === "log") setTimeout(() => $("#f-call").focus(), 20);
  }

  // ------------------------------------------------------------ Start
  async function boot() {
    S.info = await GET("/api/info");
    $("#version").textContent = "v" + S.info.version;
    $("#copyright").textContent = S.info.copyright;
    $("#footer-text").textContent = `${S.info.app} ${S.info.version} · ${S.info.copyright} · lokal, offline, im LAN`;
    if (!S.info.admin_configured) await askSetup();
    if (!S.nick) await askNick();
    $("#nick-badge").textContent = S.nick;
    await loadContests();
    connectWs();
    loadChat();
    $("#f-call").focus();
  }

  function askSetup() {
    return new Promise((resolve) => {
      const box = modal(fromTpl("tpl-setup"), { closable: false });
      box.querySelector("#setup-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
          const r = await api("POST", "/api/setup", { password: box.querySelector("#setup-pw").value });
          S.adminToken = r.token; save(); closeModal(); toast("Admin-Passwort gesetzt – du bist als Admin angemeldet.", "ok"); resolve();
        } catch (err) { toast(err.message, "err"); }
      });
    });
  }
  function askNick() {
    return new Promise((resolve) => {
      const box = modal(fromTpl("tpl-nick"), { closable: !!S.nick });
      box.querySelector("#nick-input").value = S.nick;
      box.querySelector("#nick-form").addEventListener("submit", (e) => {
        e.preventDefault();
        S.nick = box.querySelector("#nick-input").value.trim().slice(0, 24);
        if (!S.nick) return;
        save(); closeModal(); $("#nick-badge").textContent = S.nick;
        if (S.ws) { try { S.ws.close(); } catch (_) { /* */ } }
        resolve();
      });
    });
  }
  $("#nick-badge").addEventListener("click", askNick);

  // ------------------------------------------------------------ Theme
  const applyTheme = () => { const t = localStorage.getItem("cl.theme"); if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme; };
  applyTheme();
  $("#theme-btn").addEventListener("click", () => {
    const dark = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim() === "#0f1419";
    localStorage.setItem("cl.theme", dark ? "light" : "dark"); applyTheme();
  });

  // ------------------------------------------------------------ Contests / Stationen
  async function loadContests() {
    S.contests = await GET("/api/contests");
    if (!S.contests.find((c) => c.id === S.contestId)) {
      const active = S.contests.find((c) => !c.archived) || S.contests[0];
      S.contestId = active ? active.id : null;
    }
    const c = contest();
    if (c && !c.stations.find((s) => s.id === S.stationId)) S.stationId = c.stations[0]?.id || null;
    save();
    renderStationBar();
    await loadQsos();
    renderScoreboard();
    sendStatus();
    if ($("#view-admin").classList.contains("active")) renderAdmin();
  }

  function renderStationBar() {
    const sc = $("#sel-contest"), ss = $("#sel-station");
    sc.innerHTML = "";
    for (const c of S.contests) sc.append(el("option", { value: c.id }, c.name + (c.archived ? " (Archiv)" : "")));
    if (!S.contests.length) sc.append(el("option", { value: "" }, "– kein Contest – (Verwaltung)"));
    sc.value = S.contestId ?? "";
    ss.innerHTML = "";
    const c = contest();
    for (const s of c?.stations || []) ss.append(el("option", { value: s.id }, `${s.call} · ${s.band}`));
    if (!c?.stations?.length) ss.append(el("option", { value: "" }, "– keine Station –"));
    ss.value = S.stationId ?? "";
    const st = station();
    if (st) {
      $("#station-meta").textContent = `${st.locator} · ${st.mode} · nächste Nr. ${pad3(st.serial_next)}`;
      $("#f-nr-sent").value = pad3(st.serial_next);
      const unlocked = canLog();
      $("#station-state").innerHTML = unlocked
        ? `<span class="tag me">freigeschaltet</span>`
        : `<button class="ghost small" id="btn-unlock">🔒 freischalten</button>`;
      $("#btn-unlock")?.addEventListener("click", () => askUnlock(st));
      $("#qso-form").querySelectorAll("input,button").forEach((i) => { if (i.id !== "f-nr-sent") i.disabled = !unlocked; });
      $("#hint-info").textContent = unlocked ? "Rufzeichen eingeben – Vorschläge aus Call-Buch und alten Logs erscheinen automatisch." : "Station ist nur im Lesemodus. Zum Loggen mit Stations-Passwort freischalten.";
    } else {
      $("#station-meta").textContent = "";
      $("#station-state").textContent = S.contests.length ? "" : "Lege unter „Verwaltung“ einen Contest und eine Station an.";
      $("#qso-form").querySelectorAll("input,button").forEach((i) => { i.disabled = true; });
    }
    for (const f of ["edi", "adi", "csv"]) $(`#exp-${f}`).href = st ? `/api/stations/${st.id}/export.${f}` : "#";
  }
  $("#sel-contest").addEventListener("change", async (e) => {
    S.contestId = Number(e.target.value) || null;
    S.stationId = contest()?.stations[0]?.id || null;
    save(); renderStationBar(); await loadQsos(); renderScoreboard(); sendStatus();
  });
  $("#sel-station").addEventListener("change", async (e) => {
    S.stationId = Number(e.target.value) || null;
    save(); renderStationBar(); await loadQsos(); renderScoreboard(); sendStatus();
    if (S.stationId && !canLog()) askUnlock(station());
  });

  function askUnlock(st) {
    if (!st) return;
    const box = modal(fromTpl("tpl-unlock"));
    box.querySelector(".st-name").textContent = `${st.call} (${st.band})`;
    box.querySelector("#unlock-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const r = await api("POST", `/api/stations/${st.id}/unlock`, { password: box.querySelector("#unlock-pw").value });
        S.stationTokens[st.id] = r.token; save(); closeModal(); renderStationBar(); renderQsos(); toast(`${st.call} freigeschaltet`, "ok"); $("#f-call").focus();
      } catch (err) { toast(err.message, "err"); }
    });
  }

  // ------------------------------------------------------------ QSOs
  async function loadQsos() {
    if (!S.stationId) { S.qsos = []; renderQsos(); renderKpis(null); return; }
    S.qsos = await GET(`/api/stations/${S.stationId}/qsos`);
    renderQsos();
    renderKpis();
    if ($("#view-fulllog").classList.contains("active")) renderFullLog();
    if ($("#view-stats").classList.contains("active")) renderStats();
  }

  function qsoRow(q, full) {
    const tr = el("tr", { class: q.dupe ? "dupe" : "" });
    const cells = full
      ? [q.serial_sent, fmtDate(q.ts_utc), fmtTime(q.ts_utc), q.call, q.rst_sent, pad3(q.serial_sent), q.rst_rcvd, q.serial_rcvd, q.locator, q.km, q.bearing, q.points, q.country, q.mode, q.comment, q.logged_by]
      : [fmtTime(q.ts_utc), q.call, `${q.rst_sent} ${pad3(q.serial_sent)}`, `${q.rst_rcvd} ${q.serial_rcvd}`, q.locator, q.km, q.bearing, q.points, q.country, q.logged_by];
    cells.forEach((c, i) => tr.append(el("td", { class: typeof c === "number" ? "num" : "" }, c)));
    if (q.dupe) tr.title = "Doppel-QSO (0 Punkte)";
    const act = el("td", { class: "actions" });
    if (canLog()) {
      act.append(el("button", { class: "ghost", title: "Bearbeiten", onclick: () => editQso(q) }, "✎"), " ",
        el("button", { class: "ghost danger", title: "Löschen", onclick: () => deleteQso(q) }, "✕"));
    }
    tr.append(act);
    return tr;
  }
  function renderQsos() {
    const tb = $("#qso-table tbody"); tb.innerHTML = "";
    const f = $("#log-search").value.trim().toUpperCase();
    const list = S.qsos.filter((q) => !f || q.call.includes(f) || q.locator.includes(f) || (q.comment || "").toUpperCase().includes(f));
    list.slice(0, 60).forEach((q) => tb.append(qsoRow(q, false)));
    $("#qso-count").textContent = S.qsos.length;
  }
  $("#log-search").addEventListener("input", renderQsos);
  function renderFullLog() {
    const tb = $("#full-table tbody"); tb.innerHTML = "";
    const f = $("#full-search").value.trim().toUpperCase();
    const list = S.qsos.filter((q) => !f || q.call.includes(f) || q.locator.includes(f) || (q.comment || "").toUpperCase().includes(f));
    list.forEach((q) => tb.append(qsoRow(q, true)));
    $("#full-count").textContent = `${list.length} / ${S.qsos.length}`;
  }
  $("#full-search").addEventListener("input", renderFullLog);

  function renderKpis(summary) {
    const box = $("#kpis");
    const valid = S.qsos.filter((q) => !q.dupe);
    const pts = valid.reduce((a, q) => a + q.points, 0);
    const squares = new Set(valid.map((q) => q.square).filter(Boolean)).size;
    const odx = valid.reduce((a, q) => (q.km > (a?.km || 0) ? q : a), null);
    const hourAgo = Date.now() - 3600e3;
    const rate = S.qsos.filter((q) => Date.parse(q.ts_utc) > hourAgo).length;
    box.innerHTML = "";
    if (!S.stationId) return;
    const k = (v, l, cls = "") => el("div", { class: `kpi ${cls}` }, el("b", {}, v), el("span", {}, l));
    box.append(k(valid.length, "QSOs"), k(pts.toLocaleString("de"), "Punkte"), k(squares, "Großfelder"),
      k(valid.length ? Math.round(pts / valid.length) : 0, "Ø km"), k(rate, "QSOs / letzte h"), k(S.qsos.length - valid.length, "Dupes"),
      k(odx ? `${odx.call} ${odx.km} km` : "–", "ODX", "wide"));
  }

  // ---- Eingabeformular
  const F = { call: $("#f-call"), rs: $("#f-rst-sent"), ns: $("#f-nr-sent"), rr: $("#f-rst-rcvd"), nr: $("#f-nr-rcvd"), loc: $("#f-loc"), cmt: $("#f-comment") };
  const order = [F.call, F.rs, F.rr, F.nr, F.loc, F.cmt];

  function clearForm() {
    F.call.value = ""; F.rs.value = "59"; F.rr.value = "59"; F.nr.value = ""; F.loc.value = ""; F.cmt.value = "";
    S.editingId = null; $("#qso-form button.primary").textContent = "Loggen ⏎";
    hideSuggest(); updateHints(); F.call.focus();
  }
  $("#btn-clear").addEventListener("click", clearForm);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { if (!$("#modal").classList.contains("hidden")) closeModal(); else if ($("#view-log").classList.contains("active")) clearForm(); }
  });

  // Enter springt weiter; wenn Call + Locator vorhanden und man im letzten Pflichtfeld ist, wird geloggt.
  order.forEach((inp, i) => {
    inp.addEventListener("keydown", (e) => {
      if (inp === F.call && !$("#suggest").classList.contains("hidden")) {
        if (e.key === "ArrowDown") { e.preventDefault(); moveSuggest(1); return; }
        if (e.key === "ArrowUp") { e.preventDefault(); moveSuggest(-1); return; }
        if ((e.key === "Enter" || e.key === "Tab") && S.suggestSel >= 0) { e.preventDefault(); applySuggest(S.suggestions[S.suggestSel]); return; }
      }
      if (e.key === "Enter") {
        e.preventDefault();
        const ready = F.call.value.trim().length >= 3 && F.loc.value.trim().length >= 4;
        if (ready && (inp === F.loc || inp === F.cmt || inp === F.nr)) submitQso();
        else if (inp === F.call && ready) F.nr.focus();
        else (order[i + 1] || F.call).focus();
      }
      if (e.key === " " && inp === F.call) { e.preventDefault(); (F.loc.value ? F.nr : F.loc).focus(); }
    });
  });
  F.call.addEventListener("input", () => { F.call.value = F.call.value.toUpperCase(); fetchSuggest(); updateHints(); });
  F.loc.addEventListener("input", () => { F.loc.value = F.loc.value.toUpperCase(); updateHints(); });
  F.call.addEventListener("blur", () => setTimeout(hideSuggest, 150));
  F.nr.addEventListener("blur", () => { if (/^\d+$/.test(F.nr.value)) F.nr.value = pad3(Number(F.nr.value)); });

  let suggestTimer;
  function fetchSuggest() {
    clearTimeout(suggestTimer);
    const q = F.call.value.trim();
    if (q.length < 2) return hideSuggest();
    suggestTimer = setTimeout(async () => {
      try {
        S.suggestions = await GET(`/api/suggest?q=${encodeURIComponent(q)}&station=${S.stationId || ""}`);
        renderSuggest();
      } catch (_) { /* offline */ }
    }, 120);
  }
  function renderSuggest() {
    const box = $("#suggest"); box.innerHTML = ""; S.suggestSel = -1;
    const exact = S.suggestions.find((s) => s.call === F.call.value.trim());
    if (exact && !F.loc.value) { F.loc.value = exact.locator; updateHints(); }
    if (!S.suggestions.length) return hideSuggest();
    S.suggestions.slice(0, 10).forEach((s, i) => {
      const meta = [];
      if (s.km) meta.push(`${s.km} km · ${s.bearing}°`);
      if (s.qso_count) meta.push(`${s.qso_count}× gearbeitet`);
      if (s.last_seen) meta.push(`zuletzt ${fmtDate(s.last_seen)}`);
      const d = el("div", { class: s.worked_here ? "worked" : "", onmousedown: (e) => { e.preventDefault(); applySuggest(s); } },
        el("span", { class: "s-call" }, s.call), el("span", { class: "s-loc" }, s.locator || "?"),
        s.name ? el("span", {}, s.name) : null,
        s.worked_here ? el("span", { class: "tag" }, "DUPE") : null,
        el("span", { class: "s-meta" }, meta.join(" · ")));
      d.dataset.i = i; box.append(d);
    });
    box.classList.remove("hidden");
  }
  function hideSuggest() { $("#suggest").classList.add("hidden"); S.suggestSel = -1; }
  function moveSuggest(d) {
    const items = $$("#suggest div"); if (!items.length) return;
    S.suggestSel = (S.suggestSel + d + items.length) % items.length;
    items.forEach((it, i) => it.classList.toggle("sel", i === S.suggestSel));
  }
  function applySuggest(s) {
    if (!s) return;
    F.call.value = s.call; if (s.locator) F.loc.value = s.locator;
    hideSuggest(); updateHints(); F.nr.focus();
  }

  let hintTimer;
  function updateHints() {
    const st = station(); const call = F.call.value.trim(); const loc = F.loc.value.trim();
    const dupeBox = $("#hint-dupe");
    const core = call.split("/").sort((a, b) => b.length - a.length)[0] || "";
    const prev = S.qsos.filter((q) => q.core_call === core && q.id !== S.editingId);
    if (call.length >= 3 && prev.length) {
      dupeBox.textContent = `⚠ ${call} bereits gearbeitet um ${fmtTime(prev[prev.length - 1].ts_utc)} UTC (${prev[prev.length - 1].locator}) – DUPE!`;
      dupeBox.classList.remove("hidden");
    } else dupeBox.classList.add("hidden");
    clearTimeout(hintTimer);
    if (st && /^[A-R]{2}\d{2}([A-X]{2})?$/.test(loc)) {
      hintTimer = setTimeout(async () => {
        try {
          const r = await GET(`/api/calc?my=${st.locator}&loc=${loc}`);
          $("#hint-geo").textContent = r.valid ? `${r.km} km · ${r.bearing}°` : "— km · —°";
        } catch (_) { /* */ }
      }, 80);
    } else $("#hint-geo").textContent = "— km · —°";
  }

  $("#qso-form").addEventListener("submit", (e) => { e.preventDefault(); submitQso(); });
  async function submitQso() {
    if (!canLog()) return toast("Station ist nicht freigeschaltet", "err");
    const body = { call: F.call.value.trim(), locator: F.loc.value.trim(), rst_sent: F.rs.value.trim() || "59", rst_rcvd: F.rr.value.trim() || "59", serial_rcvd: F.nr.value.trim(), comment: F.cmt.value.trim() };
    if (body.call.length < 3) return F.call.focus();
    try {
      if (S.editingId) {
        await api("PATCH", `/api/qsos/${S.editingId}`, body);
        toast("QSO geändert", "ok");
      } else {
        const q = await api("POST", `/api/stations/${S.stationId}/qsos`, body);
        toast(q.dupe ? `DUPE geloggt: ${q.call} (0 Punkte)` : `${q.call} ${q.locator} · ${q.km} km · ${q.points} Punkte`, q.dupe ? "err" : "ok");
      }
      clearForm();
    } catch (err) { toast(err.message, "err"); }
  }

  function editQso(q) {
    const box = modal(el("div", {},
      el("h3", {}, `QSO #${q.serial_sent} bearbeiten – ${q.call}`),
      el("form", { id: "edit-form", class: "stack" },
        el("div", { class: "grid2" },
          lab("Datum/Zeit UTC", el("input", { id: "e-ts", value: q.ts_utc.slice(0, 16).replace("T", " ") })),
          lab("Rufzeichen", el("input", { id: "e-call", value: q.call })),
          lab("Locator", el("input", { id: "e-loc", value: q.locator })),
          lab("Nr gegeben", el("input", { id: "e-ns", value: q.serial_sent, type: "number", min: 1 })),
          lab("RST gegeben", el("input", { id: "e-rs", value: q.rst_sent })),
          lab("RST erhalten", el("input", { id: "e-rr", value: q.rst_rcvd })),
          lab("Nr erhalten", el("input", { id: "e-nr", value: q.serial_rcvd })),
          lab("Modus", el("input", { id: "e-mode", value: q.mode })),
          lab("Kommentar", el("input", { id: "e-cmt", value: q.comment }))),
        el("div", { class: "row" }, el("button", { class: "primary" }, "Speichern"), el("button", { type: "button", class: "ghost", "data-close": 1 }, "Abbrechen"),
          el("span", { class: "grow" }), el("button", { type: "button", class: "ghost danger", onclick: () => { closeModal(); deleteQso(q); } }, "Löschen")))));
    box.querySelector("#edit-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const g = (id) => box.querySelector(id).value.trim();
      const ts = g("#e-ts").replace(" ", "T");
      if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(ts)) return toast("Zeitformat: JJJJ-MM-TT HH:MM", "err");
      try {
        await api("PATCH", `/api/qsos/${q.id}`, { ts_utc: ts.slice(0, 16) + ":00Z", call: g("#e-call"), locator: g("#e-loc"), serial_sent: Number(g("#e-ns")), rst_sent: g("#e-rs"), rst_rcvd: g("#e-rr"), serial_rcvd: g("#e-nr"), mode: g("#e-mode"), comment: g("#e-cmt") }, { stationId: q.station_id });
        closeModal(); toast("QSO gespeichert", "ok");
      } catch (err) { toast(err.message, "err"); }
    });
  }
  const lab = (text, input) => el("label", {}, text, input);
  async function deleteQso(q) {
    if (!confirm(`QSO #${q.serial_sent} mit ${q.call} wirklich löschen?`)) return;
    try { await api("DELETE", `/api/qsos/${q.id}`, null, { stationId: q.station_id }); toast("QSO gelöscht"); } catch (err) { toast(err.message, "err"); }
  }
  $("#btn-serial").addEventListener("click", async () => {
    const st = station(); if (!st || !canLog()) return toast("Station nicht freigeschaltet", "err");
    const v = prompt(`Nächste zu vergebende Seriennummer für ${st.call}:`, st.serial_next);
    if (v === null || !/^\d+$/.test(v)) return;
    try { await api("POST", `/api/stations/${st.id}/serial`, { start: Number(v) }); toast(`Nächste Nr.: ${pad3(v)}`, "ok"); } catch (err) { toast(err.message, "err"); }
  });

  // ------------------------------------------------------------ Scoreboard
  async function renderScoreboard() {
    const tb = $("#scoreboard tbody"); tb.innerHTML = "";
    if (!S.contestId) return;
    let rows = [];
    try { rows = await GET(`/api/contests/${S.contestId}/scoreboard`); } catch (_) { return; }
    tb.append(el("tr", {}, el("th", {}, "Station"), el("th", {}, "Band"), el("th", { class: "num" }, "QSOs"), el("th", { class: "num" }, "Pkt"), el("th", { class: "num" }, "Felder"), el("th", { class: "num" }, "ODX"), el("th", { class: "num" }, "/h")));
    for (const r of rows) {
      const tr = el("tr", { style: "cursor:pointer", onclick: () => { $("#sel-station").value = r.id; $("#sel-station").dispatchEvent(new Event("change")); } },
        el("td", {}, r.id === S.stationId ? el("b", {}, r.call) : r.call), el("td", {}, r.band),
        el("td", { class: "num" }, r.qsos - r.dupes), el("td", { class: "num" }, (r.points || 0).toLocaleString("de")), el("td", { class: "num" }, r.squares),
        el("td", { class: "num" }, r.odx_km || "–"), el("td", { class: "num" }, r.rate_last_hour));
      tb.append(tr);
    }
  }

  // ------------------------------------------------------------ WebSocket / Chat
  function connectWs() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws?nick=${encodeURIComponent(S.nick)}`);
    S.ws = ws;
    ws.onopen = () => { $("#conn").classList.add("on"); sendStatus(); };
    ws.onclose = () => { $("#conn").classList.remove("on"); setTimeout(connectWs, 2000); };
    ws.onmessage = async (ev) => {
      const m = JSON.parse(ev.data);
      if (m.type === "chat") appendChat(m.msg);
      else if (m.type === "presence") renderPresence(m.users);
      else if (m.type === "update") {
        if (m.scope === "contests") await loadContests();
        else if (m.scope === "qsos") {
          if (m.station_id === S.stationId) { await loadQsos(); if (m.qso && m.by !== S.nick) toast(`${m.by || "?"}: ${m.qso.call} geloggt`); }
          renderScoreboard();
          const st = S.contests.flatMap((c) => c.stations).find((s) => s.id === m.station_id);
          if (st && m.qso) { st.serial_next = Math.max(st.serial_next, m.qso.serial_sent + 1); if (st.id === S.stationId) renderStationBar(); }
        }
      }
    };
  }
  function sendStatus() { if (S.ws?.readyState === 1) S.ws.send(JSON.stringify({ type: "status", station_id: S.stationId })); }
  function renderPresence(users) {
    const names = users.map((u) => { const st = S.contests.flatMap((c) => c.stations).find((s) => s.id === u.station_id); return st ? `${u.nick}@${st.call}` : u.nick; });
    $("#online").textContent = `· online: ${names.join(", ")}`;
  }
  async function loadChat() {
    const log = $("#chat-log"); log.innerHTML = "";
    try { (await GET("/api/chat")).forEach(appendChat); } catch (_) { /* */ }
  }
  function appendChat(m) {
    const log = $("#chat-log");
    log.append(el("div", { class: "m" }, el("span", { class: "t" }, fmtTime(m.ts_utc)), el("span", { class: "n" }, m.nick + ": "), m.text));
    log.scrollTop = log.scrollHeight;
  }
  $("#chat-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const t = $("#chat-input").value.trim();
    if (t && S.ws?.readyState === 1) { S.ws.send(JSON.stringify({ type: "chat", text: t })); $("#chat-input").value = ""; }
  });

  // ------------------------------------------------------------ Statistik
  async function renderStats() {
    const root = $("#stats-root"); root.innerHTML = "";
    if (!S.stationId) { root.append(el("p", { class: "muted" }, "Keine Station ausgewählt.")); return; }
    let st; try { st = await GET(`/api/stations/${S.stationId}/stats`); } catch (e) { return; }
    const s = st.summary; const own = station();
    root.append(el("div", { class: "card kpis stat-card" },
      kpi(s.qsos - s.dupes, "gültige QSOs"), kpi((s.points || 0).toLocaleString("de"), "Punkte"), kpi(s.squares, "Großfelder"),
      kpi(s.countries, "Länder"), kpi(s.avg_km, "Ø km / QSO"), kpi(s.dupes, "Dupes"),
      kpi(s.odx ? `${s.odx.call} · ${s.odx.km} km` : "–", `ODX (${s.odx?.locator || ""})`, "wide")));
    root.append(card("QSOs und Punkte pro Stunde", barChart(st.per_hour.map((h) => ({ label: h.hour.slice(11) + "h", a: h.qsos, b: h.points })), "QSOs", "Punkte")));
    root.append(card("Entfernungsverteilung (km)", barChart(st.distance.map((d) => ({ label: d.range, a: d.qsos, b: d.points })), "QSOs", "Punkte")));
    root.append(card(`Richtungsverteilung von ${own?.locator || ""}`, rose(st.bearings)));
    root.append(card("Top 10 Entfernungen", table(["Call", "Locator", "km", "Pkt", "UTC"], st.top.map((q) => [q.call, q.locator, q.km, q.points, fmtTime(q.ts_utc)]))));
    root.append(card(`Großfelder (${st.squares.length})`, table(["Feld", "QSOs", "Punkte"], st.squares.map((q) => [q.square, q.qsos, q.points]))));
    root.append(card("Länder", table(["Land", "QSOs", "Punkte", "ODX km"], st.countries.map((c) => [c.country, c.qsos, c.points, c.odx]))));
    root.append(card("Operatoren", table(["Nick", "QSOs", "Punkte"], st.operators.map((o) => [o.nick || "–", o.qsos, o.points]))));
  }
  const kpi = (v, l, cls = "") => el("div", { class: `kpi ${cls}` }, el("b", {}, v), el("span", {}, l));
  const card = (title, body) => el("div", { class: "card stat-card" }, el("h3", {}, title), body);
  function table(head, rows) {
    const t = el("table", { class: "compact" }, el("thead", {}, el("tr", {}, head.map((h) => el("th", {}, h)))));
    const tb = el("tbody"); rows.forEach((r) => tb.append(el("tr", {}, r.map((c) => el("td", { class: typeof c === "number" ? "num" : "" }, c)))));
    t.append(tb);
    return el("div", { class: "table-wrap" }, rows.length ? t : el("p", { class: "muted" }, "Noch keine Daten."));
  }
  function barChart(data, la, lb) {
    if (!data.length) return el("p", { class: "muted" }, "Noch keine Daten.");
    const W = 600, H = 220, P = 30, bw = (W - 2 * P) / data.length;
    const maxA = Math.max(1, ...data.map((d) => d.a)), maxB = Math.max(1, ...data.map((d) => d.b));
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg"); svg.setAttribute("viewBox", `0 0 ${W} ${H + 20}`);
    const add = (tag, attrs, text) => { const n = document.createElementNS(ns, tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); if (text != null) n.textContent = text; svg.append(n); return n; };
    add("line", { x1: P, y1: H, x2: W - P, y2: H, class: "axis" });
    data.forEach((d, i) => {
      const x = P + i * bw;
      const ha = (d.a / maxA) * (H - 30), hb = (d.b / maxB) * (H - 30);
      add("rect", { x: x + 2, y: H - ha, width: bw / 2 - 3, height: ha, class: "bar", rx: 2 }).append(Object.assign(document.createElementNS(ns, "title"), { textContent: `${d.label}: ${d.a} ${la}` }));
      add("rect", { x: x + bw / 2 + 1, y: H - hb, width: bw / 2 - 3, height: hb, class: "bar pts", rx: 2 }).append(Object.assign(document.createElementNS(ns, "title"), { textContent: `${d.label}: ${d.b} ${lb}` }));
      if (d.a) add("text", { x: x + bw / 4, y: H - ha - 3, class: "lbl", "text-anchor": "middle" }, d.a);
      if (data.length <= 30 || i % 2 === 0) add("text", { x: x + bw / 2, y: H + 13, class: "lbl", "text-anchor": "middle" }, d.label);
    });
    add("text", { x: P, y: 12, class: "lbl" }, `■ ${la} (blau)   ■ ${lb} (grün)`);
    return svg;
  }
  function rose(sectors) {
    const ns = "http://www.w3.org/2000/svg", R = 100, C = 120;
    const svg = document.createElementNS(ns, "svg"); svg.setAttribute("viewBox", "0 0 240 240"); svg.classList.add("rose");
    const add = (tag, attrs, text) => { const n = document.createElementNS(ns, tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); if (text != null) n.textContent = text; svg.append(n); return n; };
    [0.33, 0.66, 1].forEach((f) => add("circle", { cx: C, cy: C, r: R * f }));
    const max = Math.max(1, ...sectors.map((s) => s.points));
    sectors.forEach((s) => {
      const r = (s.points / max) * R; if (!r) return;
      const a0 = ((s.sector - 90) * Math.PI) / 180, a1 = ((s.sector + 30 - 90) * Math.PI) / 180;
      const p = add("path", { d: `M${C},${C} L${C + r * Math.cos(a0)},${C + r * Math.sin(a0)} A${r},${r} 0 0 1 ${C + r * Math.cos(a1)},${C + r * Math.sin(a1)} Z` });
      p.append(Object.assign(document.createElementNS(ns, "title"), { textContent: `${s.sector}–${s.sector + 30}°: ${s.qsos} QSOs, ${s.points} Punkte` }));
    });
    [["N", 0], ["O", 90], ["S", 180], ["W", 270]].forEach(([l, d]) => { const a = ((d - 90) * Math.PI) / 180; add("text", { x: C + (R + 12) * Math.cos(a), y: C + (R + 12) * Math.sin(a) + 4, "text-anchor": "middle" }, l); });
    return svg;
  }

  // ------------------------------------------------------------ Verwaltung
  const BANDS = ["50MHz", "70MHz", "144MHz", "432MHz", "1296MHz", "2320MHz", "3400MHz", "5760MHz", "10368MHz", "24048MHz", "47088MHz", "76032MHz"];
  const INFO_FIELDS = [["section", "Wertungsgruppe (Single/Multi …)"], ["club", "Club / DOK"], ["operators", "Operatoren (MOpe1)"], ["site_address", "Standort Adresse"], ["site_city", "Standort PLZ Ort"],
    ["resp_name", "Verantwortlicher Name"], ["resp_call", "Verantwortlicher Call"], ["resp_address", "Straße"], ["resp_zip", "PLZ"], ["resp_city", "Ort"], ["resp_country", "Land"], ["resp_phone", "Telefon"], ["resp_email", "E-Mail"],
    ["tx", "Sender"], ["rx", "Empfänger"], ["power", "Leistung (W)"], ["antenna", "Antenne"], ["antenna_height", "Antennenhöhe über Grund (m)"], ["asl", "Höhe über NN (m)"]];

  async function renderAdmin() {
    const loggedIn = !!S.adminToken;
    $("#admin-login").classList.toggle("hidden", loggedIn);
    $("#admin-root").classList.toggle("hidden", !loggedIn);
    if (!loggedIn) return;
    const tb = $("#admin-contests tbody"); tb.innerHTML = "";
    for (const c of S.contests) {
      tb.append(el("tr", {},
        el("td", {}, c.id === S.contestId ? el("b", {}, c.name) : c.name),
        el("td", { class: "muted small" }, c.start_utc ? `${fmtDate(c.start_utc)} ${fmtTime(c.start_utc)} – ${fmtDate(c.end_utc)} ${fmtTime(c.end_utc)}` : ""),
        el("td", { class: "muted small" }, `${c.stations.length} Stationen${c.archived ? " · Archiv" : ""}`),
        el("td", { class: "actions" },
          el("button", { class: "ghost", onclick: () => { S.contestId = c.id; S.stationId = c.stations[0]?.id || null; save(); renderStationBar(); loadQsos(); renderScoreboard(); renderAdmin(); } }, "wählen"), " ",
          el("button", { class: "ghost", onclick: () => contestDialog(c) }, "✎"), " ",
          el("button", { class: "ghost", onclick: async () => { await api("PATCH", `/api/contests/${c.id}`, { archived: c.archived ? 0 : 1 }); } }, c.archived ? "aktivieren" : "archivieren"), " ",
          el("button", { class: "ghost danger", onclick: async () => { if (confirm(`Contest „${c.name}“ mit allen Stationen und QSOs löschen?`)) await api("DELETE", `/api/contests/${c.id}`); } }, "✕"))));
    }
    const c = contest();
    $("#admin-contest-name").textContent = c ? `– ${c.name}` : "";
    const sb = $("#admin-stations tbody"); sb.innerHTML = "";
    for (const s of c?.stations || []) {
      sb.append(el("tr", {},
        el("td", {}, el("b", {}, s.call)), el("td", {}, s.locator), el("td", {}, s.band), el("td", {}, s.mode),
        el("td", { class: "muted small" }, `Nr. ${pad3(s.serial_next)} · ${s.has_password ? "🔒" : "offen"}`),
        el("td", { class: "actions" },
          el("button", { class: "ghost", onclick: () => stationDialog(s) }, "✎"), " ",
          el("button", { class: "ghost", onclick: async () => { const v = prompt("Nächste Seriennummer:", s.serial_next); if (v && /^\d+$/.test(v)) await api("POST", `/api/stations/${s.id}/serial`, { start: Number(v) }); } }, "Nr."), " ",
          el("button", { class: "ghost danger", onclick: async () => { if (confirm(`Station ${s.call} mit allen QSOs löschen?`)) await api("DELETE", `/api/stations/${s.id}`); } }, "✕"))));
    }
    const is = $("#imp-station"); is.innerHTML = "";
    S.contests.forEach((cc) => cc.stations.forEach((s) => is.append(el("option", { value: s.id }, `${cc.name} · ${s.call} ${s.band}`))));
    $("#cb-count").textContent = (await GET("/api/info")).callbook_count;
  }
  $("#admin-login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try { S.adminToken = (await api("POST", "/api/admin/login", { password: $("#admin-pw").value })).token; save(); $("#admin-pw").value = ""; renderAdmin(); renderStationBar(); renderQsos(); toast("Als Admin angemeldet", "ok"); } catch (err) { toast(err.message, "err"); }
  });
  $("#btn-admin-logout").addEventListener("click", () => { S.adminToken = ""; save(); renderAdmin(); renderStationBar(); renderQsos(); });
  $("#admin-pw-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try { await api("POST", "/api/admin/password", { password: $("#admin-pw-new").value }); S.adminToken = (await api("POST", "/api/admin/login", { password: $("#admin-pw-new").value })).token; save(); $("#admin-pw-new").value = ""; toast("Admin-Passwort geändert", "ok"); } catch (err) { toast(err.message, "err"); }
  });
  $("#btn-new-contest").addEventListener("click", () => contestDialog(null));
  $("#btn-new-station").addEventListener("click", () => { if (!contest()) return toast("Erst einen Contest anlegen/wählen", "err"); stationDialog(null); });

  const toLocal = (ts) => (ts ? ts.slice(0, 16) : "");
  const fromLocal = (v) => (v ? v + ":00Z" : null);
  function contestDialog(c) {
    const box = modal(el("div", {}, el("h3", {}, c ? "Contest bearbeiten" : "Neuer Contest"),
      el("form", { id: "c-form", class: "stack" },
        lab("Name", el("input", { id: "c-name", value: c?.name || "", required: 1, placeholder: "z. B. DARC UKW-Contest Mai 2026" })),
        el("div", { class: "grid2" },
          lab("Beginn (UTC)", el("input", { id: "c-start", type: "datetime-local", value: toLocal(c?.start_utc) })),
          lab("Ende (UTC)", el("input", { id: "c-end", type: "datetime-local", value: toLocal(c?.end_utc) }))),
        lab("Notizen", el("input", { id: "c-notes", value: c?.notes || "" })),
        el("div", { class: "row" }, el("button", { class: "primary" }, "Speichern"), el("button", { type: "button", class: "ghost", "data-close": 1 }, "Abbrechen")))));
    box.querySelector("#c-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = { name: box.querySelector("#c-name").value, start_utc: fromLocal(box.querySelector("#c-start").value), end_utc: fromLocal(box.querySelector("#c-end").value), notes: box.querySelector("#c-notes").value };
      try {
        const r = c ? await api("PATCH", `/api/contests/${c.id}`, body) : await api("POST", "/api/contests", body);
        if (!c) { S.contestId = r.id; save(); }
        closeModal(); toast("Contest gespeichert", "ok");
      } catch (err) { toast(err.message, "err"); }
    });
  }
  function stationDialog(s) {
    const info = s?.info || {};
    const prevInfo = !s ? (contest()?.stations[0]?.info || {}) : {};
    const box = modal(el("div", {}, el("h3", {}, s ? `Station ${s.call} bearbeiten` : "Neue Station"),
      el("form", { id: "s-form", class: "stack" },
        el("div", { class: "grid2" },
          lab("Rufzeichen", el("input", { id: "s-call", value: s?.call || "", required: 1, placeholder: "DN2LH/P" })),
          lab("Locator", el("input", { id: "s-loc", value: s?.locator || prevInfo.__loc || "", required: 1, placeholder: "JO31AA" })),
          lab("Band", el("select", { id: "s-band" }, BANDS.map((b) => el("option", { value: b, selected: (s?.band || "144MHz") === b ? 1 : null }, b)))),
          lab("Modus", el("select", { id: "s-mode" }, ["SSB", "CW", "FM", "MIXED"].map((m) => el("option", { value: m, selected: (s?.mode || "SSB") === m ? 1 : null }, m)))),
          lab(s ? "Neues Passwort (leer = unverändert)" : "Stations-Passwort", el("input", { id: "s-pw", type: "text", placeholder: "für Operatoren" })),
          lab("Start-Seriennummer", el("input", { id: "s-serial", type: "number", min: 1, value: s?.serial_next || 1 }))),
        el("details", {}, el("summary", { class: "muted" }, "Angaben für die EDI-Abgabe (Standort, Verantwortlicher, Technik)"),
          el("div", { class: "grid2" }, INFO_FIELDS.map(([k, l]) => lab(l, el("input", { id: `i-${k}`, value: info[k] ?? prevInfo[k] ?? "" }))))),
        el("div", { class: "row" }, el("button", { class: "primary" }, "Speichern"), el("button", { type: "button", class: "ghost", "data-close": 1 }, "Abbrechen")))));
    box.querySelector("#s-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const g = (id) => box.querySelector(id).value.trim();
      const infoOut = {}; INFO_FIELDS.forEach(([k]) => { infoOut[k] = g(`#i-${k}`); });
      const body = { call: g("#s-call"), locator: g("#s-loc"), band: g("#s-band"), mode: g("#s-mode"), info: infoOut, serial_next: Number(g("#s-serial")) };
      if (g("#s-pw") || !s) body.password = g("#s-pw");
      try {
        const r = s ? await api("PATCH", `/api/stations/${s.id}`, body) : await api("POST", `/api/contests/${S.contestId}/stations`, body);
        if (!s) { S.stationId = r.id; save(); }
        closeModal(); toast("Station gespeichert", "ok");
      } catch (err) { toast(err.message, "err"); }
    });
  }

  $("#imp-target").addEventListener("change", (e) => $("#imp-station-wrap").classList.toggle("hidden", e.target.value !== "station"));
  $("#import-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData();
    const file = $("#imp-file").files[0]; if (!file) return;
    fd.append("file", file);
    const target = $("#imp-target").value;
    fd.append("target", target === "station" ? "qsos" : target);
    if (target === "station") fd.append("station_id", $("#imp-station").value);
    if ($("#imp-contest-name").value) fd.append("contest_name", $("#imp-contest-name").value);
    const out = $("#imp-result"); out.classList.remove("hidden"); out.textContent = "Importiere …";
    try {
      const r = await api("POST", "/api/import", fd);
      out.textContent = `Format: ${r.kind}\nQSOs übernommen: ${r.qsos}\nCall-Buch-Einträge: ${r.callbook}` + (r.station_id ? `\nNeue Station #${r.station_id} angelegt` : "") + (r.warnings.length ? `\n\nHinweise:\n${r.warnings.join("\n")}` : "");
      toast("Import abgeschlossen", "ok");
      await loadContests(); renderAdmin();
    } catch (err) { out.textContent = "Fehler: " + err.message; toast(err.message, "err"); }
  });
  $("#cb-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try { await api("POST", "/api/callbook", { call: $("#cb-call").value, locator: $("#cb-loc").value, name: $("#cb-name").value }); toast("Call gespeichert", "ok"); $("#cb-call").value = $("#cb-loc").value = $("#cb-name").value = ""; renderAdmin(); } catch (err) { toast(err.message, "err"); }
  });

  boot().catch((e) => toast("Start fehlgeschlagen: " + e.message, "err"));
})();
