// Shared helpers for the game pages and the admin panel.
(function () {
  const FA = "۰۱۲۳۴۵۶۷۸۹";

  function fa(value) {
    return String(value ?? "").replace(/\d/g, (d) => FA[d]);
  }

  function money(n) {
    return fa(Number(n || 0).toLocaleString("en-US")).replace(/,/g, "٬");
  }

  // Gregorian -> Jalali (algorithm from jalaali-js)
  function toJalali(gy, gm, gd) {
    const g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
    let jy = gy <= 1600 ? 0 : 979;
    gy -= gy <= 1600 ? 621 : 1600;
    const gy2 = gm > 2 ? gy + 1 : gy;
    let days = 365 * gy + Math.floor((gy2 + 3) / 4) - Math.floor((gy2 + 99) / 100) +
      Math.floor((gy2 + 399) / 400) - 80 + gd + g_d_m[gm - 1];
    jy += 33 * Math.floor(days / 12053);
    days %= 12053;
    jy += 4 * Math.floor(days / 1461);
    days %= 1461;
    if (days > 365) {
      jy += Math.floor((days - 1) / 365);
      days = (days - 1) % 365;
    }
    const jm = days < 186 ? 1 + Math.floor(days / 31) : 7 + Math.floor((days - 186) / 30);
    const jd = 1 + (days < 186 ? days % 31 : (days - 186) % 30);
    return [jy, jm, jd];
  }

  const MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];

  // "2026-10-31 23:59:59" (Tehran) or an ISO string -> "۹ آبان ۱۴۰۵"
  function jalaliDate(value, withTime) {
    if (!value) return "";
    let y, m, d, hh = "", mm = "";
    const local = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(value);
    if (local && !/[zZ+]|[+-]\d{2}:\d{2}$/.test(value.slice(10))) {
      [y, m, d, hh, mm] = local.slice(1).map(Number);
    } else {
      const dt = new Date(value);
      if (isNaN(dt)) return value;
      const parts = new Intl.DateTimeFormat("en-CA", {
        timeZone: "Asia/Tehran", year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", hour12: false,
      }).formatToParts(dt);
      const get = (t) => Number(parts.find((p) => p.type === t).value);
      [y, m, d, hh, mm] = [get("year"), get("month"), get("day"), get("hour") % 24, get("minute")];
    }
    const [jy, jm, jd] = toJalali(y, m, d);
    let out = `${fa(jd)} ${MONTHS[jm - 1]} ${fa(jy)}`;
    if (withTime) out += `، ${fa(String(hh).padStart(2, "0"))}:${fa(String(mm).padStart(2, "0"))}`;
    return out;
  }

  async function api(path, options = {}) {
    const init = { credentials: "same-origin", ...options };
    if (init.body && typeof init.body !== "string") {
      init.body = JSON.stringify(init.body);
      init.headers = { "Content-Type": "application/json", ...(init.headers || {}) };
    }
    let res;
    try {
      res = await fetch(path, init);
    } catch (e) {
      throw Object.assign(new Error("اینترنت وصل نیست یا سرور جواب نداد. دوباره امتحان کنید."), { code: "network" });
    }
    let data = null;
    try { data = await res.json(); } catch (e) { /* not JSON */ }
    if (!res.ok) {
      let message = data && data.detail;
      if (Array.isArray(message)) message = "اطلاعات واردشده کامل یا درست نیست.";
      throw Object.assign(new Error(message || "خطایی پیش آمد. دوباره امتحان کنید."), {
        code: data && data.code, status: res.status,
      });
    }
    return data;
  }

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") node.className = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else if (k === "html") node.innerHTML = v;
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) {
      if (c == null || c === false) continue;
      node.append(c.nodeType ? c : document.createTextNode(c));
    }
    return node;
  }

  const store = {
    get(key) { try { return JSON.parse(localStorage.getItem(key)); } catch (e) { return null; } },
    set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* private mode */ } },
  };

  async function copy(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (e) {
      const t = el("textarea", { style: "position:fixed;opacity:0" }, text);
      document.body.append(t);
      t.select();
      const ok = document.execCommand("copy");
      t.remove();
      return ok;
    }
  }

  window.ZG = { fa, money, jalaliDate, api, el, store, copy };
})();
