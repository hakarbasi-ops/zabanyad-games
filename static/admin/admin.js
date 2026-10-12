// Admin panel: dashboard, games (prizes, chances, questions), plays, API check. Hash routes.
(function () {
  const { fa, money, jalaliDate, api, el, copy } = window.ZG;
  const root = document.getElementById("root");
  const KIND = { wheel: "گردونه شانس", scratch: "کارت خراشی", quiz: "چالش کلمه" };
  const ICON = { wheel: "🎡", scratch: "🎟️", quiz: "🔤" };
  const PRIZE_KIND = { percentage: "درصدی", amount: "مبلغی (ریال)", none: "بدون جایزه" };
  const STATUS = {
    won: ["برنده", "ok"], lost: ["بدون جایزه", "off"], need_signup: ["ثبت‌نام نکرده", "warn"],
    error: ["خطا", "bad"], pending: ["در حال بازی", "off"],
  };
  let me = null;

  window.addEventListener("hashchange", route);
  boot();

  async function boot() {
    try {
      me = await api("/api/admin/me");
      route();
    } catch (e) {
      if (e.status === 401) loginView(); else root.replaceChildren(el("div", { class: "login card" }, e.message));
    }
  }

  function loginView() {
    const input = el("input", { type: "password", placeholder: "رمز پنل", autocomplete: "current-password" });
    const msg = el("div");
    const form = el("form", { class: "card login" },
      el("h1", {}, "پنل بازی‌های زبانیاد"),
      el("label", { class: "f" }, el("span", {}, "رمز"), input),
      el("button", { class: "btn", style: "width:100%;margin-top:12px" }, "ورود"), msg);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api("/api/admin/login", { method: "POST", body: { password: input.value } });
        boot();
      } catch (err) {
        msg.replaceChildren(el("div", { class: "msg bad" }, err.message));
      }
    });
    root.replaceChildren(form);
    input.focus();
  }

  function shell(active, ...content) {
    const link = (hash, text) => el("a", { href: hash, class: active === hash ? "active" : "" }, text);
    const logout = el("a", { href: "#", onclick: async (e) => { e.preventDefault(); await api("/api/admin/logout", { method: "POST" }); loginView(); } }, "خروج");
    root.replaceChildren(el("div", { class: "layout" },
      el("nav", { class: "side" },
        el("div", { class: "logo" }, el("img", { src: "/static/img/logo-mark.png", alt: "" }), "بازی‌های زبانیاد"),
        link("#/", "داشبورد"), link("#/games", "بازی‌ها و جایزه‌ها"), link("#/plays", "بازی‌کنندگان و کدها"),
        link("#/settings", "اتصال به زبانیاد"), el("div", { class: "spacer" }), logout),
      el("main", { class: "main" }, modeNote(), ...content)));
  }

  function modeNote() {
    if (me.mode === "live") return "";
    return el("div", { class: "note", style: "margin-bottom:16px" },
      "حالت آزمایشی: کدها ساختگی‌اند (با T شروع می‌شوند) و به زبانیاد فرستاده نمی‌شوند. برای کد واقعی، کلید API را روی سرور تنظیم کنید.");
  }

  function route() {
    const hash = location.hash || "#/";
    const m = hash.match(/^#\/games\/(\d+)/);
    if (m) return gameView(Number(m[1]));
    if (hash.startsWith("#/games")) return gamesView();
    if (hash.startsWith("#/plays")) return playsView();
    if (hash.startsWith("#/settings")) return settingsView();
    return dashboardView();
  }

  function loading(active) {
    shell(active, el("p", { class: "muted" }, "در حال بارگذاری…"));
  }

  function fail(active, e) {
    if (e.status === 401) return loginView();
    shell(active, el("div", { class: "msg bad" }, e.message));
  }

  function badge(status) {
    const [text, cls] = STATUS[status] || [status, "off"];
    return el("span", { class: `badge ${cls}` }, text);
  }

  // ------------------------------------------------------------ dashboard

  async function dashboardView() {
    loading("#/");
    let stats, games;
    try {
      [stats, games] = await Promise.all([api("/api/admin/stats"), api("/api/admin/games")]);
    } catch (e) { return fail("#/", e); }
    const t = stats.totals;
    const stat = (n, label) => el("div", { class: "stat" }, el("b", {}, fa(n)), el("span", {}, label));
    const winRate = t.plays ? Math.round((t.codes / t.plays) * 100) : 0;

    shell("#/",
      el("h1", {}, "داشبورد"),
      el("div", { class: "grid", style: "margin-bottom:16px" },
        stat(t.plays, "بازی انجام‌شده"), stat(t.players, "بازیکن (شماره‌ی یکتا)"),
        stat(t.codes, "کد تخفیف ساخته‌شده"), stat(`${winRate}٪`, "نرخ برد"),
        stat(t.need_signup, "تلاش بدون ثبت‌نام در زبانیاد")),
      el("div", { class: "card" },
        el("div", { class: "row between" }, el("h2", {}, "۱۴ روز اخیر"),
          el("div", { class: "legend" }, el("span", {}, el("i", { style: "background:#fce0cc" }), "بازی"),
            el("span", {}, el("i", { style: "background:#f26600" }), "کد تخفیف"))),
        chart(stats.days)),
      el("div", { class: "card" }, el("h2", {}, "بازی‌ها"),
        el("div", { class: "grid" }, games.map((g) => el("a", { href: `#/games/${g.id}`, class: "stat", style: "text-decoration:none;color:inherit" },
          el("div", { class: "row between" }, el("strong", {}, `${ICON[g.kind]} ${g.title}`),
            g.open ? el("span", { class: "badge ok" }, "فعال") : el("span", { class: "badge off" }, "غیرفعال")),
          el("span", {}, `${fa(g.plays)} بازی · ${fa(g.codes)} کد`))))),
      el("div", { class: "card" }, el("h2", {}, "جایزه‌ها"),
        el("div", { class: "table-wrap" }, el("table", {},
          el("thead", {}, el("tr", {}, ["بازی", "جایزه", "دفعات افتادن", "کد ساخته‌شده", "موجودی"].map((h) => el("th", {}, h)))),
          el("tbody", {}, stats.by_prize.map((p) => el("tr", {},
            el("td", {}, p.game), el("td", {}, p.label), el("td", {}, fa(p.hits)),
            el("td", {}, p.kind === "none" ? "—" : fa(p.won)),
            el("td", {}, p.stock == null ? "نامحدود" : `${fa(Math.max(p.stock - p.given, 0))} از ${fa(p.stock)}`)))))))
    );
  }

  function chart(days) {
    const ns = "http://www.w3.org/2000/svg";
    const W = 700, H = 180, pad = 24;
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("class", "chart");
    svg.setAttribute("preserveAspectRatio", "none");
    const max = Math.max(1, ...days.map((d) => d.plays));
    const bw = (W - pad) / days.length;
    const add = (tag, attrs, text) => {
      const n = document.createElementNS(ns, tag);
      for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
      if (text != null) n.textContent = text;
      svg.append(n);
      return n;
    };
    days.forEach((d, i) => {
      const x = pad / 2 + i * bw;
      const h1 = ((H - 40) * d.plays) / max, h2 = ((H - 40) * d.codes) / max;
      const bar = add("rect", { x: x + bw * 0.15, y: H - 22 - h1, width: bw * 0.7, height: h1, rx: 4, fill: "#fce0cc" });
      add("rect", { x: x + bw * 0.15, y: H - 22 - h2, width: bw * 0.7, height: h2, rx: 4, fill: "#f26600" });
      const title = document.createElementNS(ns, "title");
      title.textContent = `${jalaliDate(d.day + " 12:00")}: ${fa(d.plays)} بازی، ${fa(d.codes)} کد`;
      bar.append(title);
      if (i % 2 === days.length % 2) {
        add("text", { x: x + bw / 2, y: H - 6, "text-anchor": "middle", "font-size": 11, fill: "#6b7588" },
          jalaliDate(d.day + " 12:00").split(" ").slice(0, 2).join(" "));
      }
    });
    return svg;
  }

  // ------------------------------------------------------------ games list

  async function gamesView() {
    loading("#/games");
    let games;
    try { games = await api("/api/admin/games"); } catch (e) { return fail("#/games", e); }

    const slug = el("input", { type: "text", class: "ltr", placeholder: "nowruz-wheel" });
    const title = el("input", { type: "text", placeholder: "گردونه نوروزی" });
    const kind = el("select", {}, Object.entries(KIND).map(([k, v]) => el("option", { value: k }, v)));
    const msg = el("div");
    const add = el("form", { class: "card" }, el("h2", {}, "بازی تازه"),
      el("div", { class: "form-grid" },
        el("label", { class: "f" }, el("span", {}, "نوع بازی"), kind),
        el("label", { class: "f" }, el("span", {}, "عنوان"), title),
        el("label", { class: "f" }, el("span", {}, "نشانی (انگلیسی، در لینک بازی)"), slug)),
      el("button", { class: "btn", style: "margin-top:12px" }, "ساخت بازی"), msg);
    add.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const g = await api("/api/admin/games", { method: "POST", body: { slug: slug.value, title: title.value, kind: kind.value } });
        location.hash = `#/games/${g.id}`;
      } catch (err) { msg.replaceChildren(el("div", { class: "msg bad" }, err.message)); }
    });

    shell("#/games",
      el("h1", {}, "بازی‌ها و جایزه‌ها"),
      el("div", { class: "grid", style: "margin-bottom:16px" }, games.map((g) =>
        el("div", { class: "card game-card", style: "margin:0" },
          el("div", { class: "row between" }, el("span", { class: "icon" }, ICON[g.kind]),
            g.open ? el("span", { class: "badge ok" }, "فعال") : el("span", { class: "badge off" }, g.enabled ? g.message : "غیرفعال")),
          el("h3", {}, g.title),
          el("span", { class: "muted small" }, `${KIND[g.kind]} · ${fa(g.plays)} بازی · ${fa(g.codes)} کد`),
          el("div", { class: "row" }, el("a", { class: "btn", href: `#/games/${g.id}` }, "تنظیمات"),
            el("a", { class: "btn light", href: `/g/${g.slug}`, target: "_blank" }, "دیدن بازی"))))),
      add);
  }

  // ------------------------------------------------------------ game editor

  async function gameView(id) {
    loading("#/games");
    let game;
    try { game = await api(`/api/admin/games/${id}`); } catch (e) { return fail("#/games", e); }
    const isQuiz = game.kind === "quiz";
    const url = `${location.origin}/g/${game.slug}`;

    const f = {};
    const text = (key, attrs = {}) => (f[key] = el("input", { type: "text", value: game[key] ?? "", ...attrs }));
    const num = (key, attrs = {}) => (f[key] = el("input", { type: "number", value: game[key] ?? 0, min: 0, ...attrs }));
    const dt = (key) => {
      const input = (f[key] = el("input", { type: "datetime-local", value: (game[key] || "").replace(" ", "T").slice(0, 16) }));
      const hint = el("span", { class: "small" });
      const upd = () => (hint.textContent = input.value ? jalaliDate(input.value.replace("T", " "), true) : "بدون محدودیت");
      input.addEventListener("input", upd);
      upd();
      return [input, hint];
    };
    f.enabled = el("input", { type: "checkbox", checked: !!game.enabled });
    f.rules = el("textarea", {}, game.rules || "");
    f.color = el("input", { type: "color", value: game.settings.color || "#f26600" });
    if (isQuiz) {
      f.question_count = el("input", { type: "number", min: 1, max: 20, value: game.settings.question_count || 5 });
      f.time_limit = el("input", { type: "number", min: 10, max: 600, value: game.settings.time_limit || 60 });
    }

    const prizeRows = el("tbody");
    const prizes = game.prizes.map((p) => ({ ...p }));
    const chanceCells = [];
    // amounts are rials (as the Zabanyad API expects); show the toman value under the box to avoid a zero too many
    function rialField(p, key, isRial) {
      const input = el("input", { type: "number", min: 0, value: p[key], title: isRial ? "ریال" : "درصد" });
      const hint = el("div", { class: "small muted" });
      const upd = () => {
        const v = Number(input.value) || 0;
        hint.textContent = !isRial ? "درصد" : v ? `${money(Math.round(v / 10))} تومان` : (key === "max_amount" ? "لازم است" : "");
      };
      input.addEventListener("input", () => { p[key] = input.value === "" ? 0 : Number(input.value); upd(); });
      upd();
      return el("div", {}, input, hint);
    }
    function renderPrizes() {
      chanceCells.length = 0;
      const total = prizes.filter((p) => p.active).reduce((s, p) => s + (Number(p.weight) || 0), 0);
      prizeRows.replaceChildren(...prizes.map((p, i) => {
        const bind = (key, input, cast = (v) => v) => {
          input.addEventListener("input", () => { p[key] = cast(input.type === "checkbox" ? input.checked : input.value); updChances(); });
          return input;
        };
        const n = (v) => (v === "" ? 0 : Number(v));
        const kindSel = bind("kind", el("select", {}, Object.entries(PRIZE_KIND).map(([k, v]) => el("option", { value: k, selected: p.kind === k }, v))));
        kindSel.addEventListener("change", renderPrizes);
        const chance = el("td", { class: "small muted" });
        chanceCells.push([chance, p]);
        const none = p.kind === "none";
        return el("tr", {},
          el("td", {}, bind("label", el("input", { type: "text", class: "w-label", value: p.label }))),
          el("td", {}, kindSel),
          el("td", {}, none ? "—" : rialField(p, "amount", p.kind === "amount")),
          el("td", {}, none ? "—" : rialField(p, "max_amount", true)),
          el("td", {}, none ? "—" : bind("usage_count", el("input", { type: "number", min: 1, value: p.usage_count, style: "width:70px" }), n)),
          isQuiz
            ? el("td", {}, bind("min_score", el("input", { type: "number", min: 0, value: p.min_score, style: "width:70px" }), n))
            : el("td", {}, bind("weight", el("input", { type: "number", min: 0, value: p.weight, style: "width:80px" }), n)),
          isQuiz ? "" : chance,
          el("td", {}, none ? "—" : bind("stock", el("input", { type: "number", min: 0, value: p.stock ?? "", placeholder: "نامحدود", style: "width:90px" }),
            (v) => (v === "" ? null : Number(v)))),
          el("td", { class: "small muted" }, none ? "—" : fa(p.given || 0)),
          isQuiz ? "" : el("td", {}, bind("color", el("input", { type: "color", value: p.color || "#f26600" }))),
          el("td", {}, bind("active", el("input", { type: "checkbox", checked: !!p.active }))),
          el("td", {}, el("button", { type: "button", class: "btn ghost", title: "حذف", onclick: () => { prizes.splice(i, 1); renderPrizes(); } }, "✕")));
      }));
      updChances(total);
    }
    function updChances() {
      const total = prizes.filter((p) => p.active).reduce((s, p) => s + (Number(p.weight) || 0), 0);
      for (const [cell, p] of chanceCells) {
        cell.textContent = p.active && total ? `${fa(Math.round(((Number(p.weight) || 0) / total) * 1000) / 10)}٪` : "—";
      }
    }
    renderPrizes();

    const prizeHead = ["متن جایزه", "نوع", "مقدار", "سقف تخفیف (ریال)", "دفعات استفاده",
      isQuiz ? "حداقل جواب درست" : "وزن شانس", isQuiz ? "" : "احتمال", "موجودی", "داده‌شده", isQuiz ? "" : "رنگ", "فعال", ""]
      .filter((h, i) => !(isQuiz && (i === 6 || i === 9)));

    let questionsBox = "";
    if (isQuiz) {
      const lines = game.questions.filter((q) => q.active).map((q) => [q.word, q.answer, ...q.wrong].join(" | ")).join("\n");
      f.questions = el("textarea", { class: "ltr", style: "min-height:260px;direction:rtl" }, lines);
      questionsBox = el("div", { class: "card" }, el("h2", {}, "کلمه‌ها"),
        el("p", { class: "muted small" }, "هر خط یک کلمه: «کلمه | معنی درست | گزینه‌ی غلط ۱ | گزینه‌ی غلط ۲ | گزینه‌ی غلط ۳». هر بار بازی، از بین این‌ها به‌صورت تصادفی انتخاب می‌شود."),
        f.questions,
        el("p", { class: "muted small" }, `${fa(game.questions.filter((q) => q.active).length)} کلمه‌ی فعال`));
    }

    const msg = el("div");
    const save = el("button", { class: "btn" }, "ذخیره");
    const form = el("form", {},
      el("div", { class: "row between", style: "margin-bottom:12px" },
        el("h1", { style: "margin:0" }, `${ICON[game.kind]} ${game.title}`),
        el("div", { class: "row" },
          el("a", { class: "btn light", href: url, target: "_blank" }, "دیدن بازی"),
          el("button", { type: "button", class: "btn light", onclick: async (e) => { e.currentTarget.textContent = (await copy(url)) ? "لینک کپی شد ✓" : url; } }, "کپی لینک"))),
      el("div", { class: "card" },
        el("div", { class: "row between" }, el("h2", {}, "اطلاعات بازی"),
          el("label", { class: "check" }, f.enabled, "بازی فعال باشد")),
        el("p", { class: "muted small ltr", style: "margin-top:0" }, url),
        el("div", { class: "form-grid" },
          el("label", { class: "f" }, el("span", {}, "عنوان"), text("title")),
          el("label", { class: "f" }, el("span", {}, "زیرعنوان"), text("subtitle")),
          el("label", { class: "f" }, el("span", {}, "شروع"), ...dt("starts_at")),
          el("label", { class: "f" }, el("span", {}, "پایان"), ...dt("ends_at")),
          el("label", { class: "f" }, el("span", {}, "رنگ اصلی صفحه"), f.color)),
        el("label", { class: "f", style: "margin-top:14px" }, el("span", {}, "قوانین (زیر بازی نشان داده می‌شود)"), f.rules)),
      el("div", { class: "card" }, el("h2", {}, "محدودیت‌ها و کد تخفیف"),
        el("div", { class: "form-grid" },
          el("label", { class: "f" }, el("span", {}, "هر شماره چند بار بازی کند"), num("plays_per_mobile", { min: 1 })),
          el("label", { class: "f" }, el("span", {}, "در هر چند روز (۰ = کل دوره)"), num("period_days")),
          el("label", { class: "f" }, el("span", {}, "اعتبار کد تخفیف (روز)"), num("code_valid_days", { min: 1 })),
          el("label", { class: "f" }, el("span", {}, "سقف کد در روز (۰ = بدون سقف)"), num("daily_code_limit")),
          isQuiz ? el("label", { class: "f" }, el("span", {}, "تعداد کلمه در هر بازی"), f.question_count) : "",
          isQuiz ? el("label", { class: "f" }, el("span", {}, "زمان (ثانیه)"), f.time_limit) : "")),
      el("div", { class: "card" },
        el("div", { class: "row between" }, el("h2", {}, isQuiz ? "جایزه‌ها بر اساس جواب درست" : (game.kind === "wheel" ? "خانه‌های گردونه" : "جایزه‌های کارت")),
          el("button", { type: "button", class: "btn light", onclick: () => {
            prizes.push({ label: "جایزه‌ی تازه", kind: "percentage", amount: 10, max_amount: 0, usage_count: 1, weight: 1, stock: null, min_score: 0, color: "", active: 1, given: 0 });
            renderPrizes();
          } }, "+ جایزه")),
        el("p", { class: "muted small" }, isQuiz
          ? "بازیکن بهترین جایزه‌ای را می‌گیرد که «حداقل جواب درست» آن را آورده باشد. یک ردیف «بدون جایزه» با حداقل ۰ بگذارید. مبلغ‌ها به ریال است."
          : "شانس هر جایزه = وزن آن ÷ جمع وزن‌ها. وقتی موجودی جایزه‌ای تمام شود، دیگر نمی‌افتد. مبلغ‌ها و سقف تخفیف به ریال است."),
        el("div", { class: "table-wrap" }, el("table", {}, el("thead", {}, el("tr", {}, prizeHead.map((h) => el("th", {}, h)))), prizeRows))),
      questionsBox,
      el("div", { class: "sticky-save row" }, save, msg,
        el("button", { type: "button", class: "btn danger", style: "margin-inline-start:auto", onclick: removeGame }, "حذف بازی")));

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = {
        title: f.title.value, subtitle: f.subtitle.value, rules: f.rules.value, enabled: f.enabled.checked,
        starts_at: f.starts_at.value || null, ends_at: f.ends_at.value || null,
        plays_per_mobile: Number(f.plays_per_mobile.value) || 1, period_days: Number(f.period_days.value) || 0,
        code_valid_days: Number(f.code_valid_days.value) || 7, daily_code_limit: Number(f.daily_code_limit.value) || 0,
        settings: { color: f.color.value },
        prizes: prizes.map((p) => ({
          id: p.id, label: p.label, kind: p.kind, amount: Number(p.amount) || 0, max_amount: Number(p.max_amount) || 0,
          usage_count: Number(p.usage_count) || 1, weight: Number(p.weight) || 0, stock: p.kind === "none" ? null : p.stock,
          min_score: Number(p.min_score) || 0, color: p.color || "", active: !!p.active,
        })),
      };
      if (isQuiz) {
        body.settings.question_count = Number(f.question_count.value) || 5;
        body.settings.time_limit = Number(f.time_limit.value) || 60;
        const byWord = new Map(game.questions.map((q) => [q.word, q.id]));
        const bad = [];
        body.questions = f.questions.value.split("\n").map((line, i) => [line.split("|").map((s) => s.trim()).filter(Boolean), i])
          .filter(([parts]) => parts.length)
          .map(([parts, i]) => {
            if (parts.length < 3) bad.push(fa(i + 1));
            return { id: byWord.get(parts[0]), word: parts[0], answer: parts[1] || "", wrong: parts.slice(2, 5), active: true };
          });
        if (bad.length) {
          msg.replaceChildren(el("span", { class: "msg bad" }, `خط ${bad.join("، ")} کلمه‌ها کامل نیست (حداقل کلمه، معنی و یک گزینه‌ی غلط).`));
          return;
        }
      }
      save.disabled = true;
      try {
        await api(`/api/admin/games/${id}`, { method: "PUT", body });
        msg.replaceChildren(el("span", { class: "msg ok" }, "ذخیره شد ✓"));
        setTimeout(() => gameView(id), 700);
      } catch (err) {
        msg.replaceChildren(el("span", { class: "msg bad" }, err.message));
      } finally {
        save.disabled = false;
      }
    });

    async function removeGame() {
      if (!confirm(`«${game.title}» حذف شود؟`)) return;
      try {
        await api(`/api/admin/games/${id}`, { method: "DELETE" });
        location.hash = "#/games";
      } catch (err) {
        msg.replaceChildren(el("span", { class: "msg bad" }, err.message));
      }
    }

    shell("#/games", form);
  }

  // ------------------------------------------------------------ plays

  async function playsView() {
    loading("#/plays");
    let games;
    try { games = await api("/api/admin/games"); } catch (e) { return fail("#/plays", e); }
    const state = { game_id: "", status: "", q: "", offset: 0 };
    const limit = 50;
    const gameSel = el("select", {}, el("option", { value: "" }, "همه‌ی بازی‌ها"), games.map((g) => el("option", { value: g.id }, g.title)));
    const statusSel = el("select", {}, el("option", { value: "" }, "همه‌ی وضعیت‌ها"),
      Object.entries(STATUS).map(([k, [v]]) => el("option", { value: k }, v)));
    const search = el("input", { type: "text", placeholder: "جستجوی موبایل یا کد" });
    const csv = el("a", { class: "btn light" }, "دانلود اکسل (CSV)");
    const tbody = el("tbody");
    const pager = el("div", { class: "pager" });

    async function load() {
      const params = new URLSearchParams({ limit, offset: state.offset });
      for (const k of ["game_id", "status", "q"]) if (state[k]) params.set(k, state[k]);
      const csvParams = new URLSearchParams(params);
      csvParams.delete("limit"); csvParams.delete("offset");
      csv.href = `/api/admin/plays.csv?${csvParams}`;
      let data;
      try { data = await api(`/api/admin/plays?${params}`); } catch (e) { return fail("#/plays", e); }
      tbody.replaceChildren(...(data.items.length ? data.items.map((p) => el("tr", {},
        el("td", {}, jalaliDate(p.created_at, true)), el("td", {}, p.game),
        el("td", { class: "ltr" }, fa(p.mobile)), el("td", {}, badge(p.status)),
        el("td", {}, p.prize_label || "—"),
        el("td", { class: "mono ltr" }, p.code || "—"),
        el("td", {}, p.valid_until ? jalaliDate(p.valid_until) : "—"),
        el("td", {}, p.total ? `${fa(p.score ?? "—")}/${fa(p.total)}` : "—"),
        el("td", { class: "small muted", title: p.error || "" }, p.error ? p.error.slice(0, 30) : ""))) :
        [el("tr", {}, el("td", { colspan: 9, class: "muted" }, "موردی پیدا نشد."))]));
      const pages = Math.max(1, Math.ceil(data.total / limit));
      const page = Math.floor(state.offset / limit) + 1;
      pager.replaceChildren(
        el("button", { class: "btn light", disabled: page <= 1, onclick: () => { state.offset -= limit; load(); } }, "قبلی"),
        el("span", { class: "muted" }, `صفحه‌ی ${fa(page)} از ${fa(pages)} · ${fa(data.total)} مورد`),
        el("button", { class: "btn light", disabled: page >= pages, onclick: () => { state.offset += limit; load(); } }, "بعدی"));
    }
    gameSel.addEventListener("change", () => { state.game_id = gameSel.value; state.offset = 0; load(); });
    statusSel.addEventListener("change", () => { state.status = statusSel.value; state.offset = 0; load(); });
    let timer;
    search.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { state.q = search.value.trim(); state.offset = 0; load(); }, 350); });

    shell("#/plays",
      el("h1", {}, "بازی‌کنندگان و کدها"),
      el("div", { class: "card" },
        el("div", { class: "row", style: "margin-bottom:12px" },
          el("div", { style: "flex:1;min-width:150px" }, gameSel), el("div", { style: "flex:1;min-width:150px" }, statusSel),
          el("div", { style: "flex:2;min-width:180px" }, search), csv),
        el("div", { class: "table-wrap" }, el("table", {},
          el("thead", {}, el("tr", {}, ["زمان", "بازی", "موبایل", "وضعیت", "جایزه", "کد", "اعتبار تا", "امتیاز", "توضیح"].map((h) => el("th", {}, h)))),
          tbody)),
        pager));
    load();
  }

  // ------------------------------------------------------------ settings / API check

  function settingsView() {
    const mobile = el("input", { type: "tel", class: "ltr", placeholder: "09123456789" });
    const amount = el("input", { type: "number", value: 5, min: 1, max: 100 });
    const days = el("input", { type: "number", value: 1, min: 1 });
    const maxAmount = el("input", { type: "number", value: 1000000, min: 1 });
    const out = el("div");
    const btn = el("button", { class: "btn" }, "ساخت یک کد آزمایشی");
    const form = el("form", {},
      el("div", { class: "form-grid" },
        el("label", { class: "f" }, el("span", {}, "موبایل (باید در زبانیاد ثبت‌نام کرده باشد)"), mobile),
        el("label", { class: "f" }, el("span", {}, "درصد تخفیف"), amount),
        el("label", { class: "f" }, el("span", {}, "سقف تخفیف (ریال)"), maxAmount),
        el("label", { class: "f" }, el("span", {}, "اعتبار (روز)"), days)),
      btn, out);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      btn.disabled = true;
      out.replaceChildren();
      try {
        const r = await api("/api/admin/test-code", { method: "POST", body: { mobile: mobile.value, amount: Number(amount.value), max_amount: Number(maxAmount.value) || 1, days: Number(days.value) } });
        loadLog();
        out.replaceChildren(r.ok
          ? el("div", { class: "msg ok" }, `کد ساخته شد: `, el("b", { class: "mono" }, r.code), ` (از ${jalaliDate(r.valid_from, true)} تا ${jalaliDate(r.valid_until, true)})`, r.mode === "mock" ? " — ساختگی، حالت آزمایشی" : "")
          : el("div", { class: "msg bad" }, r.message, r.detail ? el("div", { class: "small ltr" }, r.detail) : ""));
      } catch (err) {
        out.replaceChildren(el("div", { class: "msg bad" }, err.message));
      } finally {
        btn.disabled = false;
      }
    });
    btn.style.marginTop = "12px";

    shell("#/settings",
      el("h1", {}, "اتصال به زبانیاد"),
      el("div", { class: "card" },
        el("table", {}, el("tbody", {},
          el("tr", {}, el("th", {}, "حالت"), el("td", {}, me.mode === "live" ? el("span", { class: "badge ok" }, "واقعی") : el("span", { class: "badge warn" }, "آزمایشی (کد ساختگی)"))),
          el("tr", {}, el("th", {}, "کلید API"), el("td", {}, me.secret_set ? el("span", { class: "badge ok" }, "تنظیم شده") : el("span", { class: "badge bad" }, "تنظیم نشده"))),
          el("tr", {}, el("th", {}, "نشانی API"), el("td", { class: "ltr small" }, me.api_url)),
          el("tr", {}, el("th", {}, "تأیید شماره با پیامک"), el("td", {}, !me.otp_required ? el("span", { class: "badge off" }, "خاموش")
            : me.sms_mode === "mock" ? el("span", { class: "badge warn" }, "روشن، آزمایشی (کد روی صفحه نشان داده می‌شود)")
            : el("span", { class: "badge ok" }, "روشن"))),
          el("tr", {}, el("th", {}, "سایت استفاده از کد"), el("td", { class: "ltr small" }, me.shop_url)))),
        el("p", { class: "muted small" }, "این تنظیمات فقط روی سرور (فایل ‎.env‎) عوض می‌شوند؛ کلید هیچ‌وقت در پنل نشان داده نمی‌شود.")),
      el("div", { class: "card" }, el("h2", {}, "آزمایش ساخت کد"),
        el("p", { class: "note info" }, "در حالت واقعی این دکمه یک کد تخفیف واقعی روی همان شماره در زبانیاد می‌سازد. با شماره‌ی خودتان و درصد کم امتحان کنید."),
        form),
      el("div", { class: "card" },
        el("div", { class: "row between" }, el("h2", {}, "آخرین درخواست‌ها به زبانیاد"),
          el("button", { type: "button", class: "btn light", onclick: () => loadLog() }, "به‌روز کردن")),
        el("p", { class: "muted small" }, "دقیقاً همان چیزی که برای ساخت کد فرستاده شد و جوابی که زبانیاد داد (کلید نشان داده نمی‌شود). برای بررسی مشکل‌ها می‌توانید همین را به تیم بک‌اند نشان دهید."),
        logBox));
    loadLog();
  }

  const logBox = el("div", { class: "table-wrap" });

  async function loadLog() {
    let rows;
    try { rows = await api("/api/admin/api-log"); } catch (e) { logBox.replaceChildren(el("div", { class: "msg bad" }, e.message)); return; }
    if (!rows.length) { logBox.replaceChildren(el("p", { class: "muted" }, "هنوز درخواستی فرستاده نشده.")); return; }
    const status = (r) => r.mode !== "live" ? el("span", { class: "badge warn" }, "آزمایشی")
      : r.status == null ? el("span", { class: "badge bad" }, "بدون اتصال")
      : el("span", { class: `badge ${r.status < 300 ? "ok" : "bad"}` }, String(r.status));
    logBox.replaceChildren(el("table", {},
      el("thead", {}, el("tr", {}, ["زمان", "وضعیت", "فرستاده‌شده", "جواب زبانیاد", "زمان پاسخ"].map((h) => el("th", {}, h)))),
      el("tbody", {}, rows.map((r) => el("tr", {},
        el("td", {}, jalaliDate(r.created_at, true)), el("td", {}, status(r)),
        el("td", { class: "small", style: "white-space:pre-wrap;min-width:260px;direction:ltr;text-align:left;unicode-bidi:isolate" }, prettyJson(r.request)),
        el("td", { class: "small", style: "white-space:pre-wrap;min-width:160px;direction:ltr;text-align:left;unicode-bidi:isolate" }, r.response),
        el("td", { class: "small muted" }, r.ms != null ? `${fa(r.ms)} ms` : ""))))));
  }

  function prettyJson(text) {
    try { return JSON.stringify(JSON.parse(text), null, 1); } catch (e) { return text; }
  }
})();
