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
    kst: { msgs: [], users: [], status: {}, tab: "local", dm: "", sid: null, unread: 0, unreadDm: 0, macros: [], seen: {} },
  };
  const POPUP = new URLSearchParams(location.search).get("popup") === "chat";
  if (POPUP) document.body.classList.add("popup");
  const BC = ("BroadcastChannel" in window) ? new BroadcastChannel("contestlogger") : null;
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
    box.innerHTML = ""; box.classList.remove("wide");
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
    $("#footer-text").textContent = `${S.info.app} ${S.info.version} · ${S.info.copyright}`;
    if (!S.info.admin_configured) await askSetup();
    if (!S.nick) await askNick();
    $("#nick-badge").textContent = S.nick;
    await loadContests();
    connectWs();
    loadChat();
    loadKst();
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
    last: {}, bootAt: Date.now(), quietUntil: 0,
    play(kind) {
      if (!this.on || POPUP) return;  // im ausgepoppten Chatfenster keine Töne – sonst klingt alles doppelt
      // Drossel: bei Nachrichtenschüben (z. B. Verlauf nach Neuverbinden, Import) nur ein Ton je Art pro 1,5 s,
      // und in den ersten Sekunden nach Seitenstart/Neuverbindung gar keine Hinweistöne
      const now = Date.now();
      if ((kind === "chat" || kind === "other") && (now - this.bootAt < 3000 || now < this.quietUntil)) return;
      const gap = kind === "chat" || kind === "other" ? 1500 : 250;
      if (now - (this.last[kind] || 0) < gap) return;
      this.last[kind] = now;
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
    if (S.kst.sid !== S.stationId && S.kst.sid !== undefined) loadKst();  // KST-Chat ist je Station
    if (S.chatContest !== undefined && S.chatContest !== S.contestId) loadChat();  // lokaler Chat ist je Contest
    if (S.opnoteSid !== S.stationId) { S.opnoteSid = S.stationId; loadOpnote(); }
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
      $("#hint-info").textContent = unlocked ? "" : t("Station ist nur im Lesemodus. Zum Loggen mit Stations-Passwort freischalten.");
    } else {
      $("#station-meta").textContent = "";
      $("#station-state").textContent = S.contests.length ? "" : t("Lege unter „Verwaltung“ einen Contest und eine Station an.");
      $("#qso-form").querySelectorAll("input,button").forEach((i) => { i.disabled = true; });
    }
    renderMacroBar();
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
    if (res.lookup) list.append(el("div", { class: "muted small" }, res.lookup.provider === "none" ? t("Online-Abgleich (HamQTH/QRZ) aus – in der Verwaltung einrichten, dann werden Rufzeichen und Locator automatisch gegengeprüft.") : t("Online-Abgleich: {n} Rufzeichen jetzt bei {p} nachgeschlagen, bereits geprüfte werden nicht erneut abgefragt.", { n: res.lookup.checked_now, p: res.lookup.provider === "hamqth" ? "HamQTH" : "QRZ" })));
    const dl = (force) => { window.location.href = `/api/stations/${st.id}/export.edi?nick=${encodeURIComponent(S.nick)}${force ? "&force=1" : ""}`; };
    const buttons = el("div", { class: "row" });
    if (res.ok) buttons.append(el("button", { class: "primary", onclick: () => { closeModal(); dl(false); } }, t("EDI herunterladen")));
    else if (S.adminToken) buttons.append(el("button", { class: "ghost danger", onclick: () => { if (confirm(t("Mit Fehlern exportieren? Der Auswerter wird diese QSOs wahrscheinlich streichen."))) { closeModal(); dlForce(); } } }, t("Trotzdem exportieren (Admin)")));
    buttons.append(el("button", { type: "button", class: "ghost", "data-close": 1 }, t("Schließen")));
    const dlForce = async () => {
      const r = await fetch(`/api/stations/${st.id}/export.edi?force=1&nick=${encodeURIComponent(S.nick)}`, { headers: { "X-Admin-Token": S.adminToken } });
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

  const coreOf = (call) => (call || "").trim().toUpperCase().replace(/-.*$/, "").split("/").filter((p) => !["P", "M", "MM", "AM", "QRP"].includes(p) && !/^\d+$/.test(p)).sort((a, b) => b.length - a.length)[0] || "";
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
      if (r && r.locator) { setAutoLocator(r.locator); showAltLocators(r.locator, r.alt_locators || []); if (r.source !== "local") toast(`${r.call}: ${r.locator}${r.name ? " · " + r.name : ""} (${r.source === "hamqth" ? "HamQTH" : "QRZ"})`); }
      else { showAltLocators("", []); if (r && r.source === "error") toast(r.error, "err"); }
    } catch (_) { /* */ }
  }
  function showAltLocators(main, alts) {
    // Mehrere bekannte Standorte (z. B. Portabel-QTHs): als anklickbare Auswahl unter dem Formular
    const box = $("#hint-altloc"); box.innerHTML = "";
    const all = [main, ...alts].filter((x, i, a) => x && a.indexOf(x) === i);
    if (all.length < 2) return box.classList.add("hidden");
    box.append(t("Standorte") + ": ");
    for (const l of all) box.append(el("button", { type: "button", class: "ghost small" + (l === F.loc.value.trim() ? " active" : ""), onclick: () => { F.loc.value = l; S.locAuto = false; F.loc.classList.remove("auto"); updateHints(); showAltLocators(main, alts); F.loc.focus(); } }, l), " ");
    box.classList.remove("hidden");
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
    if (call.length < 3) $("#hint-altloc").classList.add("hidden");
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

  // ------------------------------------------------------------ Operator-Fenster (zweiter Monitor)
  $("#btn-operator").addEventListener("click", () => { if (!S.stationId) return toast(t("Keine Station gewählt"), "err"); window.open(`/operator?station=${S.stationId}`, "cloperator", "width=1000,height=760,resizable=yes"); });
  function sendOpnote(text) { if (S.ws?.readyState === 1 && S.stationId) S.ws.send(JSON.stringify({ type: "opnote", station_id: S.stationId, text })); }
  $("#btn-opnote").addEventListener("click", () => { sendOpnote($("#opnote").value.trim()); toast(t("Hinweis an das Operator-Fenster gesendet"), "ok"); });
  $("#opnote").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); $("#btn-opnote").click(); } });
  $("#btn-opnote-clear").addEventListener("click", () => { $("#opnote").value = ""; sendOpnote(""); });
  async function loadOpnote() { try { $("#opnote").value = S.stationId ? (await GET(`/api/stations/${S.stationId}/opnote`)).text : ""; } catch (_) { /* */ } }
  // Live-Eingabe an das Operator-Fenster (gedrosselt, nur bei Änderung)
  let typingTimer, typingLast = "";
  function sendTyping() {
    clearTimeout(typingTimer);
    typingTimer = setTimeout(() => {
      if (!S.stationId || S.ws?.readyState !== 1) return;
      const data = { call: F.call.value.trim(), rs: F.rs.value.trim(), rr: F.rr.value.trim(), nr: F.nr.value.trim(), loc: F.loc.value.trim(), serial: F.ns.value, cmt: F.cmt.value.trim(),
        geo: $("#hint-geo").textContent, dupe: $("#hint-dupe").classList.contains("hidden") ? "" : $("#hint-dupe").textContent, editing: !!S.editingId };
      const key = JSON.stringify(data); if (key === typingLast) return; typingLast = key;
      S.ws.send(JSON.stringify({ type: "typing", station_id: S.stationId, data }));
    }, 150);
  }
  order.forEach((inp) => inp.addEventListener("input", sendTyping));
  const _mo = new MutationObserver(sendTyping); _mo.observe($("#hint-geo"), { childList: true, characterData: true, subtree: true }); _mo.observe($("#hint-dupe"), { attributes: true, childList: true, subtree: true });
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
  const MACRO_DEFAULTS = { F2: "CQ Contest {mycall} {mycall} Contest", F3: "{call}", F4: "{rst} {nr} {myloc}", F5: "QRZ? {mycall}", F6: "{mycall}", F7: "TU {mycall}", F8: "AGN? NR?" };  // F1 = Hilfe
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
    if (/^F[2-8]$/.test(e.key)) { e.preventDefault(); if (station()) fireMacro(e.key); }
  });
  if (localStorage.getItem("cl.macrobar") === "1") $("#macro-bar").classList.remove("hidden");

  // ------------------------------------------------------------ Hilfe (F1 / „?“ im Kopf)
  function helpDialog() {
    const K = (keys, what) => el("tr", {}, el("td", { class: "keys" }, ...keys.map((k) => el("kbd", {}, k))), el("td", {}, what));
    const H = (title, ...rows) => [el("h4", {}, title), el("table", { class: "help-table" }, el("tbody", {}, ...rows))];
    const P = (text) => el("p", { class: "muted small" }, text);
    const box = modal(el("div", { class: "help" }, el("h3", {}, t("Hilfe und Tastenkürzel")),
      ...H(t("Loggen (Eingabeformular)"),
        K(["Enter"], t("Weiter zum nächsten Feld. Stehen Rufzeichen und Locator, wird im Feld Nr erh., Locator oder Kommentar das QSO geloggt.")),
        K(["Leertaste"], t("Springt Rufzeichen → Nr erh. → Locator → Kommentar → Rufzeichen (im Rufzeichenfeld wird dabei die Stationsdatenbank abgefragt). Im Kommentar bleibt die Leertaste ein Leerzeichen.")),
        K(["↑", "↓"], t("In der Vorschlagsliste unter dem Rufzeichen blättern.")),
        K(["Enter", "Tab"], t("Markierten Vorschlag übernehmen (Rufzeichen und Locator).")),
        K(["Esc"], t("Formular leeren (bzw. offenes Fenster schließen); laufende CW-Ausgabe stoppen.")),
        K(["F1"], t("Diese Hilfe.")),
        K(["F2", "…", "F8"], t("Sprachbausteine F2–F8 (F1 ist die Hilfe): Text wird groß eingeblendet und, wenn eine CAT-Bridge mit CW läuft, als CW gesendet. Platzhalter: {mycall} {myloc} {call} {rst} {nr} {loc} {band} {nick}. Bearbeiten über ✎ in der Makroleiste.")),
        K(["F9"], t("Makroleiste ein-/ausblenden (Übersicht aller Sprachbausteine mit ausgefülltem Text).")),
        K(["Klick auf Standort"], t("Hat ein Rufzeichen mehrere bekannte Locator, erscheinen sie unter dem Formular zur Auswahl."))),
      ...H(t("Chat, KST und DM"),
        K(["Enter"], t("Nachricht senden (Chat, KST-Tab, DM-Gespräch).")),
        K(["Klick auf Rufzeichen"], t("Im KST-Tab, im DM-Gespräch oder in der Nutzerliste: Rufzeichen und Locator in den Logger übernehmen.")),
        K(["DM"], t("Knopf an einer KST-Nachricht: Gespräch mit dem Absender öffnen. Die Eingabe geht dann nur an diesen Kontakt.")),
        K(["↓ Neueste"], t("Erscheint, wenn du hochgescrollt hast: springt ans Ende. Solange du oben bist, zieht nichts nach unten.")),
        K(["↗"], t("Chat als eigenes Fenster ausklinken (z. B. für den zweiten Bildschirm). Töne kommen nur aus dem Hauptfenster.")),
        K(["Rundruf"], t("Noch nicht gearbeitete KST-Nutzer im Umkreis gezielt anschreiben: Liste laden, „Nächste →“ dreht die Auswahl weiter, bereits Angeschriebene werden übersprungen. Eigene Texte lassen sich speichern.")),
        K(["🖥 Operator"], t("Operator-Fenster für den zweiten Monitor: zeigt live Rufzeichen, Nummern, RST, Locator, Entfernung/Richtung, eine Dupe-Warnung, den Hinweis des Loggers (Feld über der Karte, z. B. Frequenz) und die letzten QSOs. Läuft auch auf einem anderen PC im Netz über /operator?station=ID."))),
      ...H(t("Allgemein"),
        K(["Loggen", "Log", "Statistik", "Verwaltung"], t("Reiter oben: Eingabe, komplettes Log mit Suche und Log-Prüfung, Auswertung, Verwaltung (Admin).")),
        K(["Contest / Station"], t("Auswahl in der Leiste unter dem Kopf. Jede Station hat eigenes Rufzeichen, Band, Seriennummer und eigenen KST-Chat.")),
        K(["🔔"], t("Töne an/aus: Pling beim QSO, Brummen bei Dupe, Ping bei Chat/DM/„an mich“, Tick wenn eine andere Station loggt.")),
        K(["📱"], t("Adresse des Servers als QR-Code für Handy oder Tablet.")),
        K(["◐"], t("Hell/Dunkel umschalten.")),
        K([t("Sprache")], t("Umschalten der Oberfläche; eigene Übersetzungen über die Verwaltung."))),
      P(t("Export und Abgabe: in der Verwaltung unter „Export / Abgabe“ – EDI je Station/Band (mit Log-Prüfung), ADIF, CSV oder alle Bänder als EDI-ZIP. Jede Änderung steht im Aktionsprotokoll.")),
      el("div", { class: "row" }, el("span", { class: "muted small grow" }, `${S.info.app || "ContestLogger"} ${S.info.version || ""} · ${S.info.copyright || ""}`), el("button", { type: "button", class: "ghost", "data-close": 1 }, t("Schließen")))));
    box.classList.add("wide");
  }
  $("#help-btn").addEventListener("click", helpDialog);
  document.addEventListener("keydown", (e) => { if (e.key === "F1") { e.preventDefault(); if ($("#modal").classList.contains("hidden")) helpDialog(); } });

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
    const tb = $("#scoreboard tbody"); if (!tb) { if (S.contestId) { try { (await GET(`/api/contests/${S.contestId}/scoreboard`)).forEach((r) => { if (r.rig) S.rig[r.id] = r.rig; }); } catch (_) { /* */ } } return; }
    tb.innerHTML = "";
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
    ws.onopen = () => { $("#conn").classList.add("on"); Sound.quietUntil = Date.now() + 3000; sendStatus(); };
    ws.onclose = () => { $("#conn").classList.remove("on"); setTimeout(connectWs, 2000); };
    ws.onmessage = async (ev) => {
      const m = JSON.parse(ev.data);
      if (m.type === "chat") { if ((m.msg.contest_id || 0) === (S.contestId || 0)) { appendChat(m.msg); if (m.msg.nick !== S.nick) { Sound.play("chat"); if (S.kst.tab !== "local" || POPUP === false && document.hidden) { S.chatUnread = (S.chatUnread || 0) + 1; renderKstBadges(); } } } }
      else if (m.type?.startsWith("kst") && m.station_id !== S.stationId) { /* KST-Ereignis einer anderen Station */ }
      else if (m.type === "kst") {
        S.kst.msgs.push(m.msg); S.kst.msgs.splice(0, S.kst.msgs.length - 800);
        const incoming = m.msg.to_me && !m.msg.own;
        if (S.kst.tab === "local") S.kst.unread++;
        if (incoming) {
          if (!(S.kst.tab === "dm" && S.kst.dm && coreOf(S.kst.dm) === coreOf(m.msg.call))) S.kst.unreadDm++;
          Sound.play("chat");
          if (Date.now() - (S.kst.lastToast || 0) > 1500) { S.kst.lastToast = Date.now(); toast(`KST ${m.msg.call}: ${m.msg.text}`.slice(0, 120)); }
        }
        // Eigene gerichtete Nachricht (auch aus einem anderen KST-Client mit demselben Login): DM-Gespräch dazu öffnen,
        // damit die Unterhaltung hier sichtbar weitergeht. Eingehende DM ohne offenes Gespräch: Kontakt vorwählen.
        // … aber nicht, wenn hier gerade ein anderes Gespräch aktiv ist (Text in der Eingabe oder Nachrichten in den
        // letzten 3 Minuten) – sonst würde jede DM eines anderen Operators derselben Station das Fenster umschalten.
        const lastTs = S.kst.dm ? (S.kst.msgs.filter((x) => coreOf(x.own ? x.to : x.call) === coreOf(S.kst.dm)).pop()?.ts || "") : "";
        const busy = !!$("#kst-input").value.trim() || (lastTs && Date.now() - Date.parse(lastTs) < 180000);
        if (m.msg.own && m.msg.to && coreOf(m.msg.to) !== coreOf(S.kst.dm) && !busy) { S.kst.dm = m.msg.to; if (S.kst.tab !== "local") setChatTab("dm"); }
        else if (incoming && !S.kst.dm) S.kst.dm = m.msg.call;
        renderKst();
        if (m.msg.own) { Scroll.toBottom($("#kst-log")); Scroll.toBottom($("#kst-dm-msgs")); }  // eigene Nachricht: immer ans Ende
      }
      else if (m.type === "kst_users") { S.kst.users = m.users; renderKstUsers(); renderKst(); }
      else if (m.type === "kst_status") { S.kst.status = { ...S.kst.status, state: m.state, error: m.error }; renderKstStatus(); }
      else if (m.type === "kst_broadcast") {
        const s_ = $("#rr-status"); if (s_) s_.textContent = m.done < m.total ? `${m.done}/${m.total} ${t("gesendet")} – ${t("zuletzt")} ${m.call} …` : `${t("fertig")}: ${m.total} ${t("gesendet")}`;
        const sent = $("#rr-sent"); if (sent) sent.append(el("span", { class: "tag me" }, `✓ ${m.call}`), " ");
        const cb = $(`#rr-list .rr-sel[value="${m.call}"]`); if (cb) { cb.checked = false; cb.closest("label").classList.add("sent"); }
      }
      else if (m.type === "rig") { S.rig[m.station_id] = { freq: m.freq, mode: m.mode, ts: m.ts }; if (m.station_id === S.stationId) renderStationBar(); renderScoreboard(); }
      else if (m.type === "presence") renderPresence(m.users);
      else if (m.type === "opnote") { if (m.station_id === S.stationId && m.by !== S.nick) $("#opnote").value = m.text; }
      else if (m.type === "typing") { /* nur für das Operator-Fenster */ }
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
  // Scrollverhalten der Chat-Listen: wer hochgescrollt hat, bleibt oben (kein Zwangsscroll); ein Knopf „↓ Neueste“ führt ans Ende
  const Scroll = {
    atBottom: (el) => el.scrollTop + el.clientHeight >= el.scrollHeight - 30,
    btn: (el) => el.parentElement?.querySelector(".jump-down"),
    update(el) { const b = this.btn(el); if (b) b.classList.toggle("hidden", this.atBottom(el) || el.scrollHeight <= el.clientHeight); },
    toBottom(el) { el.scrollTop = el.scrollHeight; this.update(el); },
    // vor dem Neuaufbau merken, danach wiederherstellen: unten bleibt unten, oben bleibt an derselben Stelle
    snapshot(el) { return { bottom: this.atBottom(el) || !el.childElementCount, top: el.scrollTop }; },
    restore(el, snap, force) { if (force || snap.bottom) el.scrollTop = el.scrollHeight; else el.scrollTop = snap.top; this.update(el); },
  };
  $$(".logwrap").forEach((w) => { const log = w.querySelector(".chat-log"); log.addEventListener("scroll", () => Scroll.update(log)); w.querySelector(".jump-down").addEventListener("click", () => Scroll.toBottom(log)); });
  async function loadChat() {
    const log = $("#chat-log"); log.innerHTML = ""; S.chatContest = S.contestId;
    try { (await GET(`/api/chat?contest_id=${S.contestId || 0}`)).forEach(appendChat); } catch (_) { /* */ }
    Scroll.toBottom(log);
  }
  function appendChat(m) {
    const log = $("#chat-log"); const snap = Scroll.snapshot(log);
    log.append(el("div", { class: "m" }, el("span", { class: "t" }, fmtTime(m.ts_utc)), el("span", { class: "n" }, m.nick + ": "), m.text));
    Scroll.restore(log, snap, m.nick === S.nick);
  }
  $("#chat-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const t = $("#chat-input").value.trim();
    if (t && S.ws?.readyState === 1) { S.ws.send(JSON.stringify({ type: "chat", text: t, contest_id: S.contestId || 0 })); $("#chat-input").value = ""; }
  });

  // ------------------------------------------------------------ Chat-Reiter, Popup, ON4KST
  $$(".chat-tabs button").forEach((b) => b.addEventListener("click", () => setChatTab(b.dataset.ctab)));
  function setChatTab(tab) {
    S.kst.tab = tab; localStorage.setItem("cl.chattab", tab);
    $$(".chat-tabs button").forEach((b) => b.classList.toggle("active", b.dataset.ctab === tab));
    $("#ctab-local").classList.toggle("active", tab === "local");
    $("#ctab-kst").classList.toggle("active", tab !== "local");
    if (tab !== "local") { S.kst.unread = 0; if (tab === "dm") S.kst.unreadDm = 0; renderKst(); $("#kst-input").focus(); }
    else S.chatUnread = 0;
    // beim Reiterwechsel immer ans Ende (der Bereich war beim Aufbau noch unsichtbar, Scrollposition daher 0)
    Scroll.toBottom($(tab === "local" ? "#chat-log" : tab === "dm" ? "#kst-dm-msgs" : "#kst-log"));
    renderKstBadges();
  }
  function renderKstBadges() {
    const b = $("#kst-badge");
    b.textContent = S.kst.unread; b.classList.toggle("hidden", !S.kst.unread);
    const bc = $("#chat-badge"); bc.textContent = S.chatUnread || 0; bc.classList.toggle("hidden", !S.chatUnread);
    const nDm = dmConversations().reduce((a, c) => a + c.unread, 0);
    const bd = $("#kst-dm-badge"); bd.textContent = nDm; bd.classList.toggle("hidden", !nDm);
  }
  $("#btn-chat-pop").addEventListener("click", () => window.open(`${location.pathname}?popup=chat`, "clchat", "width=480,height=780,resizable=yes"));
  if (POPUP) setChatTab(localStorage.getItem("cl.chattab") || "kst");
  const sidQ = () => `station_id=${S.stationId || 0}`;
  async function loadKst() {
    S.kst.sid = S.stationId; S.kst.msgs = []; S.kst.users = []; S.kst.status = {}; S.kst.seen = {};
    try {
      S.kst.seen = await GET(`/api/kst/seen?${sidQ()}`);
      S.kst.status = await GET(`/api/kst/status?${sidQ()}`);
      S.kst.macros = S.kst.status.macros || [];
      S.kst.msgs = await GET(`/api/kst/messages?${sidQ()}&limit=300`);
      S.kst.users = await GET(`/api/kst/users?${sidQ()}&my=${station()?.locator || ""}`);
    } catch (_) { /* */ }
    renderKstStatus(); renderKstUsers(); renderKst(); renderKstMacros();
  }
  function renderKstStatus() {
    const st = S.kst.status || {};
    const el_ = $("#kst-state");
    el_.textContent = `KST: ${st.state || "aus"}${st.error ? " – " + st.error : ""}`;
    el_.className = "tag " + (st.state === "verbunden" ? "me" : "");
    $("#kst-room").textContent = st.state === "verbunden" ? `${st.user} · ${st.room_name || st.room}` : (st.configured ? (st.user || "") : t("KST-Zugang bei der Station eintragen (Verwaltung)"));
    $("#kst-input").disabled = st.state !== "verbunden";
    const a = $("#kst-admin-state"); if (a) a.textContent = `${st.state || "aus"}${st.error ? " – " + st.error : ""}`;
  }
  const kstUser = (call) => S.kst.users.find((u) => u.call === call) || S.kst.users.find((u) => coreOf(u.call) === coreOf(call));
  function renderKstUsers() {
    const box = $("#kst-users"); box.innerHTML = "";
    const my = station()?.locator;
    for (const u of S.kst.users) {
      const km = u.km ?? (my && u.locator ? null : null);
      box.append(el("span", { class: "u" + (u.away ? " away" : ""), title: `${u.name || ""} ${u.locator || ""}`, onclick: () => fillFromKst(u.call, u.locator) },
        u.call, el("small", {}, `${u.locator || "?"}${u.km != null ? ` ${u.km}km ${u.bearing}°` : ""}`)));
    }
    if (!S.kst.users.length) box.append(el("span", { class: "muted small" }, t("Keine Nutzerliste – „Nutzer“ drücken (max. 1 Abfrage/Minute).")));
  }
  $("#btn-kst-users").addEventListener("click", async () => {
    $("#kst-users").classList.toggle("hidden");
    if (!$("#kst-users").classList.contains("hidden")) { try { S.kst.users = await GET(`/api/kst/users?${sidQ()}&my=${station()?.locator || ""}`); renderKstUsers(); if (!S.kst.users.length) await api("POST", "/api/kst/refresh_users", { station_id: S.stationId }); } catch (_) { /* */ } }
  });
  function fillFromKst(call, locator) {
    const payload = { type: "fill", call, locator: locator || "" };
    if (POPUP && BC) { BC.postMessage(payload); toast(t("{call} an den Logger übergeben", { call }), "ok"); return; }
    applyFill(payload);
  }
  function applyFill(p) {
    showView("log");
    F.call.value = p.call; S.locAuto = false; F.loc.classList.remove("auto");
    if (p.locator) { F.loc.value = p.locator; S.locAuto = true; F.loc.classList.add("auto"); } else F.loc.value = "";
    updateHints(); if (!p.locator) lookupCall(); F.nr.focus();
  }
  if (BC && !POPUP) BC.onmessage = (ev) => { if (ev.data?.type === "fill") applyFill(ev.data); };
  function dmConversations() {
    const conv = {};
    for (const m of S.kst.msgs) {
      const partner = m.own ? coreOf(m.to) : (m.to_me ? coreOf(m.call) : "");
      if (!partner) continue;
      const c = conv[partner] || (conv[partner] = { call: m.own ? m.to : m.call, last: m, unread: 0 });
      c.last = m; if (!m.own) c.call = m.call;
      if (!m.own && m.ts > (S.kst.seen[partner] || "")) c.unread++;  // gelesen = bis zur zuletzt angezeigten Nachricht
    }
    return Object.values(conv).sort((a, b) => (b.last.ts || "").localeCompare(a.last.ts || ""));
  }
  function renderDmList() {
    const box = $("#kst-dm-list"); box.innerHTML = "";
    const list = dmConversations();
    if (S.kst.dm && !list.find((c) => coreOf(c.call) === coreOf(S.kst.dm))) list.unshift({ call: S.kst.dm, last: { text: "", time: "" }, unread: 0 });
    for (const c of list) box.append(el("div", { class: "dm" + (S.kst.dm && coreOf(c.call) === coreOf(S.kst.dm) ? " active" : ""), onclick: () => setDm(c.call) },
      el("b", {}, c.call, c.unread ? el("span", { class: "new" }, c.unread) : null),
      el("span", { class: "snip" }, `${c.last.own ? "→ " : ""}${c.last.text}`), el("span", { class: "t" }, c.last.time)));
    if (!list.length) box.append(el("div", { class: "muted small", style: "padding:8px" }, t("Noch keine Kontakte – „+“ oder DM an einer Nachricht.")));
  }
  function kstFiltered() {
    const my = S.kst.msgs;
    if (S.kst.tab === "dm" && S.kst.dm) { const c = coreOf(S.kst.dm); return my.filter((m) => (m.own ? coreOf(m.to) === c : (m.to_me && coreOf(m.call) === c))); }
    return my;
  }
  function renderKst() {
    const log = $("#kst-log"); const snap = Scroll.snapshot(log);
    log.innerHTML = "";
    const list = kstFiltered().slice(-400);
    for (const m of list) {
      const u = kstUser(m.call);
      log.append(el("div", { class: "m" + (m.to_me ? " me" : "") + (m.own ? " own" : "") },
        el("span", { class: "t" }, m.time),
        el("span", { class: "c", title: (u?.locator || m.locator || "") + " " + (m.name || ""), onclick: () => fillFromKst(m.call, u?.locator || m.locator) }, m.call),
        m.to ? el("span", { class: "to" }, `(${m.to})`) : null,
        el("span", { class: "txt" }, m.text),
        el("span", { class: "act" }, el("button", { class: "ghost", title: "DM", onclick: () => setDm(m.call) }, "DM"))));
    }
    if (!list.length) log.append(el("div", { class: "sys" }, t("Keine Nachrichten.")));
    Scroll.restore(log, snap, false);
    const dmMode = S.kst.tab === "dm";
    $("#kst-dm-pane").classList.toggle("hidden", !dmMode);
    $("#kst-log-wrap").classList.toggle("hidden", dmMode);
    if (dmMode) {
      if (S.kst.dm) { const lastIn = [...list].reverse().find((m) => !m.own); const k = coreOf(S.kst.dm);
        if (lastIn && (S.kst.seen[k] || "") < lastIn.ts) { S.kst.seen[k] = lastIn.ts; api("POST", "/api/kst/seen", { station_id: S.stationId, partner: k, ts: lastIn.ts }).catch(() => {}); } }
      renderDmList();
      const msgs = $("#kst-dm-msgs"); const dmSnap = Scroll.snapshot(msgs); const dmChanged = S.kst.dmShown !== S.kst.dm; S.kst.dmShown = S.kst.dm; msgs.innerHTML = "";
      const u = S.kst.dm ? kstUser(S.kst.dm) : null;
      $("#kst-dm-head").innerHTML = "";
      if (S.kst.dm) {
        const dmLoc = u?.locator || list.find((m) => !m.own && m.locator)?.locator || "";
        $("#kst-dm-head").append(el("b", { class: "c", title: t("ins Log übernehmen"), onclick: () => fillFromKst(S.kst.dm, dmLoc) }, S.kst.dm), ` ${u?.name || ""} ${dmLoc}${u?.km != null ? ` · ${u.km} km ${u.bearing}°` : ""}`,
          el("button", { type: "button", class: "ghost small", style: "margin-left:auto", onclick: () => fillFromKst(S.kst.dm, dmLoc) }, "→ " + t("Log")));
        for (const m of list) msgs.append(el("div", { class: "m" + (m.own ? " own" : "") }, el("span", { class: "t" }, m.time),
          m.own ? el("span", { class: "c" }, t("ich")) : el("span", { class: "c", title: t("ins Log übernehmen"), onclick: () => fillFromKst(m.call, m.locator || dmLoc) }, m.call), el("span", { class: "txt" }, m.text)));
        if (!list.length) msgs.append(el("div", { class: "sys" }, t("Noch keine Nachrichten in diesem Gespräch.")));
        Scroll.restore(msgs, dmSnap, dmChanged);
      } else $("#kst-dm-head").textContent = t("Kontakt wählen");
      $("#kst-input").placeholder = S.kst.dm ? t("Nachricht an {call} …", { call: S.kst.dm }) : t("Erst Kontakt wählen");
    } else $("#kst-input").placeholder = t("Nachricht an alle im KST-Chat …");
    renderKstBadges();
  }
  function setDm(call) { S.kst.dm = call; if (S.kst.tab !== "dm") setChatTab("dm"); renderKst(); $("#kst-input").focus(); }
  $("#btn-dm-new").addEventListener("click", () => { const c = (prompt(t("Rufzeichen für neues Gespräch:")) || "").trim().toUpperCase(); if (c) setDm(c); });
  $("#kst-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    let text = $("#kst-input").value.trim(); if (!text) return;
    if (S.kst.tab === "dm") { if (!S.kst.dm) return toast(t("Erst Kontakt wählen"), "err"); if (!text.startsWith("/")) text = `/CQ ${S.kst.dm} ${text}`; }
    try { await api("POST", "/api/kst/send", { text, station_id: S.stationId }); $("#kst-input").value = ""; } catch (err) { toast(err.message, "err"); }
  });
  // Ziel nur im DM-Reiter – im allgemeinen KST-Reiter gehen Texte an alle
  function kstTarget() { return (S.kst.tab === "dm" && S.kst.dm) || ""; }
  function expandKst(text) {
    const st = station() || {}; const call = kstTarget(); const u = call ? kstUser(call) : null;
    return text.replace(/\{(\w+)\}/g, (_, k) => ({ call, name: u?.name?.split(" ")[0] || "", loc: u?.locator || "", mycall: st.call || "", myloc: st.locator || "", band: (st.band || "").replace("MHz", " MHz"), nick: S.nick })[k] ?? `{${k}}`);
  }
  function renderKstMacros() {
    const box = $("#kst-macros"); box.innerHTML = "";
    for (const m of S.kst.macros) box.append(el("button", { type: "button", class: "ghost", title: m.text, onclick: async () => {
      let text = expandKst(m.text).replace(/\s{2,}/g, " ").trim();
      if (S.kst.tab === "dm") { if (!S.kst.dm) return toast(t("Erst Kontakt wählen"), "err"); if (!text.startsWith("/")) text = `/CQ ${S.kst.dm} ${text}`; }
      try { await api("POST", "/api/kst/send", { text, station_id: S.stationId }); } catch (err) { toast(err.message, "err"); }
    } }, m.label));
    box.append(el("button", { type: "button", class: "ghost small", onclick: kstMacroEditor }, "✎"));
  }
  function kstMacroEditor() {
    const rows = S.kst.macros.length ? S.kst.macros : [{ label: "", text: "" }];
    const box = modal(el("div", {}, el("h3", {}, t("KST-Textbausteine")),
      el("p", { class: "muted small" }, t("Im KST-Reiter gehen die Texte an alle (keine Adressierung). Im DM-Reiter gehen sie an den offenen Kontakt; dort gelten {call} {name} {loc}. Immer: {mycall} {myloc} {band}. Gilt für alle Operatoren.")),
      el("form", { id: "kst-macro-form", class: "stack" },
        el("div", { id: "kst-macro-rows", class: "stack" }, rows.map((m) => macroRow(m))),
        el("div", { class: "row" }, el("button", { class: "primary" }, t("Speichern")), el("button", { type: "button", class: "ghost", onclick: () => $("#kst-macro-rows").append(macroRow({ label: "", text: "" })) }, "+"), el("button", { type: "button", class: "ghost", "data-close": 1 }, t("Abbrechen"))))));
    function macroRow(m) { return el("div", { class: "row" }, el("input", { class: "km-label", value: m.label, placeholder: t("Knopf"), style: "width:90px" }), el("input", { class: "km-text", value: m.text, placeholder: "/CQ {call} …", style: "flex:1" }), el("button", { type: "button", class: "ghost danger", onclick: (e) => e.target.closest(".row").remove() }, "✕")); }
    box.querySelector("#kst-macro-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const out = $$("#kst-macro-rows .row").map((r) => ({ label: r.querySelector(".km-label").value.trim(), text: r.querySelector(".km-text").value.trim() })).filter((m) => m.label && m.text);
      try { await api("POST", "/api/settings", { kst_macros: out }); S.kst.macros = out; renderKstMacros(); closeModal(); toast(t("Gespeichert"), "ok"); } catch (err) { toast(err.message, "err"); }
    });
  }
  // Rundruf: Nutzer im Umkreis anschreiben, die noch nicht im Log sind
  $("#btn-kst-rundruf").addEventListener("click", rundrufDialog);
  async function rundrufDialog() {
    const st = station(); if (!st) return toast(t("Keine Station gewählt"), "err");
    const box = modal(el("div", {}, el("h3", {}, t("Rundruf – noch nicht gearbeitete Stationen anschreiben")),
      el("p", { class: "muted small" }, t("KST-Nutzer mit Locator im Umkreis von {loc}, die in diesem Log noch fehlen und von dieser Station noch keine Nachricht bekommen haben. Jeder Empfänger bekommt eine eigene /CQ-Nachricht, gesendet mit 2 s Abstand.", { loc: st.locator })),
      el("div", { class: "row rr-top" },
        lab(t("Umkreis km"), el("input", { id: "rr-km", type: "number", value: localStorage.getItem("cl.rr.km") || 300, min: 10, max: 2000, style: "width:90px" })),
        lab(t("max. Anzahl"), el("input", { id: "rr-n", type: "number", value: localStorage.getItem("cl.rr.n") || 10, min: 1, max: 60, style: "width:80px" })),
        el("label", { class: "check" }, el("input", { id: "rr-away", type: "checkbox" }), t("abwesende (Klammer) auch")),
        el("button", { type: "button", class: "ghost", onclick: loadCands }, t("Liste laden")),
        el("button", { type: "button", class: "ghost", id: "rr-next", title: t("Auswahl weiterdrehen: die nächsten noch nicht angeschriebenen Kandidaten ankreuzen") }, t("Nächste →"))),
      el("div", { class: "row rr-top" },
        lab(t("Gespeicherte Rundruf-Texte"), el("select", { id: "rr-tpl", style: "max-width:420px", onchange: (e) => { if (e.target.value) box.querySelector("#rr-text").value = e.target.value; } }, el("option", { value: "" }, t("– Text wählen –")))),
        el("button", { type: "button", class: "ghost", title: t("aktuellen Text in die Liste aufnehmen"), onclick: () => saveTexts([...rrTexts.filter((x) => x !== box.querySelector("#rr-text").value.trim()), box.querySelector("#rr-text").value.trim()]) }, t("Text speichern")),
        el("button", { type: "button", class: "ghost danger", title: t("gewählten Text aus der Liste entfernen"), onclick: () => { const v = box.querySelector("#rr-tpl").value; if (v) saveTexts(rrTexts.filter((x) => x !== v)); } }, "✕")),
      lab(t("Text (Platzhalter {call} {name} {loc} {mycall} {myloc} {band}) – jeder Empfänger bekommt ihn als /CQ-Nachricht"), el("input", { id: "rr-text", value: localStorage.getItem("cl.rr.text") || "" })),
      el("div", { id: "rr-list", class: "rundruf-list stack" }, el("div", { class: "muted small" }, "…")),
      el("div", { class: "row rr-bottom" }, el("button", { type: "button", class: "primary", id: "rr-send" }, t("An ausgewählte senden")), el("button", { type: "button", class: "ghost", "data-close": 1 }, t("Schließen")), el("span", { id: "rr-status", class: "muted small grow" })),
      el("div", { id: "rr-sent", class: "rundruf-sent muted small" })));
    box.classList.add("wide");
    let rrTexts = [];
    function renderTexts() {
      const sel = box.querySelector("#rr-tpl"); const cur = box.querySelector("#rr-text").value.trim(); sel.innerHTML = "";
      sel.append(el("option", { value: "" }, rrTexts.length ? t("– Text wählen –") : t("– noch keine gespeichert –")));
      for (const x of rrTexts) sel.append(el("option", { value: x, selected: x === cur ? 1 : null }, x));
    }
    async function saveTexts(list) {
      if (!list.length && !rrTexts.length) return;
      try { rrTexts = await api("POST", "/api/kst/rundruf_texts", { texts: list }); renderTexts(); toast(t("Rundruf-Texte gespeichert"), "ok"); } catch (err) { toast(err.message, "err"); }
    }
    GET("/api/kst/rundruf_texts").then((l) => { rrTexts = l; renderTexts(); if (!box.querySelector("#rr-text").value && l.length) box.querySelector("#rr-text").value = l[0]; }).catch(() => {});
    // Rotation: S.rrSent merkt sich (je Station, bis zum Neuladen der Seite) wer schon angeschrieben wurde,
    // rrOffset zeigt auf den nächsten noch offenen Kandidaten; „Nächste →“ dreht die Auswahl weiter.
    S.rrSent = S.rrSent || {}; const sentSet = (S.rrSent[st.id] = S.rrSent[st.id] || new Set());
    let cands = [], rrOffset = 0;
    function selectWindow() {
      const n = Number(box.querySelector("#rr-n").value) || 10;
      const open = cands.filter((u) => !sentSet.has(u.call));
      if (!open.length) { $$("#rr-list .rr-sel").forEach((cb) => { cb.checked = false; }); box.querySelector("#rr-status").textContent = `${cands.length} ${t("Kandidaten")} – ${t("alle bereits angeschrieben")}`; return; }
      if (rrOffset >= open.length) rrOffset = 0;
      const pick = new Set(open.slice(rrOffset, rrOffset + n).map((u) => u.call));
      $$("#rr-list .rr-sel").forEach((cb) => { cb.checked = pick.has(cb.value); cb.closest("label").classList.toggle("sent", sentSet.has(cb.value)); });
      const first = box.querySelector("#rr-list .rr-sel:checked"); if (first) first.closest("label").scrollIntoView({ block: "nearest" });
      box.querySelector("#rr-status").textContent = `${cands.length} ${t("Kandidaten")}, ${open.length} ${t("offen")} – ${t("Auswahl")} ${rrOffset + 1}–${Math.min(rrOffset + n, open.length)}`;
    }
    async function loadCands() {
      const km = Number(box.querySelector("#rr-km").value) || 300, n = Number(box.querySelector("#rr-n").value) || 10, away = box.querySelector("#rr-away").checked ? 1 : 0;
      localStorage.setItem("cl.rr.km", km); localStorage.setItem("cl.rr.n", n);
      const list = box.querySelector("#rr-list"); list.innerHTML = ""; rrOffset = 0;
      try {
        cands = await GET(`/api/kst/candidates?station_id=${st.id}&max_km=${km}&include_away=${away}`);
        cands.forEach((u) => list.append(el("label", {}, el("input", { type: "checkbox", class: "rr-sel", value: u.call }), el("b", {}, u.call), `${u.locator} ${u.name || ""}`, el("span", { class: "muted" }, `${u.km} km · ${u.bearing}°`))));
        if (!cands.length) { list.append(el("div", { class: "muted small" }, t("Niemand gefunden – Nutzerliste aktuell? (Knopf „Nutzer“, max. 1 Abfrage/Minute)"))); box.querySelector("#rr-status").textContent = ""; return; }
        selectWindow();
      } catch (err) { list.append(el("div", { class: "muted small" }, err.message)); }
    }
    box.querySelector("#rr-next").addEventListener("click", () => {
      if (!cands.length) return loadCands();
      const n = Number(box.querySelector("#rr-n").value) || 10, open = cands.filter((u) => !sentSet.has(u.call)).length;
      if (open <= n) { selectWindow(); return toast(open ? t("Alle {n} offenen Kandidaten sind schon ausgewählt – Umkreis vergrößern oder erst senden.", { n: open }) : t("Alle Kandidaten wurden bereits angeschrieben – Umkreis vergrößern oder Liste neu laden."), "err"); }
      rrOffset += n;
      if (rrOffset >= open) { rrOffset = 0; toast(t("Ende der Liste – wieder von vorn")); }
      selectWindow();
    });
    box.querySelector("#rr-send").addEventListener("click", async () => {
      const calls = $$("#rr-list .rr-sel:checked").map((c) => c.value); const text = box.querySelector("#rr-text").value.trim();
      if (!calls.length || !text) return toast(t("Empfänger und Text angeben"), "err");
      localStorage.setItem("cl.rr.text", text);
      box.querySelector("#rr-sent").innerHTML = "";
      calls.forEach((c) => sentSet.add(c));
      box.querySelector("#rr-status").textContent = `${t("Sende an")} ${calls.length}: ${calls.join(", ")} …`;
      try { await api("POST", "/api/kst/broadcast", { calls, text, station_id: st.id }); } catch (err) { box.querySelector("#rr-status").textContent = err.message; toast(err.message, "err"); }
    });
    loadCands();
  }
  // Verwaltung: DARC-Contest-Hub
  let darcList = [];
  (function initDarcYears() { const sel = $("#darc-year"); const y = new Date().getUTCFullYear(); for (let i = y; i >= 2017; i--) sel.append(el("option", { value: i }, i)); })();
  $("#btn-darc-list").addEventListener("click", async () => {
    $("#darc-summary").textContent = "…";
    try {
      darcList = await GET(`/api/darc/contests?year=${$("#darc-year").value}`);
      const tb = $("#darc-table tbody"); tb.innerHTML = "";
      for (const c of darcList) tb.append(el("tr", {}, el("td", {}, el("input", { type: "checkbox", class: "darc-sel", "data-csv": c.csv, checked: 1 })), el("td", {}, c.id), el("td", {}, c.name), el("td", { class: "muted small" }, `${c.status} ${c.date}`)));
      $("#darc-wrap").classList.toggle("hidden", !darcList.length); $("#darc-actions").classList.toggle("hidden", !darcList.length);
      $("#darc-summary").textContent = `${darcList.length} ${t("Contests")}`;
    } catch (err) { $("#darc-summary").textContent = err.message; toast(err.message, "err"); }
  });
  async function darcImport(body) {
    $("#darc-summary").textContent = t("Importiere …");
    try {
      const r = await api("POST", "/api/darc/import", body);
      const errs = r.files.filter((f) => f.error);
      $("#darc-summary").textContent = `${r.total} ${t("Rufzeichen übernommen")} · ${t("Stationsdatenbank")}: ${r.callbook_count}` + (errs.length ? ` · ${errs.length} ${t("Fehler")}: ${errs[0].error}` : "");
      toast(`${r.total} ${t("Rufzeichen übernommen")}`, "ok"); renderCallbook();
    } catch (err) { $("#darc-summary").textContent = err.message; toast(err.message, "err"); }
  }
  $("#btn-darc-import").addEventListener("click", () => darcImport({ csv_urls: $$(".darc-sel:checked").map((c) => c.dataset.csv) }));
  $("#btn-darc-all").addEventListener("click", () => { const y = new Date().getUTCFullYear(); const years = []; for (let i = 2017; i <= y; i++) years.push(i); if (confirm(t("Alle DARC-Ergebnislisten {a}–{b} laden? Das dauert ein bis zwei Minuten.", { a: 2017, b: y }))) darcImport({ years }); });

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
    const mapCard = card(t("Karte aller QSOs und Großfelder"), el("div", { id: "map-stats", class: "map tall" })); mapCard.style.gridColumn = "1 / -1"; root.append(mapCard);
    if (Maps["map-stats"]) { try { Maps["map-stats"].map.remove(); } catch (_) { /* */ } delete Maps["map-stats"]; }  // altes Element ist weg – Karte neu anlegen
    setTimeout(() => {
      const m = makeMap("map-stats"); if (!m) return;
      m.map.invalidateSize(); m.layer.clearLayers();
      // gearbeitete Großfelder (JO31 …) als Rechtecke mit QSO-Zahl
      for (const sq of st.squares) {
        const c = locToLatLon(sq.square); if (!c) continue;
        L.rectangle([[c[0] - 0.5, c[1] - 1], [c[0] + 0.5, c[1] + 1]], { color: "#ffb347", weight: 1, fillColor: "#ffb347", fillOpacity: 0.12 + Math.min(0.4, sq.qsos / 40) })
          .bindTooltip(`${sq.square}: ${sq.qsos} QSOs, ${sq.points} ${t("Punkte")}`).addTo(m.layer);
        L.marker(c, { icon: L.divIcon({ className: "map-sq-label", html: `${sq.square} · ${sq.qsos}`, iconAnchor: [28, 7] }), interactive: false }).addTo(m.layer);
      }
      drawQsoDots(m, S.qsos);
      const a = locToLatLon(own?.locator); if (a) L.circleMarker(a, { radius: 7, color: "#3fb3ff", fillColor: "#3fb3ff", fillOpacity: 1 }).bindTooltip(`${t("Eigene Station")} ${own.locator}`).addTo(m.layer);
      const pts = S.qsos.filter((q) => !q.dupe).map((q) => locToLatLon(q.locator)).filter(Boolean);
      if (pts.length) m.map.fitBounds(L.latLngBounds(pts.concat(a ? [a] : [])), { padding: [20, 20] }); else if (a) m.map.setView(a, 6);
    }, 50);
    const c1 = card(t("QSOs und Punkte pro Stunde"), barChart(st.per_hour.map((h) => ({ label: h.hour.slice(11) + "h", a: h.qsos, b: h.points })), t("QSOs"), t("Punkte"))); c1.classList.add("wide2"); root.append(c1);
    const c2 = card(t("Entfernungsverteilung (km)"), barChart(st.distance.map((d) => ({ label: d.range, a: d.qsos, b: d.points })), t("QSOs"), t("Punkte"))); c2.classList.add("wide2"); root.append(c2);
    root.append(card(t("Richtungsverteilung von {loc}", { loc: own?.locator || "" }), rose(st.bearings)));
    root.append(card(t("Top 10 Entfernungen"), table([t("Call"), t("Locator"), "km", t("Pkt"), "UTC"], st.top.map((q) => [q.call, q.locator, q.km, q.points, fmtTime(q.ts_utc)]))));
    const csq = card(`${t("Großfelder")} (${st.squares.length})`, table([t("Feld"), t("QSOs"), t("Punkte")], st.squares.map((q) => [q.square, q.qsos, q.points]))); csq.querySelector(".table-wrap")?.classList.add("tall"); root.append(csq);
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
    const svg = document.createElementNS(ns, "svg"); svg.setAttribute("viewBox", `0 0 ${W} ${H + 20}`); svg.classList.add("chart");
    const add = (tag, attrs, text) => { const n = document.createElementNS(ns, tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); if (text != null) n.textContent = text; svg.append(n); return n; };
    add("line", { x1: P, y1: H, x2: W - P, y2: H, class: "axis" });
    data.forEach((d, i) => {
      const x = P + i * bw;
      const ha = (d.a / maxA) * (H - 30), hb = (d.b / maxB) * (H - 30);
      add("rect", { x: x + 2, y: H - ha, width: bw / 2 - 3, height: ha, class: "bar", rx: 2 }).append(Object.assign(document.createElementNS(ns, "title"), { textContent: `${d.label}: ${d.a} ${la}` }));
      add("rect", { x: x + bw / 2 + 1, y: H - hb, width: bw / 2 - 3, height: hb, class: "bar pts", rx: 2 }).append(Object.assign(document.createElementNS(ns, "title"), { textContent: `${d.label}: ${d.b} ${lb}` }));
      if (d.a) add("text", { x: x + bw / 4, y: H - ha - 3, class: "lbl", "text-anchor": "middle" }, d.a);
      // lange Beschriftungen (z. B. 300-400) versetzt in zwei Reihen, damit nichts überlappt
      const long = data.some((q) => String(q.label).length > 4);
      if (data.length <= 30 || i % 2 === 0) add("text", { x: x + bw / 2, y: H + (long && i % 2 ? 28 : 13), class: "lbl", "text-anchor": "middle" }, d.label);
    });
    if (data.some((q) => String(q.label).length > 4)) svg.setAttribute("viewBox", `0 0 ${W} ${H + 36}`);
    add("text", { x: P, y: 12, class: "lbl" }, `■ ${la} (${t("blau")})   ■ ${lb} (${t("grün")})`);
    return svg;
  }
  function rose(sectors) {
    const ns = "http://www.w3.org/2000/svg", R = 100, C = 120;
    const svg = document.createElementNS(ns, "svg"); svg.setAttribute("viewBox", "0 0 240 240"); svg.classList.add("rose", "chart");
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
    const cs = card(t("Stationen / Bänder"), table([t("Station"), t("Band"), t("QSOs"), t("Punkte"), t("Felder"), "ODX km", t("ODX-Call"), "/h"],
      st.stations.map((s) => { const o = st.odx.find((x) => x.band === s.band); return [s.call, s.band, s.qsos - s.dupes, s.points || 0, s.squares, s.odx_km || 0, o ? `${o.call} ${o.locator}` : "–", s.rate_last_hour]; }))); cs.classList.add("wide2"); root.append(cs);
    // Stundenverlauf je Band (gestapelt)
    const hours = [...new Set(st.per_hour.map((h) => h.hour))].sort();
    const bands = [...new Set(st.per_hour.map((h) => h.band))];
    const ch = card(t("QSOs pro Stunde je Band"), stackedChart(hours, bands, st.per_hour)); ch.classList.add("wide2"); root.append(ch);
    const feed = el("div", { class: "feed table-wrap" }, table(["UTC", t("Station"), t("Band"), t("Call"), t("Locator"), "km", t("Pkt"), "Op"],
      st.recent.map((q) => [fmtTime(q.ts_utc), q.own_call, q.band, q.call + (q.dupe ? t(" (D)") : ""), q.locator, q.km, q.points, q.logged_by])));
    const cf = card(t("Letzte QSOs (alle Stationen)"), feed); cf.classList.add("wide2"); root.append(cf);
    root.append(card(t("Länder (alle Bänder)"), table([t("Land"), t("QSOs"), t("Punkte"), t("ODX km")], st.countries.map((x) => [x.country, x.qsos, x.points, x.odx]))));
    root.append(card(t("Operatoren (alle Bänder)"), table([t("Nick"), t("QSOs"), t("Punkte")], st.operators.map((o) => [o.nick || "–", o.qsos, o.points]))));
  }
  function stackedChart(hours, bands, rows) {
    if (!hours.length) return el("p", { class: "muted" }, t("Noch keine Daten."));
    const W = 600, H = 220, P = 30, bw = (W - 2 * P) / hours.length, ns = "http://www.w3.org/2000/svg";
    const colors = ["#3fb3ff", "#3ddc84", "#ffb347", "#ff5c6c", "#b48cff", "#6ee7e7"];
    const totals = hours.map((h) => rows.filter((r) => r.hour === h).reduce((a, r) => a + r.qsos, 0));
    const max = Math.max(1, ...totals);
    const svg = document.createElementNS(ns, "svg"); svg.setAttribute("viewBox", `0 0 ${W} ${H + 20}`); svg.classList.add("chart");
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
        el("td", { class: "name", title: c.name }, c.id === S.contestId ? el("b", {}, c.name) : c.name),
        el("td", { class: "muted small" }, c.start_utc ? `${fmtDate(c.start_utc)} ${fmtTime(c.start_utc)} – ${fmtDate(c.end_utc)} ${fmtTime(c.end_utc)}` : ""),
        el("td", { class: "muted small" }, `${c.stations.length} ${t("Stationen")}${c.archived ? " · " + t("Archiv") : ""}`),
        el("td", { class: "actions" },
          el("button", { class: "ghost", onclick: () => { S.contestId = c.id; S.stationId = c.stations[0]?.id || null; save(); renderStationBar(); loadQsos(); renderScoreboard(); renderAdmin(); } }, t("wählen")), " ",
          el("a", { class: "button ghost", href: `/api/contests/${c.id}/export.zip?nick=${encodeURIComponent(S.nick)}`, download: 1, title: t("Alle Stationen/Bänder dieses Contests als EDI-Dateien") }, "EDI-ZIP"), " ",
          el("button", { class: "ghost", onclick: () => contestDialog(c) }, "✎"), " ",
          el("button", { class: "ghost", onclick: async () => { await api("PATCH", `/api/contests/${c.id}`, { archived: c.archived ? 0 : 1 }); } }, c.archived ? t("aktivieren") : t("archivieren")), " ",
          el("button", { class: "ghost danger", onclick: async () => { if (confirm(t("Contest „{name}“ mit allen Stationen und QSOs löschen?", c))) await api("DELETE", `/api/contests/${c.id}`); } }, "✕"))));
    }
    // globale Stationen
    try { S.templates = await GET("/api/templates"); } catch (_) { S.templates = []; }
    const tt = $("#admin-templates tbody"); tt.innerHTML = "";
    for (const s of S.templates) tt.append(el("tr", {},
      el("td", { class: "name", title: s.call }, el("b", {}, s.call)), el("td", {}, s.band), el("td", {}, s.locator), el("td", {}, s.mode),
      el("td", { class: "muted small" }, `${s.has_password ? "🔒" : t("offen")}${s.kst_user ? ` · KST ${s.kst_user}` : ""}`),
      el("td", { class: "actions" }, el("button", { class: "ghost", onclick: () => stationDialog(s, true) }, "✎"), " ",
        el("button", { class: "ghost danger", onclick: async () => { if (confirm(t("Globale Station {call} {band} löschen? (Logs in Contests bleiben erhalten)", s))) { await api("DELETE", `/api/templates/${s.id}`); renderAdmin(); } } }, "✕"))));
    if (!S.templates.length) tt.append(el("tr", {}, el("td", { class: "muted" }, t("Noch keine globale Station – mit „+ Station“ anlegen."))));
    const c = contest();
    $("#admin-contest-name").textContent = c ? `– ${c.name}` : "";
    const ts = $("#tpl-add-sel"); ts.innerHTML = "";
    for (const s of S.templates) ts.append(el("option", { value: s.id }, `${s.call} · ${s.band}`));
    const sb = $("#admin-stations tbody"); sb.innerHTML = "";
    for (const s of c?.stations || []) {
      sb.append(el("tr", {},
        el("td", { class: "name", title: s.call }, el("b", {}, s.call), el("div", { class: "muted small" }, `ID ${s.id}`)), el("td", {}, s.locator), el("td", {}, s.band), el("td", {}, s.mode),
        el("td", { class: "muted small" }, `${t("Nr.")} ${pad3(s.serial_next)} · ${s.has_password ? "🔒" : t("offen")}${s.kst_user ? ` · KST ${s.kst_user}` : ""}`),
        el("td", { class: "actions" },
          el("button", { class: "ghost", onclick: () => { S.stationId = s.id; save(); renderStationBar(); loadQsos().then(() => runCheck(true)); }, title: t("EDI dieser Station") }, "EDI"), " ",
          el("a", { class: "button ghost", href: `/api/stations/${s.id}/export.adi`, download: 1 }, "ADIF"), " ",
          el("button", { class: "ghost", onclick: () => stationDialog(s) }, "✎"), " ",
          el("button", { class: "ghost", onclick: async () => { const v = prompt("Nächste Seriennummer:", s.serial_next); if (v && /^\d+$/.test(v)) await api("POST", `/api/stations/${s.id}/serial`, { start: Number(v) }); } }, t("Nr.")), " ",
          el("button", { class: "ghost danger", onclick: async () => { if (confirm(t("Station {call} mit allen QSOs löschen?", s))) await api("DELETE", `/api/stations/${s.id}`); } }, "✕"))));
    }
    // Export / Abgabe des gewählten Contests
    $("#admin-export-name").textContent = c ? `– ${c.name}` : "";
    const ex = $("#admin-export"); ex.innerHTML = "";
    for (const s of c?.stations || []) ex.append(el("div", { class: "row" },
      el("b", { style: "min-width:160px" }, `${s.call} · ${s.band}`),
      el("button", { class: "primary small", onclick: () => { S.stationId = s.id; save(); renderStationBar(); loadQsos().then(() => runCheck(true)); } }, t("EDI (mit Prüfung)")),
      el("a", { class: "button ghost small", href: `/api/stations/${s.id}/export.adi`, download: 1 }, "ADIF"),
      el("a", { class: "button ghost small", href: `/api/stations/${s.id}/export.csv`, download: 1 }, "CSV")));
    if (c) ex.append(el("div", { class: "row" }, el("a", { class: "button primary", href: `/api/contests/${c.id}/export.zip?nick=${encodeURIComponent(S.nick)}`, download: 1 }, t("Alle Bänder als EDI-ZIP")), el("span", { class: "muted small" }, t("nur Logs, die die Prüfung bestehen; Details in NICHT_EXPORTIERT.txt im ZIP"))));
    if (!c?.stations?.length) ex.append(el("div", { class: "muted small" }, t("Keine Stationen im gewählten Contest.")));
    const is = $("#imp-station"); is.innerHTML = "";
    S.contests.forEach((cc) => cc.stations.forEach((s) => is.append(el("option", { value: s.id }, `${cc.name} · ${s.call} ${s.band}`))));
    const inf = await GET("/api/info"); $("#cb-count").textContent = inf.callbook_count; $("#tile-url").value = inf.tile_url || "";
    try {
      const cfg = await GET("/api/settings"); $("#lookup-provider").value = cfg.lookup_provider; $("#lookup-user").value = cfg.lookup_user || ""; $("#lookup-pass").placeholder = cfg.lookup_pass_set ? t("Passwort (gespeichert)") : t("Passwort");
      S.kstRooms = cfg.kst_rooms || {};
      $("#repo-url").value = cfg.repo_url || ""; $("#repo-token").placeholder = cfg.repo_token_set ? t("Token (gespeichert)") : t("GitHub-Token (nur bei privatem Repo)");
    } catch (_) { /* */ }
    renderBackups(); renderCallbook(); renderAudit();
  }
  $("#admin-login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try { S.adminToken = (await api("POST", "/api/admin/login", { password: $("#admin-pw").value })).token; save(); $("#admin-pw").value = ""; renderAdmin(); renderStationBar(); renderQsos(); toast(t("Als Admin angemeldet"), "ok"); } catch (err) { toast(err.message, "err"); }
  });
  $("#btn-backup").addEventListener("click", async () => {
    try { const r = await api("POST", "/api/backups"); toast(t("Gesichert: {name}", r), "ok"); renderBackups(); } catch (err) { toast(err.message, "err"); }
  });
  async function renderAudit() {
    const tb = $("#audit-table tbody"); tb.innerHTML = "";
    try {
      const rows = await GET(`/api/audit?limit=300&q=${encodeURIComponent($("#audit-search").value.trim())}`);
      for (const r of rows) tb.append(el("tr", { class: r.status >= 400 ? "audit-fail" : "" },
        el("td", { class: "muted small nowrap" }, `${fmtDate(r.ts_utc)} ${fmtTime(r.ts_utc)}`),
        el("td", { class: "nowrap" }, el("b", {}, r.nick || "?"), r.admin ? el("span", { class: "tag me", style: "margin-left:4px" }, "Admin") : null),
        el("td", {}, r.action, r.status >= 400 ? el("span", { class: "muted small" }, ` (${t("fehlgeschlagen")} ${r.status})`) : null),
        el("td", { class: "muted small audit-details", title: r.details }, r.details)));
      if (!rows.length) tb.append(el("tr", {}, el("td", { class: "muted" }, t("Keine Einträge."))));
    } catch (_) { /* */ }
  }
  let auditTimer; $("#audit-search").addEventListener("input", () => { clearTimeout(auditTimer); auditTimer = setTimeout(renderAudit, 200); });
  $("#btn-audit-refresh").addEventListener("click", renderAudit);
  $("#btn-audit-dl").addEventListener("click", async () => {
    try { const r = await fetch("/api/audit.txt", { headers: { "X-Admin-Token": S.adminToken } }); const blob = await r.blob(); const a = el("a", { href: URL.createObjectURL(blob), download: "contestlogger-protokoll.txt" }); document.body.append(a); a.click(); a.remove(); } catch (err) { toast(err.message, "err"); }
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
  $("#btn-new-template").addEventListener("click", () => stationDialog(null, true));
  $("#btn-add-template").addEventListener("click", async () => {
    const tid = Number($("#tpl-add-sel").value); if (!tid || !S.contestId) return toast(t("Erst globale Station und Contest wählen"), "err");
    try { await api("POST", `/api/contests/${S.contestId}/stations/from_template`, { template_id: tid }); toast(t("Station aufgenommen"), "ok"); } catch (err) { toast(err.message, "err"); }
  });
  $("#repo-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = { repo_url: $("#repo-url").value.trim() }; if ($("#repo-token").value) body.repo_token = $("#repo-token").value;
    try { await api("POST", "/api/settings", body); $("#repo-token").value = ""; toast(t("Einstellungen gespeichert"), "ok"); renderAdmin(); } catch (err) { toast(err.message, "err"); }
  });
  $("#btn-cb-sync").addEventListener("click", async () => {
    const out = $("#cb-sync-result"); out.textContent = t("Lade aus dem Repo …");
    try { const r = await api("POST", "/api/callbook/sync_repo", {}); out.textContent = `${r.total} ${t("Einträge im Repo")}: ${r.new} ${t("neu")}, ${r.changed} ${t("Locator aktualisiert")} · ${t("Stationsdatenbank")}: ${r.callbook_count}`; toast(`${r.new} ${t("neue Rufzeichen übernommen")}`, "ok"); renderCallbook(); $("#cb-count").textContent = r.callbook_count; }
    catch (err) { out.textContent = err.message; toast(err.message, "err"); }
  });
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
        c ? null : el("div", { class: "stack" }, el("span", { class: "muted small" }, t("Teilnehmende Stationen (aus den globalen Stationen):")),
          el("div", { class: "tpl-list" }, (S.templates || []).map((s) => el("label", { class: "check" }, el("input", { type: "checkbox", class: "c-tpl", value: s.id, checked: 1 }), `${s.call} · ${s.band} · ${s.locator}`)),
            (S.templates || []).length ? null : el("span", { class: "muted small" }, t("Keine globalen Stationen angelegt – Stationen können auch später aufgenommen werden.")))),
        el("div", { class: "row" }, el("button", { class: "primary" }, t("Speichern")), el("button", { type: "button", class: "ghost", "data-close": 1 }, t("Abbrechen"))))));
    box.querySelector("#c-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = { name: box.querySelector("#c-name").value, start_utc: fromLocal(box.querySelector("#c-start").value), end_utc: fromLocal(box.querySelector("#c-end").value), notes: box.querySelector("#c-notes").value,
        template_ids: $$("#c-form .c-tpl:checked").map((x) => Number(x.value)) };
      try {
        const r = c ? await api("PATCH", `/api/contests/${c.id}`, body) : await api("POST", "/api/contests", body);
        if (!c) { S.contestId = r.id; save(); }
        closeModal(); toast(t("Contest gespeichert"), "ok");
      } catch (err) { toast(err.message, "err"); }
    });
  }
  function stationDialog(s, isGlobal = false) {
    const info = s?.info || {};
    const prevInfo = !s ? ((isGlobal ? S.templates?.[0]?.info : contest()?.stations[0]?.info) || {}) : {};
    const box = modal(el("div", {}, el("h3", {}, s ? (isGlobal ? t("Globale Station {call} bearbeiten", s) : t("Station {call} bearbeiten", s)) : (isGlobal ? t("Neue globale Station") : t("Neue Station (nur dieser Contest)"))),
      el("form", { id: "s-form", class: "stack" },
        el("div", { class: "grid2" },
          lab(t("Rufzeichen"), el("input", { id: "s-call", value: s?.call || "", required: 1, placeholder: "DN2LH/P" })),
          lab(t("Locator"), el("input", { id: "s-loc", value: s?.locator || prevInfo.__loc || "", required: 1, placeholder: "JO31AA" })),
          lab(t("Band"), el("select", { id: "s-band" }, BANDS.map((b) => el("option", { value: b, selected: (s?.band || "144MHz") === b ? 1 : null }, b)))),
          lab(t("Modus"), el("select", { id: "s-mode" }, ["SSB", "CW", "FM", "MIXED"].map((m) => el("option", { value: m, selected: (s?.mode || "SSB") === m ? 1 : null }, m)))),
          lab(s ? t("Neues Passwort (leer = unverändert)") : t("Stations-Passwort"), el("input", { id: "s-pw", type: "text", placeholder: t("für Operatoren") })),
          isGlobal ? el("span") : lab(t("Start-Seriennummer"), el("input", { id: "s-serial", type: "number", min: 1, value: s?.serial_next || 1 }))),
        el("details", {}, el("summary", { class: "muted" }, t("Angaben für die EDI-Abgabe (Standort, Verantwortlicher, Technik)")),
          el("div", { class: "grid2" }, INFO_FIELDS.map(([k, l]) => lab(l, el("input", { id: `i-${k}`, value: info[k] ?? prevInfo[k] ?? "" }))))),
        el("details", { open: s?.kst_user ? 1 : null }, el("summary", { class: "muted" }, t("ON4KST-Chat dieser Station")),
          el("p", { class: "muted small" }, t("Eigene KST-Verbindung je Station. Nachrichten an den KST-Login oder das Stations-Call gelten immer als „an mich“ (Zusätze wie /P oder -2 werden ignoriert); weitere Rufzeichen Komma-getrennt eintragen.")),
          el("div", { class: "grid2" },
            lab(t("KST-Rufzeichen"), el("input", { id: "s-kuser", value: s?.kst_user || "", placeholder: "DN2LH", autocomplete: "off" })),
            lab(s?.kst_pass_set ? t("KST-Passwort (leer = unverändert)") : t("KST-Passwort"), el("input", { id: "s-kpass", type: "password", autocomplete: "new-password" })),
            lab(t("Raum"), el("select", { id: "s-kroom" }, Object.entries(S.kstRooms || { 2: "144/432 MHz" }).map(([n, name]) => el("option", { value: n, selected: Number(n) === (s?.kst_room || 2) ? 1 : null }, `${n} – ${name}`)))),
            lab(t("„An mich“-Rufzeichen"), el("input", { id: "s-kmy", value: s?.kst_my_calls || "", placeholder: t("weitere, z. B. DL0ABC") })),
            lab(t("beim Serverstart verbinden"), el("input", { id: "s-kauto", type: "checkbox", checked: s?.kst_autostart ? 1 : null }))),
          s && !isGlobal ? el("div", { class: "row" },
            el("button", { type: "button", class: "ghost", onclick: async () => { try { await api("POST", "/api/kst/start", { station_id: s.id }); toast(t("KST: verbinde …")); } catch (err) { toast(err.message, "err"); } } }, t("Verbinden")),
            el("button", { type: "button", class: "ghost", onclick: async () => { try { await api("POST", "/api/kst/stop", { station_id: s.id }); toast(t("KST getrennt")); } catch (err) { toast(err.message, "err"); } } }, t("Trennen")),
            el("button", { type: "button", class: "ghost small", title: t("Rohdaten der Verbindung (zur Fehlersuche)"), onclick: async () => { try { const r = await GET(`/api/kst/raw?station_id=${s.id}`); const w = window.open("", "kstraw"); w.document.write("<pre style=\"font:12px monospace;white-space:pre-wrap\">" + r.lines.map((l) => l.replace(/</g, "&lt;")).join("\n") + "</pre>"); } catch (err) { toast(err.message, "err"); } } }, t("Rohdaten"))) : null),
        el("div", { class: "row" }, el("button", { class: "primary" }, t("Speichern")), el("button", { type: "button", class: "ghost", "data-close": 1 }, t("Abbrechen"))))));
    box.querySelector("#s-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const g = (id) => box.querySelector(id).value.trim();
      const infoOut = {}; INFO_FIELDS.forEach(([k]) => { infoOut[k] = g(`#i-${k}`); });
      const body = { call: g("#s-call"), locator: g("#s-loc"), band: g("#s-band"), mode: g("#s-mode"), info: infoOut,
        kst_user: g("#s-kuser").toUpperCase(), kst_room: Number(g("#s-kroom")) || 2, kst_my_calls: g("#s-kmy").toUpperCase(), kst_autostart: box.querySelector("#s-kauto").checked ? 1 : 0 };
      if (!isGlobal) body.serial_next = Number(g("#s-serial"));
      if (box.querySelector("#s-kpass").value) body.kst_pass = box.querySelector("#s-kpass").value;
      if (g("#s-pw") || !s) body.password = g("#s-pw");
      try {
        if (isGlobal) { s ? await api("PATCH", `/api/templates/${s.id}`, body) : await api("POST", "/api/templates", body); closeModal(); toast(t("Globale Station gespeichert"), "ok"); renderAdmin(); return; }
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
        el("td", {}, el("b", {}, c.call)), el("td", {}, c.locator, c.alt_locators ? el("span", { class: "muted small", title: t("weitere bekannte Standorte") }, ` (${c.alt_locators.split(",").join(", ")})`) : null), el("td", { class: "muted small" }, c.name || ""),
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
      out.innerHTML = "";
      out.append(el("div", { class: "imp-sum" },
        `${r.files.length} ${t("Dateien importiert")} · ${r.contests} ${t("Contests angelegt")} · ${r.qsos} ${t("QSOs übernommen")}`, el("br"),
        `${t("Rufzeichen")}: ${r.calls_new} ${t("neu")}, ${r.calls_known} ${t("bereits bekannt")}`),
        el("details", {}, el("summary", {}, t("Details je Datei")),
          el("div", {}, r.files.map((f) => el("div", {}, `${f.file}: ${f.kind}, ${f.qsos} QSOs, ${f.imported} ${t("neu")}, ${t("Rufzeichen")} ${f.calls_new} ${t("neu")} / ${f.calls_known} ${t("bekannt")}${f.note ? " – " + f.note : ""}`)))),
        ...(r.skipped.length ? [el("details", {}, el("summary", {}, `${t("Hinweise")} (${r.skipped.length})`), el("div", {}, r.skipped.map((x) => el("div", {}, x))))] : []));
      toast(t("Import abgeschlossen"), "ok"); await loadContests(); renderAdmin();
    } catch (err) { out.textContent = t("Fehler: ") + err.message; toast(err.message, "err"); }
  });
  let resPairs = [];
  $("#results-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData();
    if ($("#res-file").files[0]) fd.append("file", $("#res-file").files[0]);
    fd.append("url", $("#res-url").value.trim()); fd.append("text", $("#res-text").value); fd.append("commit", "0");
    $("#res-summary").textContent = t("Importiere …");
    try {
      const r = await api("POST", "/api/import/results", fd);
      resPairs = r.pairs;
      const tb = $("#res-table tbody"); tb.innerHTML = "";
      for (const p of r.pairs) tb.append(el("tr", { class: p.status === "gleich" ? "muted" : "" },
        el("td", {}, el("input", { type: "checkbox", class: "res-sel", "data-call": p.call, checked: p.status !== "gleich" ? 1 : null })),
        el("td", {}, el("b", {}, p.call)), el("td", {}, p.locator), el("td", { class: "muted small" }, p.status === "neu" ? t("neu") : p.status === "gleich" ? t("bekannt") : `${t("bisher")} ${p.known}`)));
      $("#res-wrap").classList.toggle("hidden", !r.pairs.length); $("#res-actions").classList.toggle("hidden", !r.pairs.length);
      const nNew = r.pairs.filter((p) => p.status !== "gleich").length;
      $("#res-summary").textContent = `${r.count} ${t("Rufzeichen mit Locator gefunden")}, ${nNew} ${t("neu / geändert")}` + (r.warnings.length ? ` · ${r.warnings.length} ${t("Hinweise")}: ${r.warnings.slice(0, 3).join("; ")}` : "");
    } catch (err) { $("#res-summary").textContent = err.message; toast(err.message, "err"); }
  });
  $("#res-only-new").addEventListener("change", (e) => { $$(".res-sel").forEach((cb) => { const p = resPairs.find((x) => x.call === cb.dataset.call); cb.checked = e.target.checked ? p.status !== "gleich" : true; }); });
  $("#btn-res-commit").addEventListener("click", async () => {
    const sel = $$(".res-sel:checked").map((cb) => cb.dataset.call);
    if (!sel.length) return toast(t("Nichts ausgewählt"), "err");
    const fd = new FormData();
    if ($("#res-file").files[0]) fd.append("file", $("#res-file").files[0]);
    fd.append("url", $("#res-url").value.trim()); fd.append("text", $("#res-text").value); fd.append("commit", "1"); fd.append("selected", sel.join(","));
    try { const r = await api("POST", "/api/import/results", fd); toast(`${r.imported} ${t("Rufzeichen übernommen")}`, "ok"); $("#res-wrap").classList.add("hidden"); $("#res-actions").classList.add("hidden"); $("#res-summary").textContent = ""; renderCallbook(); } catch (err) { toast(err.message, "err"); }
  });
  $("#cb-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try { await api("POST", "/api/callbook", { call: $("#cb-call").value, locator: $("#cb-loc").value, name: $("#cb-name").value }); toast(t("Call gespeichert"), "ok"); $("#cb-call").value = $("#cb-loc").value = $("#cb-name").value = ""; renderCallbook(); } catch (err) { toast(err.message, "err"); }
  });

  boot().catch((e) => toast(t("Start fehlgeschlagen: ") + e.message, "err"));
})();
