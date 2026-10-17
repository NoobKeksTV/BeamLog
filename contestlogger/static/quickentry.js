/* BeamLog – Schnelleingabe („Fast Log Entry“): alles in eine Zeile, in beliebiger Reihenfolge, z. B.
 *   DL1ABC JO31AA 012 57 G01      oder      57 012 G01 jo31aa dl1abc
 * parse() ordnet jedes Stück zu: Rufzeichen, Locator, Nr erh., RST erh., DOK erh., Rest = Kommentar.
 * Eigene Angaben (RST geg., Nr geg.) setzt die Schnelleingabe nie.
 *
 * Regeln für Zahlen (RST erh. oder Nr erh.):
 *  - RST ist plausibel, wenn er mit 5 beginnt: 51–59 (Sprechfunk) bzw. 511–599 (CW); 4x, 3x … sind sehr selten und
 *    gelten als Nummer – ausdrücklich als RST mit „r“ davor: r44, rst449. Nummer ausdrücklich: #12 oder nr12.
 *  - Führende Null (012, 059) = immer Nummer.
 *  - Eine einzelne Zahl ist die Nummer (bei reinem DOK-Austausch der RST).
 *  - Zwei Zahlen: die plausible RST-Zahl ist der RST, die andere die Nummer; sind beide plausibel (57 55), gilt
 *    59/599 als RST, sonst die zweite – mit Hinweis „mehrdeutig“.
 */
(function (root) {
  "use strict";
  const LOC = /^[A-R]{2}[0-9]{2}(?:[A-X]{2}(?:[0-9]{2})?)?$/;
  // Präfix (DL, F, 9A, 2E …), Ziffer(n), Suffix aus Buchstaben; optional /P, /M, DL/… usw.
  const CALL = /^(?:[A-Z0-9]{1,4}\/)?(?:[A-Z]{1,2}|[0-9][A-Z]|[A-Z][0-9])[0-9]{1,4}[A-Z]{1,4}(?:\/[A-Z0-9]{1,4})?$/;
  const DOK = /^[A-Z0-9]{1,8}$/;
  const NUM = /^[0-9]{1,5}$/;

  function rstPlausible(n, mode) {
    const m = String(mode || "").toUpperCase();
    const phone = /^5[1-9]$/.test(n), cw = /^5[1-9][1-9]$/.test(n);
    if (m === "CW") return cw;
    if (m === "SSB" || m === "FM" || m === "AM") return phone;
    return phone || cw;  // MIXED / unbekannt
  }

  /** opts: { mode: "SSB"|"CW"|"FM"|"MIXED", serial: bool (Nummer im Austausch), dok: bool (DOK im Austausch) } */
  function parse(line, opts) {
    opts = Object.assign({ mode: "SSB", serial: true, dok: false }, opts || {});
    const out = { call: "", locator: "", serial: "", rst: "", dok: "", comment: "", notes: [] };
    const nums = [], rest = [];
    const tokens = String(line || "").split(/[\s,;]+/).filter(Boolean);
    for (const raw of tokens) {
      const tok = raw.toUpperCase();  // erkannt wird in Großbuchstaben, der Kommentar behält die Schreibweise
      let m;
      if ((m = /^R(?:ST)?([0-9]{2,3})$/.exec(tok)) && !out.rst) out.rst = m[1];
      else if ((m = /^(?:#|NR)([0-9]{1,5})$/.exec(tok)) && !out.serial && opts.serial) out.serial = m[1];
      else if (LOC.test(tok) && !out.locator) out.locator = tok;
      else if (CALL.test(tok) && !out.call) out.call = tok;
      else if (NUM.test(tok)) nums.push(tok);
      else if (opts.dok && DOK.test(tok) && !out.dok) out.dok = tok;
      else rest.push(raw);
    }
    // Zahlen auf RST erh. und Nr erh. verteilen
    const isRst = (n) => !/^0/.test(n) && rstPlausible(n, opts.mode);
    const take = (n) => { nums.splice(nums.indexOf(n), 1); return n; };
    if (!opts.serial) {
      const r = nums.find(isRst);
      if (r && !out.rst) out.rst = take(r);
    } else {
      if (out.serial && !out.rst) { const r = nums.find(isRst); if (r) out.rst = take(r); }
      if (!out.serial && out.rst && nums.length) out.serial = take(nums[0]);
      if (!out.serial && !out.rst && nums.length === 1) out.serial = take(nums[0]);
      if (!out.serial && !out.rst && nums.length >= 2) {
        const cands = nums.filter(isRst);
        let r = null;
        if (cands.length === 1) r = cands[0];
        else if (cands.length > 1) {
          r = cands.find((n) => n === "59" || n === "599") || cands[cands.length - 1];
          if (cands.length === nums.length) out.notes.push({ kind: "ambiguous", values: nums.slice(0, 2) });
        }
        if (r) out.rst = take(r);
        if (nums.length) out.serial = take(nums[0]);
      }
    }
    if (out.serial && /^[0-9]+$/.test(out.serial)) out.serial = String(Number(out.serial)).padStart(3, "0");
    if (nums.length) rest.unshift(...nums);
    out.comment = rest.join(" ");
    return out;
  }

  const api = { parse, rstPlausible, LOC, CALL };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.BeamQuick = api;
})(typeof window !== "undefined" ? window : this);
