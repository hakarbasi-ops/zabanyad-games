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

  // invite links look like /?r=AB12CD: keep the code until this visitor verifies a mobile
  try {
    const ref = new URLSearchParams(location.search).get("r");
    if (ref && /^[A-Za-z0-9]{4,12}$/.test(ref)) store.set("zg:ref", ref.toUpperCase());
  } catch (e) { /* ignore */ }

  // campaign links carry ?utm_source=instagram|telegram|sms|story: remember it for 7 days for the report
  let src = "";
  try {
    const fromUrl = (new URLSearchParams(location.search).get("utm_source") || "").toLowerCase().replace(/[^a-z0-9_-]/g, "").slice(0, 30);
    const saved = store.get("zg:src");
    if (fromUrl) store.set("zg:src", { v: fromUrl, until: Date.now() + 7 * 864e5 });
    src = fromUrl || (saved && saved.until > Date.now() ? saved.v : "");
  } catch (e) { /* ignore */ }
  // counts a visit of this page (home or a game) per day and source; no personal data
  function visit(slug) {
    fetch("/api/visit", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug, src }), keepalive: true }).catch(() => {});
  }

  const WEEKDAYS = ["یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه"];
  // "2026-11-30 23:59:59" -> "یکشنبه ۹ آذر"
  function dayName(value) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value || "");
    if (!m) return "";
    const wd = WEEKDAYS[new Date(Date.UTC(+m[1], m[2] - 1, +m[3])).getUTCDay()];
    return `${wd} ${jalaliDate(`${m[1]}-${m[2]}-${m[3]} 12:00`).replace(/\s[۰-۹]{4}$/, "")}`;
  }

  // drawn illustrations (static/img/art/*.svg) instead of emoji; ?v= so a redrawn picture is not served from cache
  const V = (document.querySelector('meta[name="zg-version"]') || {}).content || "";
  function art(name, cls = "art") {
    return el("img", { class: cls, src: `/static/img/art/${name}.svg${V ? `?v=${V}` : ""}`, alt: "", "aria-hidden": "true", draggable: "false" });
  }
  // small line icons that take the text colour
  const ICONS = {
    ticket: '<path d="M4 7h16v3a2 2 0 0 0 0 4v3H4v-3a2 2 0 0 0 0-4Z"/><path d="M15 7v10" stroke-dasharray="2 2"/>',
    gift: '<rect x="3.5" y="9" width="17" height="11" rx="1.5"/><path d="M2.5 9h19M12 9v11M12 9C10 5 6.5 4 6 6.5S9 9 12 9Zm0 0c2-4 5.5-5 6-2.5S15 9 12 9Z"/>',
    play: '<rect x="2.5" y="7" width="19" height="11" rx="5.5"/><path d="M7.5 10.5v4M5.5 12.5h4"/><circle cx="15.5" cy="11.5" r=".6" fill="currentColor"/><circle cx="17.5" cy="13.5" r=".6" fill="currentColor"/>',
    sound: '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4Z"/><path d="M15.5 9a4.5 4.5 0 0 1 0 6M18 6.5a8 8 0 0 1 0 11"/>',
    mute: '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4Z"/><path d="m16 9.5 5 5m0-5-5 5"/>',
    hourglass: '<path d="M6.5 3.5h11M6.5 20.5h11M7.5 3.5c0 5 9 6 9 8.5s-9 3.5-9 8.5M16.5 3.5c0 5-9 6-9 8.5s9 3.5 9 8.5"/>',
    flame: '<path d="M12 21c4 0 6.5-2.6 6.5-6.2 0-4.3-4-6.3-4.5-10.3-2.8 1.8-4 4.5-3.7 7-1-.4-1.8-1.5-2-2.8C6.6 10.4 5.5 12.6 5.5 14.8 5.5 18.4 8 21 12 21Z"/>',
    sparkle: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18"/>',
    lock: '<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5M12 14.5v2.5"/>',
    trophy: '<path d="M8 4h8v5a4 4 0 0 1-8 0Z"/><path d="M8 6H4.5c0 3 1.5 4.5 3.7 4.8M16 6h3.5c0 3-1.5 4.5-3.7 4.8M12 13v4M8.5 20h7l-.8-3h-5.4Z"/>',
  };
  function icon(name) {
    return el("span", { class: "ico", "aria-hidden": "true", html:
      `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ""}</svg>` });
  }

  // «آخرین برنده‌ها»: real winners of every prize (90% ones in gold), today's players, 90% codes still waiting.
  // Refreshes every 30 s. Hidden while there is nothing real to show.
  function activityBoard() {
    const box = el("section", { class: "jackpot activity hidden" });
    const ago = (s) => (s < 60 ? "همین الان" : s < 3600 ? `${fa(Math.floor(s / 60))} دقیقه پیش`
      : s < 86400 ? `${fa(Math.floor(s / 3600))} ساعت پیش` : `${fa(Math.floor(s / 86400))} روز پیش`);
    async function load() {
      let a;
      try { a = await api("/api/activity"); } catch (e) { return; }
      const cards = a.jackpots.map((j) => {
        const name = String(j.label).split(" ")[0];
        let text;
        if (j.left === 0) text = `کدهای ${name} تموم شد`;
        else if (j.left_today > 0) text = `${fa(j.left_today)} کد ${name} امروز مونده`;
        else if (j.next_day) text = `${fa(j.left)} کد ${name} منتظر برنده‌ست، از ${dayName(j.next_day)}`;
        else text = `${fa(j.left)} کد ${name} منتظر برنده‌ست`;
        return el("a", { class: "jp-card", href: `/g/${encodeURIComponent(j.slug)}` }, icon("trophy"), el("b", {}, text), el("small", {}, j.game));
      });
      if (!a.recent.length && !cards.length) return box.classList.add("hidden");
      box.replaceChildren(
        el("div", { class: "act-head" }, el("h3", {}, icon("sparkle"), " آخرین برنده‌ها"),
          a.players_today ? el("span", { class: "act-count" }, `امروز ${fa(a.players_today)} نفر بازی کردن`) : ""),
        ...cards,
        a.recent.length ? el("ol", {}, a.recent.map((w) => el("li", { class: w.big ? "big" : "" },
          el("span", { class: "m" }, fa(w.mobile)), el("b", { class: "p" }, w.prize), el("span", { class: "g" }, w.game),
          el("small", {}, ago(w.ago))))) : el("p", {}, "اولین برنده‌ی امروز می‌تونی تو باشی!"));
      box.classList.remove("hidden");
    }
    load();
    const timer = setInterval(() => (document.body.contains(box) ? load() : clearInterval(timer)), 30000);
    return box;
  }

  window.ZG = { fa, money, jalaliDate, api, el, store, copy, src: () => src, visit, dayName, art, icon, ICONS, activityBoard };
})();
