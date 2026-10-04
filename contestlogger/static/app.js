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
    rig: {},
    locAuto: false,
  };
  // ------------------------------------------------------------ Sprache
  // Schlüssel = deutscher Originaltext; Übersetzungen kommen aus /static/lang/<code>.json bzw. data/lang/<code>.json.
  let LANG = {};
  const t = (key, vars) => {
    let out = LANG[key] ?? key;
    if (vars) out = out.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
    return out;
  };
  window.t = t;
  async function loadLanguage() {
    const code = localStorage.getItem("cl.lang") || (navigator.language || "de").slice(0, 2).toLowerCase();
    LANG = {};
    if (code !== "de") {
      try { LANG = await (await fetch(`/api/lang/${code}`)).json(); } catch (_) { LANG = {}; }
    }
    document.documentElement.lang = code;
    translateDom(document.body);
  }
  const ORIG = new WeakMap();
  function translateDom(root) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: (n) => (n.parentNode && !["SCRIPT", "STYLE", "TEMPLATE"].includes(n.parentNode.nodeName) && n.nodeValue.trim() ? 1 : 2) });
    const nodes = []; let n; while ((n = walker.nextNode())) nodes.push(n);
    for (const node of nodes) {
      const orig = ORIG.get(node) ?? node.nodeValue; ORIG.set(node, orig);
      const trimmed = orig.trim(); const tr = t(trimmed);
      if (tr !== trimmed) node.nodeValue = orig.replace(trimmed, tr);
    }
    root.querySelectorAll("[placeholder], [title]").forEach((e) => {
      for (const a of ["placeholder", "title"]) {
        if (!e.hasAttribute(a)) continue;
        const k = `__i18n_${a}`; const orig = e[k] ?? e.getAttribute(a); e[k] = orig;
        e.setAttribute(a, t(orig));
      }
    });
    document.querySelectorAll("template").forEach((tpl) => { tpl.content.querySelectorAll("*").forEach(() => {}); });
  }
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
  const fromTpl = (id) => { const f = document.getElementById(id).content.cloneNode(true); const d = document.createElement("div"); d.append(f); translateDom(d); const out = document.createDocumentFragment(); while (d.firstChild) out.append(d.firstChild); return out; };
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
    const c = contest(); const cd = $("#countdown");
    if (c?.end_utc && c?.start_utc) {
      const start = Date.parse(c.start_utc), end = Date.parse(c.end_utc), now = d.getTime();
      const fmt = (ms) => { const m = Math.floor(ms / 60000); return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`; };
      cd.textContent = now < start ? t("Start in {t}", { t: fmt(start - now) }) : now < end ? t("noch {t}", { t: fmt(end - now) }) : t("Contest beendet");
      cd.className = "tag " + (now < start ? "" : now < end ? "me" : "");
    } else cd.textContent = "";
  }
  setInterval(tickClock, 500); tickClock();

  // ------------------------------------------------------------ Tabs
  $$(".tabs button").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
  function showView(v) {
    $$(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
    $$(".view").forEach((s) => s.classList.toggle("active", s.id === `view-${v}`));
    if (v === "stats") { renderContest(); renderStats(); }
    if (v === "fulllog") renderFullLog();
    if (v === "admin") renderAdmin();
    if (v === "log") setTimeout(() => $("#f-call").focus(), 20);
  }

  // ------------------------------------------------------------ Start
  async function boot() {
    S.info = await GET("/api/info");
    await loadLanguage();
    renderLangSelect();
    $("#version").textContent = "v" + S.info.version;
    $("#footer-text").textContent = `${S.info.app} ${S.info.version} · ${S.info.copyright} · ${t("lokal, offline, im LAN")}`;
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
          S.adminToken = r.token; save(); closeModal(); toast(t("Admin-Passwort gesetzt – du bist als Admin angemeldet."), "ok"); resolve();
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

  // ------------------------------------------------------------ Töne (WebAudio, keine Dateien nötig)
  const Sound = {
    on: localStorage.getItem("cl.sound") !== "off",
    ctx: null,
    ensure() { if (!this.ctx) { try { this.ctx = new (window.AudioContext || window.webkitAudioContext)(); } catch (_) { return null; } } if (this.ctx.state === "suspended") this.ctx.resume(); return this.ctx; },
    tone(freq, start, dur, type = "sine", gain = 0.18) {
      const c = this.ensure(); if (!c) return;
      const o = c.createOscillator(), g = c.createGain();
      o.type = type; o.frequency.value = freq; o.connect(g); g.connect(c.destination);
      const t = c.currentTime + start;
      g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(gain, t + 0.01); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      o.start(t); o.stop(t + dur + 0.02);
    },
    play(kind) {
      if (!this.on) return;
      if (kind === "qso") { this.tone(880, 0, 0.12); this.tone(1320, 0.1, 0.18); }          // Pling – QSO geloggt
      else if (kind === "dupe") { this.tone(220, 0, 0.18, "square", 0.12); this.tone(180, 0.2, 0.25, "square", 0.12); } // Brummen – Dupe
      else if (kind === "chat") { this.tone(1046, 0, 0.08); this.tone(1568, 0.09, 0.12); }   // Ping – Chat
      else if (kind === "other") { this.tone(660, 0, 0.06, "triangle", 0.08); }             // Tick – andere Station hat geloggt
      else if (kind === "error") { this.tone(300, 0, 0.15, "sawtooth", 0.1); }
    },
  };
  const renderSoundBtn = () => $("#sound-btn").classList.toggle("off", !Sound.on);
  renderSoundBtn();
  $("#sound-btn").addEventListener("click", () => { Sound.on = !Sound.on; localStorage.setItem("cl.sound", Sound.on ? "on" : "off"); renderSoundBtn(); if (Sound.on) Sound.play("chat"); });
  document.addEventListener("pointerdown", () => Sound.ensure(), { once: true });
  document.addEventListener("keydown", () => Sound.ensure(), { once: true });

  // ------------------------------------------------------------ QR-Code
  $("#qr-btn").addEventListener("click", () => {
    const local = ["localhost", "127.0.0.1", "::1"].includes(location.hostname);
    const url = local && S.info.public_url ? S.info.public_url : location.origin + "/";
    const box = modal(fromTpl("tpl-qr"));
    box.querySelector("#qr-img").src = `/api/qr.svg?text=${encodeURIComponent(url)}`;
    box.querySelector("#qr-url").textContent = url;
  });

  // ------------------------------------------------------------ Sprachauswahl
  async function renderLangSelect() {
    const sel = $("#lang-select"); if (!sel) return;
    let langs = [{ code: "de", name: "Deutsch" }];
    try { langs = await GET("/api/lang"); } catch (_) { /* */ }
    sel.innerHTML = "";
    const cur = localStorage.getItem("cl.lang") || (navigator.language || "de").slice(0, 2).toLowerCase();
    for (const l of langs) sel.append(el("option", { value: l.code, selected: l.code === cur ? 1 : null }, l.name));
    if (!langs.find((l) => l.code === cur)) sel.value = "de";
    sel.onchange = () => { localStorage.setItem("cl.lang", sel.value); location.reload(); };
  }

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
    for (const c of S.contests) sc.append(el("option", { value: c.id }, c.name + (c.archived ? t(" (Archiv)") : "")));
    if (!S.contests.length) sc.append(el("option", { value: "" }, t("– kein Contest – (Verwaltung)")));
    sc.value = S.contestId ?? "";
    ss.innerHTML = "";
    const c = contest();
    for (const s of c?.stations || []) ss.append(el("option", { value: s.id }, `${s.call} · ${s.band}`));
    if (!c?.stations?.length) ss.append(el("option", { value: "" }, t("– keine Station –")));
    ss.value = S.stationId ?? "";
    const st = station();
    if (st && !st.has_password && !canLog()) autoUnlock(st);
    if (st) {
      const rig = S.rig[st.id];
      $("#station-meta").innerHTML = `${esc(st.locator)} · ${esc(st.mode)} · ${t("nächste Nr.")} <span class="serial-badge">${pad3(st.serial_next)}</span>` + (rig?.freq ? ` · 📻 ${esc(rig.freq)} MHz ${esc(rig.mode || "")}` : "");
      $("#f-nr-sent").value = pad3(st.serial_next);
      const unlocked = canLog();
      $("#station-state").innerHTML = unlocked
        ? `<span class="tag me">${t("freigeschaltet")}</span>`
        : `<button class="ghost small" id="btn-unlock">🔒 ${t("freischalten")}</button>`;
      $("#btn-unlock")?.addEventListener("click", () => askUnlock(st));
      $("#qso-form").querySelectorAll("input,button").forEach((i) => { if (i.id !== "f-nr-sent") i.disabled = !unlocked; });
      $("#hint-info").textContent = unlocked ? t("Rufzeichen eingeben – Vorschläge aus Call-Buch und alten Logs erscheinen automatisch.") : t("Station ist nur im Lesemodus. Zum Loggen mit Stations-Passwort freischalten.");
    } else {
      $("#station-meta").textContent = "";
      $("#station-state").textContent = S.contests.length ? "" : t("Lege unter „Verwaltung“ einen Contest und eine Station an.");
      $("#qso-form").querySelectorAll("input,button").forEach((i) => { i.disabled = true; });
    }
    for (const f of ["adi", "csv"]) $(`#exp-${f}`).href = st ? `/api/stations/${st.id}/export.${f}` : "#";
    renderMacroBar();
    $("#exp-zip").href = S.contestId ? `/api/contests/${S.contestId}/export.zip` : "#";
    $("#export-station").textContent = st ? `– ${st.call} ${st.band}` : "";
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

  async function autoUnlock(st) {
    try {
      const r = await api("POST", `/api/stations/${st.id}/unlock`, { password: "" });
      S.stationTokens[st.id] = r.token; save(); renderStationBar(); renderQsos();
    } catch (_) { askUnlock(st); }
  }
  function askUnlock(st) {
    if (!st) return;
    if (!st.has_password) return autoUnlock(st);
    const box = modal(fromTpl("tpl-unlock"));
    box.querySelector(".st-name").textContent = `${st.call} (${st.band})`;
    box.querySelector("#unlock-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const r = await api("POST", `/api/stations/${st.id}/unlock`, { password: box.querySelector("#unlock-pw").value });
        S.stationTokens[st.id] = r.token; save(); closeModal(); renderStationBar(); renderQsos(); toast(t("{call} freigeschaltet", { call: st.call }), "ok"); $("#f-call").focus();
      } catch (err) { toast(err.message, "err"); }
    });
  }

  // ------------------------------------------------------------ QSOs
  async function loadQsos() {
    if (!S.stationId) { S.qsos = []; renderQsos(); renderKpis(null); return; }
    S.qsos = await GET(`/api/stations/${S.stationId}/qsos`);
    renderQsos();
    renderKpis();
    const m = makeMap("map-log"); if (m) { drawQsoDots(m, S.qsos); updateLogMap(); }
    if ($("#view-fulllog").classList.contains("active")) renderFullLog();
    if ($("#view-stats").classList.contains("active")) renderStats();
  }

  function qsoRow(q, full) {
    const tr = el("tr", { class: q.dupe ? "dupe" : "" });
    const cells = full
      ? [q.serial_sent, fmtDate(q.ts_utc), fmtTime(q.ts_utc), q.call, q.rst_sent, pad3(q.serial_sent), q.rst_rcvd, q.serial_rcvd, q.locator, q.km, q.bearing, q.points, q.country, q.mode, q.freq || "", q.comment, q.logged_by]
      : [fmtTime(q.ts_utc), q.call, `${q.rst_sent} ${pad3(q.serial_sent)}`, `${q.rst_rcvd} ${q.serial_rcvd}`, q.locator, q.km, q.bearing, q.points, q.country, q.logged_by];
    cells.forEach((c, i) => tr.append(el("td", { class: typeof c === "number" ? "num" : "" }, c)));
    if (q.dupe) tr.title = t("Doppel-QSO (0 Punkte)");
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

  // ---- Log-Prüfung (Pflicht vor dem EDI-Export)
  async function runCheck(thenExport) {
    const st = station(); if (!st) return toast(t("Keine Station gewählt"), "err");
    let res; try { res = await GET(`/api/stations/${st.id}/check`); } catch (err) { return toast(err.message, "err"); }
    const list = el("div", { class: "check-list" });
    const item = (x, cls) => el("div", { class: cls, onclick: () => { if (x.qso_id) { const q = S.qsos.find((q) => q.id === x.qso_id); closeModal(); if (q) editQso(q); } } },
      x.serial ? el("span", { class: "n" }, `#${pad3(x.serial)} ${x.call}`) : null, x.msg);
    res.errors.forEach((x) => list.append(item(x, "err")));
    res.warnings.forEach((x) => list.append(item(x, "warn")));
    const dl = (force) => { window.location.href = `/api/stations/${st.id}/export.edi${force ? "?force=1" : ""}`; };
    const buttons = el("div", { class: "row" });
    if (res.ok) buttons.append(el("button", { class: "primary", onclick: () => { closeModal(); dl(false); } }, t("EDI herunterladen")));
    else if (S.adminToken) buttons.append(el("button", { class: "ghost danger", onclick: () => { if (confirm(t("Mit Fehlern exportieren? Der Auswerter wird diese QSOs wahrscheinlich streichen."))) { closeModal(); dlForce(); } } }, t("Trotzdem exportieren (Admin)")));
    buttons.append(el("button", { type: "button", class: "ghost", "data-close": 1 }, t("Schließen")));
    const dlForce = async () => {
      const r = await fetch(`/api/stations/${st.id}/export.edi?force=1`, { headers: { "X-Admin-Token": S.adminToken } });
      const blob = await r.blob(); const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `${st.call.replace("/", "-")}_${st.band}.edi`; a.click();
    };
    modal(el("div", {},
      el("h3", {}, t("Log-Prüfung {call} {band} – {n} QSOs", { call: st.call, band: st.band, n: res.qsos })),
      res.ok ? el("p", { class: "check-ok" }, t("✔ Keine Fehler{w} – das Log kann abgegeben werden.", { w: res.warnings.length ? ", " + res.warnings.length + " " + t("Hinweise") : "" }))
             : el("p", { class: "hint warn" }, t("✖ {e} Fehler, {w} Hinweise. Fehler müssen vor dem EDI-Export behoben werden (Klick auf eine Zeile öffnet das QSO).", { e: res.errors.length, w: res.warnings.length })),
      list, buttons));
    if (res.ok && thenExport) { closeModal(); dl(false); }
  }
  $("#btn-check").addEventListener("click", () => runCheck(false));
  $("#exp-edi").addEventListener("click", () => runCheck(true));

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
    const k = (v, l, cls = "") => el("span", { class: `st ${cls}` }, el("b", {}, v), l);
    box.append(k(valid.length, t("QSOs")), k(pts.toLocaleString("de"), t("Punkte")), k(squares, t("Großfelder")),
      k(valid.length ? Math.round(pts / valid.length) : 0, t("Ø km")), k(rate, t("QSOs / letzte h")), k(S.qsos.length - valid.length, t("Dupes")),
      k(odx ? `${odx.call} ${odx.km} km` : "–", "ODX", "odx"));
  }

  // ---- Eingabeformular
  const F = { call: $("#f-call"), rs: $("#f-rst-sent"), ns: $("#f-nr-sent"), rr: $("#f-rst-rcvd"), nr: $("#f-nr-rcvd"), loc: $("#f-loc"), cmt: $("#f-comment") };
  const order = [F.call, F.rs, F.rr, F.nr, F.loc, F.cmt];

  function clearForm() {
    F.call.value = ""; F.rs.value = "59"; F.rr.value = "59"; F.nr.value = ""; F.loc.value = ""; F.cmt.value = "";
    S.locAuto = false; F.loc.classList.remove("auto");
    S.editingId = null; $("#qso-form button.primary").textContent = t("Loggen ⏎");
    hideSuggest(); updateHints(); F.call.focus();
  }
  $("#btn-clear").addEventListener("click", clearForm);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (!$("#modal").classList.contains("hidden")) closeModal();
      else if ($("#view-log").classList.contains("active")) { clearForm(); $("#macro-flash").classList.add("hidden"); if (canLog() && S.rig[S.stationId]?.cw) api("POST", `/api/stations/${S.stationId}/cw`, { stop: true }).catch(() => {}); }
    }
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
      // Leertaste springt: Rufzeichen -> Nr erhalten -> Locator -> Kommentar -> Rufzeichen
      if (e.key === " " && inp !== F.cmt) {
        e.preventDefault();
        if (inp === F.call) lookupCall();
        const hop = { [F.call.id]: F.nr, [F.rs.id]: F.nr, [F.rr.id]: F.nr, [F.nr.id]: F.loc, [F.loc.id]: F.cmt };
        (hop[inp.id] || F.call).focus();
      }
    });
  });
  F.call.addEventListener("input", () => {
    F.call.value = F.call.value.toUpperCase();
    if (S.locAuto) { F.loc.value = ""; S.locAuto = false; F.loc.classList.remove("auto"); }
    fetchSuggest(); updateHints();
    clearTimeout(lookupTimer); lookupTimer = setTimeout(lookupCall, 150);
    if (!$("#macro-bar").classList.contains("hidden")) renderMacroBar();
  });
  F.loc.addEventListener("input", () => { F.loc.value = F.loc.value.toUpperCase(); updateHints(); });
  F.call.addEventListener("blur", () => setTimeout(hideSuggest, 150));
  F.nr.addEventListener("blur", () => { if (/^\d+$/.test(F.nr.value)) F.nr.value = pad3(Number(F.nr.value)); });

  const coreOf = (call) => (call || "").trim().toUpperCase().split("/").filter((p) => !["P", "M", "MM", "AM", "QRP"].includes(p) && !/^\d+$/.test(p)).sort((a, b) => b.length - a.length)[0] || "";
  function setAutoLocator(loc) {
    // Locator aus der Stationsdatenbank übernehmen, solange der Operator nichts eigenes eingetragen hat
    if (!loc || (F.loc.value && !S.locAuto)) return;
    if (F.loc.value !== loc) { F.loc.value = loc; S.locAuto = true; F.loc.classList.add("auto"); updateHints(); }
  }
  let lookupTimer;
  async function lookupCall() {
    const call = F.call.value.trim();
    if (call.length < 3) return;
    try {
      const r = await GET(`/api/lookup?call=${encodeURIComponent(call)}`);
      if (call !== F.call.value.trim()) return;
      if (r && r.locator) { setAutoLocator(r.locator); if (r.source !== "local") toast(`${r.call}: ${r.locator}${r.name ? " · " + r.name : ""} (${r.source === "hamqth" ? "HamQTH" : "QRZ"})`); }
      else if (r && r.source === "error") toast(r.error, "err");
    } catch (_) { /* */ }
  }
  F.loc.addEventListener("input", () => { S.locAuto = false; F.loc.classList.remove("auto"); });
  F.call.addEventListener("blur", lookupCall);

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
    const exact = S.suggestions.find((s) => s.call === coreOf(F.call.value));
    if (exact) setAutoLocator(exact.locator);
    if (!S.suggestions.length) return hideSuggest();
    S.suggestions.slice(0, 10).forEach((s, i) => {
      const meta = [];
      if (s.km) meta.push(`${s.km} km · ${s.bearing}°`);
      if (s.qso_count) meta.push(`${s.qso_count}× ${t("gearbeitet")}`);
      if (s.last_seen) meta.push(`${t("zuletzt")} ${fmtDate(s.last_seen)}`);
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
      dupeBox.textContent = t("⚠ {call} bereits gearbeitet um {time} UTC ({loc}) – DUPE!", { call, time: fmtTime(prev[prev.length - 1].ts_utc), loc: prev[prev.length - 1].locator });
      dupeBox.classList.remove("hidden");
    } else dupeBox.classList.add("hidden");
    clearTimeout(hintTimer);
    if (st && /^[A-R]{2}\d{2}([A-X]{2})?$/.test(loc)) {
      hintTimer = setTimeout(async () => {
        try {
          const r = await GET(`/api/calc?my=${st.locator}&loc=${loc}&call=${encodeURIComponent(call)}`);
          $("#hint-geo").textContent = r.valid ? `${r.km} km · ${r.bearing}°` : "— km · —°";
          const pb = $("#hint-plaus");
          if (r.warnings && r.warnings.length) { pb.textContent = "⚠ " + r.warnings.join(" · "); pb.classList.remove("hidden"); } else pb.classList.add("hidden");
          updateLogMap();
        } catch (_) { /* */ }
      }, 80);
    } else { $("#hint-geo").textContent = "— km · —°"; $("#hint-plaus").classList.add("hidden"); updateLogMap(); }
  }

  $("#qso-form").addEventListener("submit", (e) => { e.preventDefault(); submitQso(); });
  async function submitQso() {
    if (!canLog()) return toast(t("Station ist nicht freigeschaltet"), "err");
    const body = { call: F.call.value.trim(), locator: F.loc.value.trim(), rst_sent: F.rs.value.trim() || "59", rst_rcvd: F.rr.value.trim() || "59", serial_rcvd: F.nr.value.trim(), comment: F.cmt.value.trim() };
    if (!S.editingId && S.rig[S.stationId]?.freq) body.freq = S.rig[S.stationId].freq;
    if (body.call.length < 3) return F.call.focus();
    try {
      if (S.editingId) {
        await api("PATCH", `/api/qsos/${S.editingId}`, body);
        toast(t("QSO geändert"), "ok");
      } else {
        const q = await api("POST", `/api/stations/${S.stationId}/qsos`, body);
        toast(q.dupe ? t("DUPE geloggt: {call} (0 Punkte)", q) : t("{call} {locator} · {km} km · {points} Punkte", q), q.dupe ? "err" : "ok");
        Sound.play(q.dupe ? "dupe" : "qso");
      }
      clearForm();
    } catch (err) { toast(err.message, "err"); Sound.play("error"); }
  }

  function editQso(q) {
    const box = modal(el("div", {},
      el("h3", {}, t("QSO #{nr} bearbeiten – {call}", { nr: q.serial_sent, call: q.call })),
      el("form", { id: "edit-form", class: "stack" },
        el("div", { class: "grid2" },
          lab(t("Datum/Zeit UTC"), el("input", { id: "e-ts", value: q.ts_utc.slice(0, 16).replace("T", " ") })),
          lab(t("Rufzeichen"), el("input", { id: "e-call", value: q.call })),
          lab(t("Locator"), el("input", { id: "e-loc", value: q.locator })),
          lab(t("Nr gegeben"), el("input", { id: "e-ns", value: q.serial_sent, type: "number", min: 1 })),
          lab(t("RST gegeben"), el("input", { id: "e-rs", value: q.rst_sent })),
          lab(t("RST erhalten"), el("input", { id: "e-rr", value: q.rst_rcvd })),
          lab(t("Nr erhalten"), el("input", { id: "e-nr", value: q.serial_rcvd })),
          lab(t("Modus"), el("input", { id: "e-mode", value: q.mode })),
          lab(t("Kommentar"), el("input", { id: "e-cmt", value: q.comment }))),
        el("div", { class: "row" }, el("button", { class: "primary" }, t("Speichern")), el("button", { type: "button", class: "ghost", "data-close": 1 }, t("Abbrechen")),
          el("span", { class: "grow" }), el("button", { type: "button", class: "ghost danger", onclick: () => { closeModal(); deleteQso(q); } }, t("Löschen"))))));
    box.querySelector("#edit-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const g = (id) => box.querySelector(id).value.trim();
      const ts = g("#e-ts").replace(" ", "T");
      if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(ts)) return toast(t("Zeitformat: JJJJ-MM-TT HH:MM"), "err");
      try {
        await api("PATCH", `/api/qsos/${q.id}`, { ts_utc: ts.slice(0, 16) + ":00Z", call: g("#e-call"), locator: g("#e-loc"), serial_sent: Number(g("#e-ns")), rst_sent: g("#e-rs"), rst_rcvd: g("#e-rr"), serial_rcvd: g("#e-nr"), mode: g("#e-mode"), comment: g("#e-cmt") }, { stationId: q.station_id });
        closeModal(); toast(t("QSO gespeichert"), "ok");
      } catch (err) { toast(err.message, "err"); }
    });
  }
  const lab = (text, input) => el("label", {}, text, input);
  async function deleteQso(q) {
    if (!confirm(t("QSO #{nr} mit {call} wirklich löschen?", { nr: q.serial_sent, call: q.call }))) return;
    try { await api("DELETE", `/api/qsos/${q.id}`, null, { stationId: q.station_id }); toast(t("QSO gelöscht")); } catch (err) { toast(err.message, "err"); }
  }
  $("#btn-serial").addEventListener("click", async () => {
    const st = station(); if (!st || !canLog()) return toast(t("Station nicht freigeschaltet"), "err");
    const v = prompt(t("Nächste zu vergebende Seriennummer für {call}:", { call: st.call }), st.serial_next);
    if (v === null || !/^\d+$/.test(v)) return;
    try { await api("POST", `/api/stations/${st.id}/serial`, { start: Number(v) }); toast(t("Nächste Nr.: {nr}", { nr: pad3(v) }), "ok"); } catch (err) { toast(err.message, "err"); }
  });

  // ------------------------------------------------------------ Makros (F1–F8)
  const MACRO_DEFAULTS = { F1: "CQ Contest {mycall} {mycall} Contest", F2: "{call}", F3: "{rst} {nr} {myloc}", F4: "QRZ? {mycall}", F5: "{mycall}", F6: "TU {mycall}", F7: "AGN?", F8: "NR?" };
  const MACRO_KEYS = Object.keys(MACRO_DEFAULTS);
  const macros = () => ({ ...MACRO_DEFAULTS, ...((station()?.info || {}).macros || {}) });
  function expandMacro(text) {
    const st = station() || {};
    return text.replace(/\{(\w+)\}/g, (_, k) => ({
      mycall: st.call || "", myloc: st.locator || "", call: F.call.value.trim() || "?", rst: F.rs.value.trim() || "59",
      nr: pad3(st.serial_next || 1), loc: F.loc.value.trim() || "?", nick: S.nick, band: st.band || "",
    })[k] ?? `{${k}}`);
  }
  function renderMacroBar() {
    const list = $("#macro-list"); list.innerHTML = "";
    const m = macros();
    MACRO_KEYS.forEach((k) => list.append(el("div", { title: m[k], onclick: () => fireMacro(k) }, el("b", {}, k), expandMacro(m[k]))));
  }
  let flashTimer;
  async function fireMacro(key) {
    const text = expandMacro(macros()[key]);
    const f = $("#macro-flash"); f.innerHTML = ""; f.append(text, el("small", {}, `${key}${S.rig[S.stationId]?.cw ? " · " + t("wird als CW gesendet") : ""}`));
    f.classList.remove("hidden"); clearTimeout(flashTimer); flashTimer = setTimeout(() => f.classList.add("hidden"), 4000);
    if (canLog() && S.stationId) { try { await api("POST", `/api/stations/${S.stationId}/cw`, { text }); } catch (_) { /* keine Bridge */ } }
  }
  function macroEditor() {
    const st = station(); if (!st) return;
    const m = macros();
    const box = modal(el("div", {}, el("h3", {}, t("Makros für {call}", st)),
      el("p", { class: "muted small" }, t("Platzhalter: {mycall} {myloc} {call} {loc} {rst} {nr} {nick} {band}. Die Makros gelten für alle Operatoren dieser Station. Mit laufender CAT-Bridge (--cw) werden sie als CW gegeben, sonst nur groß angezeigt.")),
      el("form", { id: "macro-form", class: "stack" },
        MACRO_KEYS.map((k) => lab(k, el("input", { id: `m-${k}`, value: m[k] }))),
        el("div", { class: "row" }, el("button", { class: "primary" }, t("Speichern")), el("button", { type: "button", class: "ghost", onclick: () => { MACRO_KEYS.forEach((k) => { box.querySelector(`#m-${k}`).value = MACRO_DEFAULTS[k]; }); } }, t("Standard")), el("button", { type: "button", class: "ghost", "data-close": 1 }, t("Abbrechen"))))));
    box.querySelector("#macro-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const out = {}; MACRO_KEYS.forEach((k) => { out[k] = box.querySelector(`#m-${k}`).value; });
      try { await api("PATCH", `/api/stations/${st.id}`, { info: { ...(st.info || {}), macros: out } }); closeModal(); toast(t("Makros gespeichert"), "ok"); } catch (err) { toast(err.message, "err"); }
    });
  }
  $("#btn-macro-edit").addEventListener("click", macroEditor);
  document.addEventListener("keydown", (e) => {
    if (!$("#view-log").classList.contains("active") || !$("#modal").classList.contains("hidden")) return;
    if (e.key === "F9") { e.preventDefault(); $("#macro-bar").classList.toggle("hidden"); localStorage.setItem("cl.macrobar", $("#macro-bar").classList.contains("hidden") ? "0" : "1"); renderMacroBar(); return; }
    if (/^F[1-8]$/.test(e.key)) { e.preventDefault(); if (station()) fireMacro(e.key); }
  });
  if (localStorage.getItem("cl.macrobar") === "1") $("#macro-bar").classList.remove("hidden");

  // ------------------------------------------------------------ Karte (Leaflet, lokal gebündelt; Kacheln von OSM oder eigenem Server)
  function locToLatLon(loc) {
    loc = (loc || "").toUpperCase();
    if (!/^[A-R]{2}[0-9]{2}([A-X]{2})?$/.test(loc)) return null;
    let lon = (loc.charCodeAt(0) - 65) * 20 - 180 + Number(loc[2]) * 2;
    let lat = (loc.charCodeAt(1) - 65) * 10 - 90 + Number(loc[3]);
    if (loc.length >= 6) { lon += (loc.charCodeAt(4) - 65) * (2 / 24) + 1 / 24; lat += (loc.charCodeAt(5) - 65) * (1 / 24) + 1 / 48; }
    else { lon += 1; lat += 0.5; }
    return [lat, lon];
  }
  function geodesic(a, b, n = 48) {
    const r = Math.PI / 180, [lat1, lon1] = [a[0] * r, a[1] * r], [lat2, lon2] = [b[0] * r, b[1] * r];
    const d = 2 * Math.asin(Math.sqrt(Math.sin((lat2 - lat1) / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin((lon2 - lon1) / 2) ** 2));
    if (d < 1e-9) return [a, b];
    const pts = [];
    for (let i = 0; i <= n; i++) {
      const f = i / n, A = Math.sin((1 - f) * d) / Math.sin(d), B = Math.sin(f * d) / Math.sin(d);
      const x = A * Math.cos(lat1) * Math.cos(lon1) + B * Math.cos(lat2) * Math.cos(lon2);
      const y = A * Math.cos(lat1) * Math.sin(lon1) + B * Math.cos(lat2) * Math.sin(lon2);
      const z = A * Math.sin(lat1) + B * Math.sin(lat2);
      pts.push([Math.atan2(z, Math.sqrt(x * x + y * y)) / r, Math.atan2(y, x) / r]);
    }
    return pts;
  }
  const Maps = {};
  function makeMap(id) {
    if (Maps[id]) return Maps[id];
    if (typeof L === "undefined") return null;
    const map = L.map(id, { zoomControl: true, attributionControl: true }).setView([51, 10], 5);
    const url = localStorage.getItem("cl.tileurl") || S.info.tile_url || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
    L.tileLayer(url, { maxZoom: 18, attribution: "© OpenStreetMap" }).addTo(map);
    const m = { map, layer: L.layerGroup().addTo(map), dots: L.layerGroup().addTo(map) };
    Maps[id] = m;
    return m;
  }
  function drawQsoDots(m, qsos) {
    m.dots.clearLayers();
    for (const q of qsos) {
      const p = locToLatLon(q.locator); if (!p || q.dupe) continue;
      L.circleMarker(p, { radius: 3, color: "#3ddc84", fillOpacity: .8, weight: 1 }).bindTooltip(`${q.call} ${q.locator} · ${q.km} km`).addTo(m.dots);
    }
  }
  function drawBearing(m, myLoc, loc, label) {
    m.layer.clearLayers();
    const a = locToLatLon(myLoc); if (!a) return;
    L.circleMarker(a, { radius: 6, color: "#3fb3ff", fillColor: "#3fb3ff", fillOpacity: 1 }).bindTooltip(`${t("Eigene Station")} ${myLoc}`).addTo(m.layer);
    const b = locToLatLon(loc);
    if (!b) { m.map.setView(a, 7); return; }
    // Feld des Partners als Rechteck
    const sz = loc.length >= 6 ? [1 / 24, 2 / 24] : [1, 2];
    L.rectangle([[b[0] - sz[0] / 2, b[1] - sz[1] / 2], [b[0] + sz[0] / 2, b[1] + sz[1] / 2]], { color: "#ff5c6c", weight: 1, fillOpacity: .25 }).addTo(m.layer);
    const pts = geodesic(a, b);
    L.polyline(pts, { color: "#ff5c6c", weight: 3, opacity: .9 }).addTo(m.layer);
    // Pfeilspitze in Linienrichtung
    const p1 = pts[pts.length - 2], p2 = pts[pts.length - 1];
    const ang = Math.atan2((p2[1] - p1[1]) * Math.cos(p2[0] * Math.PI / 180), p2[0] - p1[0]) * 180 / Math.PI;
    L.marker(b, { icon: L.divIcon({ className: "arrow-icon", html: `<div style="transform:rotate(${ang - 90}deg)">➤</div>`, iconSize: [26, 26], iconAnchor: [13, 13] }), interactive: false }).addTo(m.layer);
    if (label) L.marker(b, { icon: L.divIcon({ className: "map-label", html: label, iconAnchor: [-10, -10] }), interactive: false }).addTo(m.layer);
    m.map.fitBounds(L.latLngBounds(pts), { padding: [30, 30], maxZoom: 9 });
  }
  function updateLogMap() {
    const st = station(); const m = makeMap("map-log"); if (!m) return;
    setTimeout(() => m.map.invalidateSize(), 50);
    if (!st) { m.layer.clearLayers(); m.dots.clearLayers(); return; }
    const loc = F.loc.value.trim().toUpperCase();
    const geo = $("#hint-geo").textContent;
    drawBearing(m, st.locator, loc, locToLatLon(loc) ? `${F.call.value.trim() || loc} · ${geo}` : "");
    $("#map-info").textContent = locToLatLon(loc) ? `${loc}: ${geo}` : `${st.locator} · ${S.qsos.filter((q) => !q.dupe).length} QSOs`;
  }
  $("#lookup-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = { lookup_provider: $("#lookup-provider").value, lookup_user: $("#lookup-user").value.trim() };
    if ($("#lookup-pass").value) body.lookup_pass = $("#lookup-pass").value;
    try { await api("POST", "/api/settings", body); $("#lookup-pass").value = ""; toast(t("Einstellungen gespeichert"), "ok"); } catch (err) { toast(err.message, "err"); }
  });
  $("#btn-lookup-test").addEventListener("click", async () => {
    $("#lookup-result").textContent = "…";
    try { const r = await api("POST", "/api/lookup/test"); $("#lookup-result").textContent = r.msg; $("#lookup-result").style.color = r.ok ? "var(--ok)" : "var(--bad)"; } catch (err) { $("#lookup-result").textContent = err.message; }
  });
  $("#tile-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    try { await api("POST", "/api/settings", { tile_url: $("#tile-url").value.trim() }); toast(t("Kachel-URL gespeichert – Seite neu laden"), "ok"); } catch (err) { toast(err.message, "err"); }
  });

  // ------------------------------------------------------------ Scoreboard
  async function renderScoreboard() {
    const tb = $("#scoreboard tbody"); tb.innerHTML = "";
    if (!S.contestId) return;
    let rows = [];
    try { rows = await GET(`/api/contests/${S.contestId}/scoreboard`); } catch (_) { return; }
    tb.append(el("tr", {}, el("th", {}, t("Station")), el("th", {}, t("Band")), el("th", { class: "num" }, t("QSOs")), el("th", { class: "num" }, t("Pkt")), el("th", { class: "num" }, t("Felder")), el("th", { class: "num" }, "ODX"), el("th", { class: "num" }, "/h")));
    let tq = 0, tp = 0;
    for (const r of rows) {
      if (r.rig) S.rig[r.id] = r.rig;
      tq += r.qsos - r.dupes; tp += r.points || 0;
      const tr = el("tr", { style: "cursor:pointer", onclick: () => { $("#sel-station").value = r.id; $("#sel-station").dispatchEvent(new Event("change")); } },
        el("td", {}, r.id === S.stationId ? el("b", {}, r.call) : r.call, r.rig?.freq ? el("div", { class: "muted small" }, `${r.rig.freq} MHz`) : null), el("td", {}, r.band),
        el("td", { class: "num" }, r.qsos - r.dupes), el("td", { class: "num" }, (r.points || 0).toLocaleString("de")), el("td", { class: "num" }, r.squares),
        el("td", { class: "num" }, r.odx_km || "–"), el("td", { class: "num" }, r.rate_last_hour));
      tb.append(tr);
    }
    if (rows.length > 1) tb.append(el("tr", { class: "total" }, el("td", {}, el("b", {}, t("Gesamt"))), el("td", {}, `${rows.length} ${t("Bänder")}`), el("td", { class: "num" }, el("b", {}, tq)), el("td", { class: "num" }, el("b", {}, tp.toLocaleString("de"))), el("td", { colspan: 3 })));
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
      if (m.type === "chat") { appendChat(m.msg); if (m.msg.nick !== S.nick) Sound.play("chat"); }
      else if (m.type === "rig") { S.rig[m.station_id] = { freq: m.freq, mode: m.mode, ts: m.ts }; if (m.station_id === S.stationId) renderStationBar(); renderScoreboard(); }
      else if (m.type === "presence") renderPresence(m.users);
      else if (m.type === "update") {
        if (m.scope === "contests") await loadContests();
        else if (m.scope === "qsos") {
          if (m.station_id === S.stationId) { await loadQsos(); if (m.qso && m.by !== S.nick) { toast(`${m.by || "API"}: ${m.qso.call} ${t("geloggt")}`); Sound.play("other"); } }
          else if (m.qso && m.by !== S.nick) Sound.play("other");
          renderScoreboard();
          if ($("#view-stats").classList.contains("active")) renderContest();
          const st = S.contests.flatMap((c) => c.stations).find((s) => s.id === m.station_id);
          if (st && m.qso) { st.serial_next = Math.max(st.serial_next, m.qso.serial_sent + 1); if (st.id === S.stationId) renderStationBar(); }
        }
      }
    };
  }
  function sendStatus() { if (S.ws?.readyState === 1) S.ws.send(JSON.stringify({ type: "status", station_id: S.stationId })); }
  function renderPresence(users) {
    const names = users.map((u) => { const st = S.contests.flatMap((c) => c.stations).find((s) => s.id === u.station_id); return st ? `${u.nick}@${st.call}` : u.nick; });
    $("#online").textContent = `· ${t("online")}: ${names.join(", ")}`;
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
    if (!S.stationId) { root.append(el("p", { class: "muted" }, t("Keine Station ausgewählt."))); return; }
    let st; try { st = await GET(`/api/stations/${S.stationId}/stats`); } catch (e) { return; }
    const s = st.summary; const own = station();
    $("#stats-title").textContent = `${t("Station")} ${own?.call || ""} ${own?.band || ""}`;
    root.append(el("div", { class: "card kpis stat-card" },
      kpi(s.qsos - s.dupes, t("gültige QSOs")), kpi((s.points || 0).toLocaleString("de"), t("Punkte")), kpi(s.squares, t("Großfelder")),
      kpi(s.countries, t("Länder")), kpi(s.avg_km, t("Ø km / QSO")), kpi(s.dupes, t("Dupes")),
      kpi(s.odx ? `${s.odx.call} · ${s.odx.km} km` : "–", `ODX (${s.odx?.locator || ""})`, "wide")));
    const mapCard = card(t("Karte aller QSOs"), el("div", { id: "map-stats", class: "map tall" })); mapCard.style.gridColumn = "1 / -1"; root.append(mapCard);
    setTimeout(() => { const m = makeMap("map-stats"); if (!m) return; m.map.invalidateSize(); drawQsoDots(m, S.qsos); m.layer.clearLayers(); const a = locToLatLon(own?.locator); if (a) L.circleMarker(a, { radius: 7, color: "#3fb3ff", fillOpacity: 1 }).addTo(m.layer); const pts = S.qsos.map((q) => locToLatLon(q.locator)).filter(Boolean); if (pts.length) m.map.fitBounds(L.latLngBounds(pts.concat(a ? [a] : [])), { padding: [20, 20] }); }, 50);
    root.append(card(t("QSOs und Punkte pro Stunde"), barChart(st.per_hour.map((h) => ({ label: h.hour.slice(11) + "h", a: h.qsos, b: h.points })), t("QSOs"), t("Punkte"))));
    root.append(card(t("Entfernungsverteilung (km)"), barChart(st.distance.map((d) => ({ label: d.range, a: d.qsos, b: d.points })), t("QSOs"), t("Punkte"))));
    root.append(card(t("Richtungsverteilung von {loc}", { loc: own?.locator || "" }), rose(st.bearings)));
    root.append(card(t("Top 10 Entfernungen"), table([t("Call"), t("Locator"), "km", t("Pkt"), "UTC"], st.top.map((q) => [q.call, q.locator, q.km, q.points, fmtTime(q.ts_utc)]))));
    root.append(card(`${t("Großfelder")} (${st.squares.length})`, table([t("Feld"), t("QSOs"), t("Punkte")], st.squares.map((q) => [q.square, q.qsos, q.points]))));
    root.append(card(t("Länder"), table([t("Land"), t("QSOs"), t("Punkte"), t("ODX km")], st.countries.map((c) => [c.country, c.qsos, c.points, c.odx]))));
    root.append(card(t("Operatoren"), table([t("Nick"), t("QSOs"), t("Punkte")], st.operators.map((o) => [o.nick || "–", o.qsos, o.points]))));
  }
  const kpi = (v, l, cls = "") => el("div", { class: `kpi ${cls}` }, el("b", {}, v), el("span", {}, l));
  const card = (title, body) => el("div", { class: "card stat-card" }, el("h3", {}, title), body);
  function table(head, rows) {
    const t = el("table", { class: "compact" }, el("thead", {}, el("tr", {}, head.map((h) => el("th", {}, h)))));
    const tb = el("tbody"); rows.forEach((r) => tb.append(el("tr", {}, r.map((c) => el("td", { class: typeof c === "number" ? "num" : "" }, c)))));
    t.append(tb);
    return el("div", { class: "table-wrap" }, rows.length ? t : el("p", { class: "muted" }, t("Noch keine Daten.")));
  }
  function barChart(data, la, lb) {
    if (!data.length) return el("p", { class: "muted" }, t("Noch keine Daten."));
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
    add("text", { x: P, y: 12, class: "lbl" }, `■ ${la} (${t("blau")})   ■ ${lb} (${t("grün")})`);
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
      p.append(Object.assign(document.createElementNS(ns, "title"), { textContent: `${s.sector}–${s.sector + 30}°: ${s.qsos} QSOs, ${s.points} ${t("Punkte")}` }));
    });
    [["N", 0], ["O", 90], ["S", 180], ["W", 270]].forEach(([l, d]) => { const a = ((d - 90) * Math.PI) / 180; add("text", { x: C + (R + 12) * Math.cos(a), y: C + (R + 12) * Math.sin(a) + 4, "text-anchor": "middle" }, l); });
    return svg;
  }

  // ------------------------------------------------------------ Contest gesamt (alle Stationen)
  async function renderContest() {
    const root = $("#contest-root"); root.innerHTML = "";
    const c = contest(); $("#contest-title").textContent = c ? c.name : t("Kein Contest");
    if (!c) return;
    let st; try { st = await GET(`/api/contests/${c.id}/stats`); } catch (_) { return; }
    root.append(el("div", { class: "card kpis big", style: "grid-column: 1 / -1" },
      kpi(st.total_qsos, t("QSOs gesamt")), kpi(st.total_points.toLocaleString("de"), t("Punkte gesamt")), kpi(st.rate_last_hour, t("QSOs letzte Stunde")), kpi(st.unique_calls, t("verschiedene Calls")),
      kpi(st.unique_squares, t("Großfelder (alle Bänder)")), kpi(st.unique_countries, t("Länder")), kpi(st.bands.length, t("Bänder aktiv")),
      kpi(c.end_utc ? $("#countdown").textContent || "–" : "–", t("Restzeit"))));
    root.append(card(t("Stationen / Bänder"), table([t("Station"), t("Band"), t("QSOs"), t("Punkte"), t("Felder"), "ODX", t("ODX-Call"), "/h"],
      st.stations.map((s) => { const o = st.odx.find((x) => x.band === s.band); return [s.call, s.band, s.qsos - s.dupes, s.points || 0, s.squares, s.odx_km || 0, o ? `${o.call} ${o.locator}` : "–", s.rate_last_hour]; }))));
    // Stundenverlauf je Band (gestapelt)
    const hours = [...new Set(st.per_hour.map((h) => h.hour))].sort();
    const bands = [...new Set(st.per_hour.map((h) => h.band))];
    root.append(card(t("QSOs pro Stunde je Band"), stackedChart(hours, bands, st.per_hour)));
    const feed = el("div", { class: "feed table-wrap" }, table(["UTC", t("Station"), t("Band"), t("Call"), t("Locator"), "km", t("Pkt"), "Op"],
      st.recent.map((q) => [fmtTime(q.ts_utc), q.own_call, q.band, q.call + (q.dupe ? t(" (D)") : ""), q.locator, q.km, q.points, q.logged_by])));
    root.append(card(t("Letzte QSOs (alle Stationen)"), feed));
    root.append(card(t("Länder (alle Bänder)"), table([t("Land"), t("QSOs"), t("Punkte"), t("ODX km")], st.countries.map((x) => [x.country, x.qsos, x.points, x.odx]))));
    root.append(card(t("Operatoren (alle Bänder)"), table([t("Nick"), t("QSOs"), t("Punkte")], st.operators.map((o) => [o.nick || "–", o.qsos, o.points]))));
  }
  function stackedChart(hours, bands, rows) {
    if (!hours.length) return el("p", { class: "muted" }, t("Noch keine Daten."));
    const W = 600, H = 220, P = 30, bw = (W - 2 * P) / hours.length, ns = "http://www.w3.org/2000/svg";
    const colors = ["#3fb3ff", "#3ddc84", "#ffb347", "#ff5c6c", "#b48cff", "#6ee7e7"];
    const totals = hours.map((h) => rows.filter((r) => r.hour === h).reduce((a, r) => a + r.qsos, 0));
    const max = Math.max(1, ...totals);
    const svg = document.createElementNS(ns, "svg"); svg.setAttribute("viewBox", `0 0 ${W} ${H + 20}`);
    const add = (tag, attrs, text) => { const n = document.createElementNS(ns, tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); if (text != null) n.textContent = text; svg.append(n); return n; };
    add("line", { x1: P, y1: H, x2: W - P, y2: H, class: "axis" });
    hours.forEach((h, i) => {
      let y = H;
      bands.forEach((b, bi) => {
        const r = rows.find((x) => x.hour === h && x.band === b); if (!r) return;
        const hh = (r.qsos / max) * (H - 30); y -= hh;
        add("rect", { x: P + i * bw + 2, y, width: bw - 4, height: hh, fill: colors[bi % colors.length], rx: 2 }).append(Object.assign(document.createElementNS(ns, "title"), { textContent: `${h.slice(11)}h ${b}: ${r.qsos} QSOs, ${r.points} ${t("Punkte")}` }));
      });
      if (totals[i]) add("text", { x: P + i * bw + bw / 2, y: y - 3, class: "lbl", "text-anchor": "middle" }, totals[i]);
      if (hours.length <= 30 || i % 2 === 0) add("text", { x: P + i * bw + bw / 2, y: H + 13, class: "lbl", "text-anchor": "middle" }, h.slice(11) + "h");
    });
    bands.forEach((b, bi) => { add("rect", { x: P + bi * 90, y: 2, width: 10, height: 10, fill: colors[bi % colors.length] }); add("text", { x: P + bi * 90 + 14, y: 11, class: "lbl" }, b); });
    return svg;
  }
  $("#btn-bigscreen").addEventListener("click", () => { document.body.classList.toggle("bigscreen"); if (document.body.classList.contains("bigscreen")) document.documentElement.requestFullscreen?.().catch(() => {}); else document.exitFullscreen?.().catch(() => {}); });
  document.addEventListener("fullscreenchange", () => { if (!document.fullscreenElement) document.body.classList.remove("bigscreen"); });

  // ------------------------------------------------------------ Verwaltung
  const BANDS = ["50MHz", "70MHz", "144MHz", "432MHz", "1296MHz", "2320MHz", "3400MHz", "5760MHz", "10368MHz", "24048MHz", "47088MHz", "76032MHz"];
  const INFO_FIELDS = [["section", t("Wertungsgruppe (Single/Multi …)")], ["club", t("Club / DOK")], ["operators", t("Operatoren (MOpe1)")], ["site_address", t("Standort Adresse")], ["site_city", t("Standort PLZ Ort")],
    ["resp_name", t("Verantwortlicher Name")], ["resp_call", t("Verantwortlicher Call")], ["resp_address", t("Straße")], ["resp_zip", "PLZ"], ["resp_city", t("Ort")], ["resp_country", t("Land")], ["resp_phone", t("Telefon")], ["resp_email", t("E-Mail")],
    ["tx", t("Sender")], ["rx", t("Empfänger")], ["power", t("Leistung (W)")], ["antenna", t("Antenne")], ["antenna_height", t("Antennenhöhe über Grund (m)")], ["asl", t("Höhe über NN (m)")]];

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
        el("td", { class: "muted small" }, `${c.stations.length} ${t("Stationen")}${c.archived ? " · " + t("Archiv") : ""}`),
        el("td", { class: "actions" },
          el("button", { class: "ghost", onclick: () => { S.contestId = c.id; S.stationId = c.stations[0]?.id || null; save(); renderStationBar(); loadQsos(); renderScoreboard(); renderAdmin(); } }, t("wählen")), " ",
          el("a", { class: "button ghost", href: `/api/contests/${c.id}/export.zip`, download: 1, title: t("Alle Stationen/Bänder dieses Contests als EDI-Dateien") }, "ZIP"), " ",
          el("button", { class: "ghost", onclick: () => contestDialog(c) }, "✎"), " ",
          el("button", { class: "ghost", onclick: async () => { await api("PATCH", `/api/contests/${c.id}`, { archived: c.archived ? 0 : 1 }); } }, c.archived ? t("aktivieren") : t("archivieren")), " ",
          el("button", { class: "ghost danger", onclick: async () => { if (confirm(t("Contest „{name}“ mit allen Stationen und QSOs löschen?", c))) await api("DELETE", `/api/contests/${c.id}`); } }, "✕"))));
    }
    const c = contest();
    $("#admin-contest-name").textContent = c ? `– ${c.name}` : "";
    const sb = $("#admin-stations tbody"); sb.innerHTML = "";
    for (const s of c?.stations || []) {
      sb.append(el("tr", {},
        el("td", {}, el("b", {}, s.call), el("div", { class: "muted small" }, `ID ${s.id}`)), el("td", {}, s.locator), el("td", {}, s.band), el("td", {}, s.mode),
        el("td", { class: "muted small" }, `${t("Nr.")} ${pad3(s.serial_next)} · ${s.has_password ? "🔒" : t("offen")}`),
        el("td", { class: "actions" },
          el("button", { class: "ghost", onclick: () => { S.stationId = s.id; save(); renderStationBar(); loadQsos(); showView("fulllog"); setTimeout(() => runCheck(true), 300); } , title: t("EDI dieser Station") }, "EDI"), " ",
          el("a", { class: "button ghost", href: `/api/stations/${s.id}/export.adi`, download: 1 }, "ADIF"), " ",
          el("button", { class: "ghost", onclick: () => stationDialog(s) }, "✎"), " ",
          el("button", { class: "ghost", onclick: async () => { const v = prompt("Nächste Seriennummer:", s.serial_next); if (v && /^\d+$/.test(v)) await api("POST", `/api/stations/${s.id}/serial`, { start: Number(v) }); } }, t("Nr.")), " ",
          el("button", { class: "ghost danger", onclick: async () => { if (confirm(t("Station {call} mit allen QSOs löschen?", s))) await api("DELETE", `/api/stations/${s.id}`); } }, "✕"))));
    }
    const is = $("#imp-station"); is.innerHTML = "";
    S.contests.forEach((cc) => cc.stations.forEach((s) => is.append(el("option", { value: s.id }, `${cc.name} · ${s.call} ${s.band}`))));
    const inf = await GET("/api/info"); $("#cb-count").textContent = inf.callbook_count; $("#tile-url").value = inf.tile_url || "";
    try { const cfg = await GET("/api/settings"); $("#lookup-provider").value = cfg.lookup_provider; $("#lookup-user").value = cfg.lookup_user || ""; $("#lookup-pass").placeholder = cfg.lookup_pass_set ? t("Passwort (gespeichert)") : t("Passwort"); } catch (_) { /* */ }
    renderBackups(); renderCallbook();
  }
  $("#admin-login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try { S.adminToken = (await api("POST", "/api/admin/login", { password: $("#admin-pw").value })).token; save(); $("#admin-pw").value = ""; renderAdmin(); renderStationBar(); renderQsos(); toast(t("Als Admin angemeldet"), "ok"); } catch (err) { toast(err.message, "err"); }
  });
  $("#btn-backup").addEventListener("click", async () => {
    try { const r = await api("POST", "/api/backups"); toast(t("Gesichert: {name}", r), "ok"); renderBackups(); } catch (err) { toast(err.message, "err"); }
  });
  async function renderBackups() {
    const tb = $("#backup-list tbody"); tb.innerHTML = "";
    try {
      const r = await GET("/api/backups");
      $("#backup-info").textContent = t("Automatisch alle {min} Minuten (nur bei Änderungen) nach {dir}; beim Beenden zusätzlich. WAL + synchrones Schreiben: ein Stromausfall beschädigt die Datenbank nicht.", { min: r.interval_min, dir: r.dir });
      for (const b of r.backups) tb.append(el("tr", {}, el("td", {}, b.name), el("td", { class: "num muted small" }, `${Math.round(b.size / 1024)} KB`), el("td", { class: "muted small" }, `${fmtDate(b.ts_utc)} ${fmtTime(b.ts_utc)}`)));
      if (!r.backups.length) tb.append(el("tr", {}, el("td", { class: "muted" }, t("Noch keine Sicherung."))));
    } catch (_) { /* */ }
  }
  $("#btn-admin-logout").addEventListener("click", () => { S.adminToken = ""; save(); renderAdmin(); renderStationBar(); renderQsos(); });
  $("#admin-pw-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try { await api("POST", "/api/admin/password", { password: $("#admin-pw-new").value }); S.adminToken = (await api("POST", "/api/admin/login", { password: $("#admin-pw-new").value })).token; save(); $("#admin-pw-new").value = ""; toast(t("Admin-Passwort geändert"), "ok"); } catch (err) { toast(err.message, "err"); }
  });
  $("#btn-new-contest").addEventListener("click", () => contestDialog(null));
  $("#btn-new-station").addEventListener("click", () => { if (!contest()) return toast(t("Erst einen Contest anlegen/wählen"), "err"); stationDialog(null); });

  const toLocal = (ts) => (ts ? ts.slice(0, 16) : "");
  const fromLocal = (v) => (v ? v + ":00Z" : null);
  function contestDialog(c) {
    const box = modal(el("div", {}, el("h3", {}, c ? t("Contest bearbeiten") : t("Neuer Contest")),
      el("form", { id: "c-form", class: "stack" },
        lab(t("Name"), el("input", { id: "c-name", value: c?.name || "", required: 1, placeholder: t("z. B. DARC UKW-Contest Mai 2026") })),
        el("div", { class: "grid2" },
          lab(t("Beginn (UTC)"), el("input", { id: "c-start", type: "datetime-local", value: toLocal(c?.start_utc) })),
          lab(t("Ende (UTC)"), el("input", { id: "c-end", type: "datetime-local", value: toLocal(c?.end_utc) }))),
        lab(t("Notizen"), el("input", { id: "c-notes", value: c?.notes || "" })),
        el("div", { class: "row" }, el("button", { class: "primary" }, t("Speichern")), el("button", { type: "button", class: "ghost", "data-close": 1 }, t("Abbrechen"))))));
    box.querySelector("#c-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = { name: box.querySelector("#c-name").value, start_utc: fromLocal(box.querySelector("#c-start").value), end_utc: fromLocal(box.querySelector("#c-end").value), notes: box.querySelector("#c-notes").value };
      try {
        const r = c ? await api("PATCH", `/api/contests/${c.id}`, body) : await api("POST", "/api/contests", body);
        if (!c) { S.contestId = r.id; save(); }
        closeModal(); toast(t("Contest gespeichert"), "ok");
      } catch (err) { toast(err.message, "err"); }
    });
  }
  function stationDialog(s) {
    const info = s?.info || {};
    const prevInfo = !s ? (contest()?.stations[0]?.info || {}) : {};
    const box = modal(el("div", {}, el("h3", {}, s ? t("Station {call} bearbeiten", s) : t("Neue Station")),
      el("form", { id: "s-form", class: "stack" },
        el("div", { class: "grid2" },
          lab(t("Rufzeichen"), el("input", { id: "s-call", value: s?.call || "", required: 1, placeholder: "DN2LH/P" })),
          lab(t("Locator"), el("input", { id: "s-loc", value: s?.locator || prevInfo.__loc || "", required: 1, placeholder: "JO31AA" })),
          lab(t("Band"), el("select", { id: "s-band" }, BANDS.map((b) => el("option", { value: b, selected: (s?.band || "144MHz") === b ? 1 : null }, b)))),
          lab(t("Modus"), el("select", { id: "s-mode" }, ["SSB", "CW", "FM", "MIXED"].map((m) => el("option", { value: m, selected: (s?.mode || "SSB") === m ? 1 : null }, m)))),
          lab(s ? t("Neues Passwort (leer = unverändert)") : t("Stations-Passwort"), el("input", { id: "s-pw", type: "text", placeholder: t("für Operatoren") })),
          lab(t("Start-Seriennummer"), el("input", { id: "s-serial", type: "number", min: 1, value: s?.serial_next || 1 }))),
        el("details", {}, el("summary", { class: "muted" }, t("Angaben für die EDI-Abgabe (Standort, Verantwortlicher, Technik)")),
          el("div", { class: "grid2" }, INFO_FIELDS.map(([k, l]) => lab(l, el("input", { id: `i-${k}`, value: info[k] ?? prevInfo[k] ?? "" }))))),
        el("div", { class: "row" }, el("button", { class: "primary" }, t("Speichern")), el("button", { type: "button", class: "ghost", "data-close": 1 }, t("Abbrechen"))))));
    box.querySelector("#s-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const g = (id) => box.querySelector(id).value.trim();
      const infoOut = {}; INFO_FIELDS.forEach(([k]) => { infoOut[k] = g(`#i-${k}`); });
      const body = { call: g("#s-call"), locator: g("#s-loc"), band: g("#s-band"), mode: g("#s-mode"), info: infoOut, serial_next: Number(g("#s-serial")) };
      if (g("#s-pw") || !s) body.password = g("#s-pw");
      try {
        const r = s ? await api("PATCH", `/api/stations/${s.id}`, body) : await api("POST", `/api/contests/${S.contestId}/stations`, body);
        if (!s) { S.stationId = r.id; save(); }
        closeModal(); toast(t("Station gespeichert"), "ok");
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
    const out = $("#imp-result"); out.classList.remove("hidden"); out.textContent = t("Importiere …");
    try {
      const r = await api("POST", "/api/import", fd);
      out.textContent = `${t("Format")}: ${r.kind}\n${t("QSOs übernommen")}: ${r.qsos}\n${t("Call-Buch-Einträge")}: ${r.callbook}` + (r.station_id ? `\n${t("Neue Station #{id} angelegt", { id: r.station_id })}` : "") + (r.warnings.length ? `\n\n${t("Hinweise")}:\n${r.warnings.join("\n")}` : "");
      toast(t("Import abgeschlossen"), "ok");
      await loadContests(); renderAdmin();
    } catch (err) { out.textContent = "Fehler: " + err.message; toast(err.message, "err"); }
  });
  async function renderCallbook() {
    const tb = $("#cb-table tbody"); tb.innerHTML = "";
    try {
      const r = await GET(`/api/callbook?q=${encodeURIComponent($("#cb-search").value.trim())}&limit=300`);
      $("#cb-count").textContent = r.total;
      for (const c of r.rows) tb.append(el("tr", {},
        el("td", {}, el("b", {}, c.call)), el("td", {}, c.locator), el("td", { class: "muted small" }, c.name || ""),
        el("td", { class: "num muted small" }, c.qso_count ? `${c.qso_count}×` : ""), el("td", { class: "muted small" }, c.last_seen ? fmtDate(c.last_seen) : ""),
        el("td", { class: "actions" }, el("button", { class: "ghost", onclick: () => { $("#cb-call").value = c.call; $("#cb-loc").value = c.locator; $("#cb-name").value = c.name || ""; } }, "✎"), " ",
          el("button", { class: "ghost danger", onclick: async () => { if (confirm(t("{call} aus der Stationsdatenbank löschen?", c))) { await api("DELETE", `/api/callbook/${encodeURIComponent(c.call)}`); renderCallbook(); } } }, "✕"))));
      if (!r.rows.length) tb.append(el("tr", {}, el("td", { class: "muted" }, t("Keine Einträge."))));
    } catch (_) { /* */ }
  }
  let cbTimer; $("#cb-search").addEventListener("input", () => { clearTimeout(cbTimer); cbTimer = setTimeout(renderCallbook, 150); });
  $("#folder-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const files = Array.from($("#folder-files").files).filter((f) => /\.(mdb|txt|exp|edi|adi|adif|csv)$/i.test(f.name) && f.size < 50e6);
    if (!files.length) return toast(t("Keine passenden Dateien im Ordner"), "err");
    const fd = new FormData(); files.forEach((f) => fd.append("files", f, f.webkitRelativePath || f.name));
    const out = $("#folder-result"); out.classList.remove("hidden"); out.textContent = t("Importiere …") + ` (${files.length} ${t("Dateien")})`;
    try {
      const r = await api("POST", "/api/import/folder", fd);
      out.textContent = `${t("Contests angelegt")}: ${r.contests}\n${t("QSOs übernommen")}: ${r.qsos}\n${t("Call-Buch-Einträge")}: ${r.callbook}\n\n` +
        r.files.map((f) => `${f.file}: ${f.kind}, ${f.qsos} QSOs, ${f.imported} ${t("neu")}${f.note ? " – " + f.note : ""}`).join("\n") + (r.skipped.length ? `\n\n${t("Hinweise")}:\n${r.skipped.join("\n")}` : "");
      toast(t("Import abgeschlossen"), "ok"); await loadContests(); renderAdmin();
    } catch (err) { out.textContent = t("Fehler: ") + err.message; toast(err.message, "err"); }
  });
  $("#cb-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try { await api("POST", "/api/callbook", { call: $("#cb-call").value, locator: $("#cb-loc").value, name: $("#cb-name").value }); toast(t("Call gespeichert"), "ok"); $("#cb-call").value = $("#cb-loc").value = $("#cb-name").value = ""; renderCallbook(); } catch (err) { toast(err.message, "err"); }
  });

  boot().catch((e) => toast(t("Start fehlgeschlagen: ") + e.message, "err"));
})();
