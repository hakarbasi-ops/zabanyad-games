// Game page: /g/<slug>. Loads the game, asks for the mobile number, plays, shows the code.
(function () {
  const { fa, jalaliDate, api, el, store, copy, visit, dayName, art, icon } = window.ZG;
  const sfx = window.ZG.sfx;
  const slug = decodeURIComponent(location.pathname.split("/").filter(Boolean).pop() || "");
  const app = document.getElementById("app");
  const storeKey = `zg:last:${slug}`;
  let info = null;

  init();

  async function init() {
    try {
      info = await api(`/api/games/${encodeURIComponent(slug)}`);
    } catch (e) {
      document.getElementById("title").textContent = "بازی پیدا نشد";
      app.replaceChildren(el("div", { class: "closed" }, e.message));
      return;
    }
    document.title = info.title;
    visit(slug);
    if (info.kind === "vault" || info.theme === "bf") {
      document.body.classList.add("theme-bf");
      const meta = document.querySelector('meta[name="theme-color"]');
      if (meta) meta.content = "#0c0c11";
    }
    if (info.color) document.documentElement.style.setProperty("--brand", info.color);
    document.getElementById("eyebrow").textContent = { wheel: "گردونه شانس", scratch: "کارت خراشی", quiz: "چالش کلمه", chest: "صندوق شانس", slot: "ماشین شانس", wordle: "کلمه‌ی مخفی", vault: "ویژه‌ی جمعه سیاه" }[info.kind] || "";
    if (info.theme === "bf") document.getElementById("eyebrow").textContent = "ویژه‌ی جمعه سیاه";
    document.getElementById("title").textContent = info.title;
    document.getElementById("subtitle").textContent = info.subtitle || "";
    document.getElementById("rules").textContent = info.rules || "";
    if (!info.open) {
      if (info.focus) renderFocusNotice();
      else if (info.teaser && info.starts_at && msLeft(info.starts_at) > 0) renderVaultTeaser();
      else app.replaceChildren(el("div", { class: "closed" }, info.message));
      return;
    }
    ({ wheel: renderWheel, scratch: renderScratch, quiz: renderQuiz, chest: renderChest, slot: renderSlot,
       wordle: renderWordle, vault: renderVault })[info.kind]();
    if (info.test_mode) {
      app.before(el("p", { class: "notice" },
        "حالت آزمایشی: کدهای تخفیف این صفحه ساختگی‌اند (با T شروع می‌شوند) و در زبانیاد کار نمی‌کنند."));
    }
    if (!info.own_spins) app.before(walletBar);   // games with their own daily spins do not use the shared chances
    app.after(ZG.activityBoard());
    const saved = store.get("zg:otp");
    if (saved && saved.until > Date.now()) refreshWallet(saved.mobile, saved.token);
  }

  // ------------------------------------------------------------ chances + invites

  const walletBar = el("div", { class: "wallet hidden" });
  let wallet = null;

  async function refreshWallet(mobile, token) {
    try {
      showWallet(await api("/api/me", { method: "POST", body: { mobile, otp_token: token } }));
    } catch (e) {
      if (e.code === "need_otp") store.set("zg:otp", null);
    }
  }

  function showWallet(w) {
    wallet = { ...(wallet || {}), ...w };
    const n = wallet.chances;
    walletBar.replaceChildren(
      el("div", { class: "wallet-count" }, el("span", { class: "wallet-icon" }, art("ticket", "wallet-art")),
        n > 0 ? el("span", {}, el("b", {}, fa(n)), " شانس داری") : el("span", {}, "شانست تموم شد؛ فردا یه شانس تازه داری")),
      wallet.referral_enabled ? el("button", { class: "wallet-invite", type: "button", onclick: showInvite }, icon("gift"), " دعوت دوستان") : "");
    walletBar.classList.remove("hidden");
  }

  // out of chances: push the invite, the only way to play again today
  function showOutOfChances(message) {
    const close = () => overlay.remove();
    const canInvite = wallet && wallet.referral_enabled && wallet.ref_code;
    const overlay = el("div", { class: "overlay", onclick: (e) => e.target === overlay && close() },
      el("div", { class: "sheet", role: "dialog", "aria-modal": "true" },
        art("ticket", "art-big"),
        el("h2", {}, "شانس‌های امروزت تموم شد!"),
        el("p", {}, canInvite
          ? `می‌خوای همین الان دوباره بازی کنی؟ هر دوستی که دعوت کنی، ${fa(wallet.referral_reward)} شانس تازه برات میاره.`
          : (message || "فردا یه شانس تازه داری.")),
        canInvite ? el("button", { class: "btn", type: "button", onclick: () => { close(); showInvite(); } }, icon("gift"), " دعوت دوستان و گرفتن شانس") : "",
        el("a", { class: "btn outline", href: "/my" }, "دیدن کدهای تخفیف من"),
        el("button", { class: "link", type: "button", onclick: close }, "فردا برمی‌گردم")));
    document.body.append(overlay);
  }

  function showInvite() {
    if (!wallet || !wallet.ref_code) return;
    const link = `${location.origin}/?r=${wallet.ref_code}`;
    const text = `با این لینک وارد بازی‌های زبانیاد شو، ${fa(wallet.invitee_chances)} شانس هدیه بگیر و کد تخفیف ببر! ${link}`;
    const close = () => overlay.remove();
    const copyBtn = el("button", { type: "button" }, "کپی");
    copyBtn.addEventListener("click", async () => { copyBtn.textContent = (await copy(link)) ? "کپی شد ✓" : "کپی نشد"; });
    const share = navigator.share ? el("button", { class: "btn", type: "button",
      onclick: () => navigator.share({ title: "بازی‌های زبانیاد", text, url: link }).catch(() => {}) }, "اشتراک‌گذاری لینک") : "";
    const overlay = el("div", { class: "overlay", onclick: (e) => e.target === overlay && close() },
      el("div", { class: "sheet", role: "dialog", "aria-modal": "true" },
        art("gift", "art-big"),
        el("h2", {}, "دوستات رو دعوت کن، شانس هدیه بگیر!"),
        el("p", {}, `هر دوستی که با لینک تو بیاد و شماره‌اش رو تأیید کنه، ${fa(wallet.referral_reward)} شانس برای تو و ${fa(wallet.invitee_chances)} شانس برای خودش.`),
        el("div", { class: "code-box" }, el("b", { class: "link-text" }, link), copyBtn),
        wallet.invites ? el("p", { class: "muted" }, `تا الان ${fa(wallet.invites)} نفر رو دعوت کردی.`) : "",
        share,
        el("a", { class: "btn outline", href: `https://wa.me/?text=${encodeURIComponent(text)}`, target: "_blank", rel: "noopener" }, "ارسال در واتس‌اپ"),
        el("a", { class: "btn outline", href: `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text.replace(link, ""))}`, target: "_blank", rel: "noopener" }, "ارسال در تلگرام"),
        el("button", { class: "link", type: "button", onclick: close }, "بستن")));
    document.body.append(overlay);
  }

  // ------------------------------------------------------------ shared pieces

  function mobileField(id) {
    const saved = (store.get("zg:mobile") || "");
    return el("div", { class: "field" },
      el("label", { for: id }, "شماره موبایلی که با آن در زبانیاد ثبت‌نام کرده‌اید"),
      el("input", {
        class: "input", id, type: "tel", inputmode: "numeric", autocomplete: "tel",
        placeholder: "۰۹۱۲۳۴۵۶۷۸۹", maxlength: "14", value: saved,
      }));
  }

  function readMobile(input) {
    const digits = input.value.replace(/[۰-۹]/g, (d) => "۰۱۲۳۴۵۶۷۸۹".indexOf(d)).replace(/[٠-٩]/g, (d) => "٠١٢٣٤٥٦٧٨٩".indexOf(d));
    const clean = digits.replace(/[\s\-()]/g, "").replace(/^(\+98|0098)/, "0").replace(/^9(\d{9})$/, "09$1");
    return /^09\d{9}$/.test(clean) ? clean : null;
  }

  function errorBox() {
    return el("div", { class: "error hidden", role: "alert" });
  }

  function showError(box, err) {
    box.replaceChildren(err.message);
    if (err.code === "need_signup" && (info.store_links || []).length) {
      box.append(el("div", { class: "store-row" }, info.store_links.map((l) =>
        el("a", { href: l.url, target: "_blank", rel: "noopener" }, `${l.label} ←`))));
    } else if (err.code === "need_signup" && info.signup_url) {
      box.append(" ", el("a", { href: info.signup_url, target: "_blank", rel: "noopener" }, "ثبت‌نام در زبانیاد ←"));
    }
    box.classList.remove("hidden");
  }

  function pastResult() {
    const last = store.get(storeKey);
    if (!last || last.result !== "won") return null;
    return el("button", { class: "btn outline", type: "button", onclick: () => showResult(last) }, "دیدن دوباره‌ی کد تخفیفم");
  }

  async function start(input, box, button, path, extraBody) {
    box.classList.add("hidden");
    const mobile = readMobile(input);
    if (!mobile) {
      showError(box, { message: "شماره موبایل درست نیست. مثل ۰۹۱۲۳۴۵۶۷۸۹ وارد کنید." });
      input.focus();
      return null;
    }
    store.set("zg:mobile", mobile);
    button.disabled = true;
    let otp_token = null;
    if (info.otp) {
      otp_token = await ZG.verifyMobile(mobile, {
        input, button, onError: (e) => showError(box, e), onWallet: (w) => showWallet(w),
      });
      if (!otp_token) {
        button.disabled = false;
        return null;
      }
    }
    try {
      return { mobile, res: await api(path, { method: "POST", body: { mobile, otp_token, src: ZG.src(), ...(extraBody || {}) } }) };
    } catch (e) {
      if (e.code === "need_otp") store.set("zg:otp", null);
      if (e.code === "no_chances") {
        if (wallet) showWallet({ chances: 0 });
        showOutOfChances(e.message);
      } else {
        showError(box, e);
      }
      button.disabled = false;
      return null;
    }
  }

  function remember(res, mobile) {
    if (typeof res.chances === "number") {
      if (wallet) showWallet({ chances: res.chances });
      else {
        const saved = store.get("zg:otp");
        refreshWallet(mobile, saved && saved.mobile === mobile ? saved.token : null);
      }
    }
    if (res.result === "won") store.set(storeKey, { ...res, mobile });
  }

  // ------------------------------------------------------------ wheel

  // Brand palette from the Zabanyad design system, used when a prize has no color of its own.
  const SLICE_COLORS = ["#f26600", "#fce0cc", "#33357d", "#f7a366"];

  function sliceColor(s, i) {
    return s.color || SLICE_COLORS[i % SLICE_COLORS.length];
  }

  function textOn(hex) {
    const n = parseInt(hex.slice(1), 16);
    const lum = (0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
    return lum > 0.62 ? "#572401" : "#ffffff";
  }

  // a tick each time a slice edge passes the pointer, read from the live CSS rotation
  function tickWhileSpinning(svg, seg, ms) {
    const until = performance.now() + ms;
    let last = null;
    (function frame(now) {
      const m = getComputedStyle(svg).transform;
      if (m && m !== "none") {
        const [a, b] = m.slice(7, -1).split(",").map(Number);
        const deg = (Math.atan2(b, a) * 180 / Math.PI + 360) % 360;
        const slot = Math.floor(deg / seg);
        if (last !== null && slot !== last) sfx.tick();
        last = slot;
      }
      if (now < until) requestAnimationFrame(frame);
    })(performance.now());
  }

  function renderWheel() {
    const copies = Math.max(1, info.slice_repeat || 1);   // 8 slices on screen = each prize twice
    const slices = Array.from({ length: copies }, () => info.slices).flat().map((s) =>
      s.sold_out ? { ...s, color: "#3a3a44", label: "تمام شد" } : s);
    const n = slices.length;
    const seg = 360 / n;
    const R = 160;
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "-170 -170 340 340");
    svg.setAttribute("class", "wheel");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "گردونه شانس");
    const add = (parent, tag, attrs) => {
      const node = document.createElementNS(ns, tag);
      for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
      parent.append(node);
      return node;
    };
    add(svg, "circle", { r: R + 8, fill: "#212228" });
    const point = (deg, r) => {
      const a = (deg * Math.PI) / 180;
      return [r * Math.sin(a), -r * Math.cos(a)];
    };
    slices.forEach((s, i) => {
      const [x1, y1] = point(i * seg, R);
      const [x2, y2] = point((i + 1) * seg, R);
      add(svg, "path", {
        d: `M0 0 L${x1} ${y1} A${R} ${R} 0 ${seg > 180 ? 1 : 0} 1 ${x2} ${y2} Z`,
        fill: sliceColor(s, i), stroke: "#fff", "stroke-width": 2,
      });
      const mid = (i + 0.5) * seg;
      const g = add(svg, "g", { transform: `rotate(${mid})` });
      const size = Math.max(10, Math.min(16, 150 / Math.max(s.label.length, 1)));
      // labels run along the radius; on the right half turn them the other way so none is upside down
      const t = add(g, "text", {
        x: 0, y: 0, transform: `translate(0 ${-R * 0.6}) rotate(${mid > 0 && mid < 180 ? -90 : 90})`,
        "text-anchor": "middle", direction: "rtl",
        "dominant-baseline": "central", fill: textOn(sliceColor(s, i)), "font-size": size, "font-weight": 800,
        "font-family": "Vazirmatn, Tahoma, sans-serif",
      });
      t.textContent = s.label;
    });
    for (let i = 0; i < n; i++) {
      const [x, y] = point(i * seg, R + 4);
      add(svg, "circle", { cx: x, cy: y, r: 3.5, fill: "#fce0cc" });
    }

    const pointer = el("div", { class: "wheel-pointer", html:
      '<svg viewBox="0 0 34 40"><path d="M17 38 3 12a14 14 0 1 1 28 0Z" fill="#f26600" stroke="#fff" stroke-width="3"/><circle cx="17" cy="13" r="5" fill="#fff"/></svg>' });
    const wrap = el("div", { class: "wheel-wrap" }, pointer, svg,
      el("div", { class: "wheel-hub" }, el("img", { src: "/static/img/logo-mark.png", alt: "زبانیاد" })));
    const input = mobileField("mobile");
    const box = errorBox();
    const button = el("button", { class: "btn", type: "button" }, "بچرخون!");
    let rotation = 0;

    button.addEventListener("click", async () => {
      const got = await start(input.querySelector("input"), box, button, `/api/games/${slug}/play`);
      if (!got) return;
      const { res, mobile } = got;
      const jitter = (Math.random() - 0.5) * seg * 0.6;
      const shown = res.prize_index + info.slices.length * Math.floor(Math.random() * copies);
      const target = 360 - (shown + 0.5) * seg + jitter;
      rotation = rotation - (rotation % 360) + 360 * 6 + target;
      svg.style.transform = `rotate(${rotation}deg)`;
      button.textContent = "در حال چرخش…";
      const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
      sfx.spin();
      tickWhileSpinning(svg, seg, reduced ? 1100 : 5300);
      setTimeout(() => {
        remember(res, mobile);
        showResult({ ...res, mobile });
        button.textContent = "بچرخون!";
        button.disabled = false;
        if (typeof res.spins_left === "number") {
          spinsLine.textContent = res.spins_left > 0 ? `امروز ${fa(res.spins_left)} چرخش دیگه داری.` : "چرخش امروزت رو زدی؛ فردا دوباره بیا.";
        }
      }, reduced ? 1100 : 5400);
    });

    const spinsLine = el("p", { class: "spins-line" });
    if (info.own_spins) {
      const o = info.own_spins;
      spinsLine.textContent = o.bonus && o.bonus_date ? `هر روز ${fa(o.daily)} چرخش، ${dayName(o.bonus_date)} ${fa(o.daily + o.bonus)} چرخش.`
        : `هر روز ${fa(o.daily)} چرخش.`;
    }
    const top = info.theme === "bf" ? eventStrip() : null;
    app.replaceChildren(top ? top.strip : "", wrap, input, button, info.own_spins ? spinsLine : "", box, pastResult() || "",
      top ? winnersTicker(top.badges) : "");
  }

  // ------------------------------------------------------------ scratch card

  function renderScratch() {
    const prize = el("div", { class: "prize" });
    const canvas = el("canvas");
    const card = el("div", { class: "scratch" }, prize, canvas);
    const hint = el("p", { class: "scratch-hint" }, "شماره‌تان را وارد کنید تا کارت فعال شود.");
    const input = mobileField("mobile");
    const box = errorBox();
    const button = el("button", { class: "btn", type: "button" }, "کارت رو فعال کن");
    const form = el("div", {}, input, button, box);
    app.replaceChildren(card, hint, form, pastResult() || "");

    const ctx = canvas.getContext("2d");
    let ready = false, done = false, drawing = false, last = null, moves = 0, result = null;

    function paintCover() {
      const ratio = window.devicePixelRatio || 1;
      const { width, height } = card.getBoundingClientRect();
      canvas.width = width * ratio;
      canvas.height = height * ratio;
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      const grad = ctx.createLinearGradient(0, 0, width, height);
      grad.addColorStop(0, "#f7a366");
      grad.addColorStop(1, "#f26600");
      ctx.globalCompositeOperation = "source-over";
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, width, height);
      ctx.fillStyle = "rgba(255,255,255,.35)";
      for (let i = 0; i < 70; i++) ctx.fillRect(Math.random() * width, Math.random() * height, 2, 2);
      ctx.fillStyle = "#fff";
      ctx.font = "800 22px Vazirmatn, Tahoma, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.direction = "rtl";
      ctx.fillText("اینجا رو بخراش!", width / 2, height / 2);
    }
    document.fonts && document.fonts.ready.then(paintCover);
    paintCover();

    function pos(e) {
      const r = canvas.getBoundingClientRect();
      return [e.clientX - r.left, e.clientY - r.top];
    }
    function scratch(from, to) {
      ctx.globalCompositeOperation = "destination-out";
      ctx.lineWidth = 42;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(...from);
      ctx.lineTo(...to);
      ctx.stroke();
      if (moves % 3 === 0) sfx.scratch();
      if (++moves % 8 === 0) checkCleared();
    }
    function checkCleared() {
      const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);
      let clear = 0, total = 0;
      for (let i = 3; i < data.length; i += 4 * 40) {
        total++;
        if (data[i] < 30) clear++;
      }
      if (clear / total > 0.5) reveal();
    }
    function reveal() {
      if (done) return;
      done = true;
      canvas.style.transition = "opacity .5s";
      canvas.style.opacity = "0";
      setTimeout(() => showResult(result), 600);
    }

    canvas.addEventListener("pointerdown", (e) => {
      if (!ready || done) return;
      drawing = true;
      last = pos(e);
      canvas.setPointerCapture(e.pointerId);
      scratch(last, last);
    });
    canvas.addEventListener("pointermove", (e) => {
      if (!drawing) return;
      const p = pos(e);
      scratch(last, p);
      last = p;
    });
    const stop = () => { drawing = false; };
    canvas.addEventListener("pointerup", stop);
    canvas.addEventListener("pointercancel", stop);

    button.addEventListener("click", async () => {
      const got = await start(input.querySelector("input"), box, button, `/api/games/${slug}/play`);
      if (!got) return;
      result = { ...got.res, mobile: got.mobile };
      remember(got.res, got.mobile);
      prize.replaceChildren(got.res.prize_label,
        el("small", {}, got.res.result === "won" ? "کد تخفیف شما آماده است" : "دفعه‌ی بعد!"));
      ready = true;
      form.classList.add("hidden");
      hint.textContent = "با انگشت روی کارت بکشید";
    });
  }

  // ------------------------------------------------------------ word quiz

  function renderQuiz() {
    const ladder = el("div", { class: "ladder" },
      info.ladder.filter((l) => l.win).map((l) =>
        el("div", {}, el("span", {}, `${fa(l.min_score)} جواب درست`), el("b", {}, l.label))));
    const input = mobileField("mobile");
    const box = errorBox();
    const button = el("button", { class: "btn", type: "button" }, "شروع چالش");
    const intro = el("p", { style: "margin:0;color:var(--dark-3)" },
      `${fa(info.question_count)} کلمه در ${fa(info.time_limit)} ثانیه. معنی درست هر کلمه را انتخاب کنید؛ هرچه جواب درست بیشتر، تخفیف بیشتر.`);
    app.replaceChildren(intro, ladder, input, button, box, pastResult() || "");

    button.addEventListener("click", async () => {
      const got = await start(input.querySelector("input"), box, button, `/api/games/${slug}/quiz/start`);
      if (got) {
        if (wallet && typeof got.res.chances === "number") showWallet({ chances: got.res.chances });
        runQuiz(got.res, got.mobile);
      }
    });
  }

  function runQuiz(run, mobile) {
    const answers = {};
    let index = 0, finished = false;
    const deadline = Date.now() + run.time_limit * 1000;
    const total = run.questions.length;
    const clock = el("span");
    const count = el("span");
    const bar = el("i");
    const head = el("div", { class: "q-head" }, clock, count);
    const word = el("div", { class: "q-word" });
    const options = el("div", { class: "options" });
    app.replaceChildren(head, el("div", { class: "progress" }, bar),
      el("p", { class: "q-label" }, "معنی این کلمه چیه؟"), word, options);

    let lastBeep = null;
    function updClock() {
      const left = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
      clock.textContent = `${String(Math.floor(left / 60)).padStart(2, "0")}:${String(left % 60).padStart(2, "0")}`;
      clock.classList.toggle("timer-low", left <= 10);
      if (left <= 5 && left > 0 && left !== lastBeep) { lastBeep = left; sfx.countdown(); }
      if (left <= 0) finish();
    }
    const tick = setInterval(updClock, 250);
    updClock();

    function show() {
      const q = run.questions[index];
      count.textContent = `${index + 1}/${total}`;
      bar.style.width = `${(index / total) * 100}%`;
      word.textContent = q.word;
      options.replaceChildren(...q.options.map((o) => el("button", {
        class: "option", type: "button",
        onclick: (e) => {
          if (finished) return;
          answers[q.id] = o;
          sfx.tap();
          e.currentTarget.classList.add("picked");
          options.querySelectorAll("button").forEach((b) => (b.disabled = true));
          setTimeout(() => (++index < run.questions.length ? show() : finish()), 220);
        },
      }, o)));
    }

    async function finish() {
      if (finished) return;
      finished = true;
      clearInterval(tick);
      app.replaceChildren(el("div", { class: "closed" }, "در حال بررسی جواب‌ها…"));
      try {
        const res = await api(`/api/games/${slug}/quiz/finish`, { method: "POST", body: { token: run.token, answers } });
        remember(res, mobile);
        showResult({ ...res, mobile });
      } catch (e) {
        const box = errorBox();
        showError(box, e);
        app.replaceChildren(box);
        return;
      }
      renderQuiz();
    }

    show();
  }

  // ------------------------------------------------------------ chest: pick one of three

  function renderChest() {
    const chests = el("div", { class: "chests" });
    const hint = el("p", { class: "scratch-hint" }, "شماره‌ات رو بنویس و یکی از صندوق‌ها رو انتخاب کن.");
    const input = mobileField("mobile");
    const box = errorBox();
    let busy = false;
    const items = [0, 1, 2].map((i) => {
      const c = el("button", { class: "chest", type: "button", "aria-label": `صندوق ${fa(i + 1)}` },
        el("span", { class: "chest-lid" }), el("span", { class: "chest-body" }), el("span", { class: "chest-lock" }),
        el("span", { class: "chest-prize" }));
      c.addEventListener("click", () => pick(i));
      return c;
    });
    chests.append(...items);
    app.replaceChildren(chests, hint, input, box, pastResult() || "");

    async function pick(i) {
      if (busy) return;
      busy = true;
      sfx.tap();
      const got = await start(input.querySelector("input"), box, chests, `/api/games/${slug}/play`);
      if (!got) { busy = false; return; }
      const { res, mobile } = got;
      const chosen = items[i];
      chosen.classList.add("shake");
      setTimeout(() => {
        chosen.classList.remove("shake");
        chosen.classList.add("open", "chosen");
        chosen.querySelector(".chest-prize").textContent = shortLabel(res.prize_label);
        sfx.open();
      }, 700);
      // show what the other boxes held (for fun only; the result was decided by the server)
      const others = info.slices.map((s) => shortLabel(s.label)).filter((l) => l !== shortLabel(res.prize_label));
      setTimeout(() => items.forEach((c, j) => {
        if (j === i) return;
        c.classList.add("open", "dim");
        c.querySelector(".chest-prize").textContent = others[(Math.random() * others.length) | 0] || "۱۰٪";
      }), 1500);
      setTimeout(() => {
        remember(res, mobile);
        showResult({ ...res, mobile });
        busy = false;
        setTimeout(() => items.forEach((c) => { c.className = "chest"; c.querySelector(".chest-prize").textContent = ""; }), 400);
      }, 2600);
    }
  }

  function shortLabel(label) {
    return String(label || "").split(" ")[0];
  }

  // ------------------------------------------------------------ slot machine: three reels land on the prize

  function renderSlot() {
    const symbols = info.slices.map((s) => ({ text: shortLabel(s.label), color: s.color || "#f26600" }));
    const N = symbols.length;
    const ROW = 84;
    const reels = [0, 1, 2].map((r) => {
      const strip = el("div", { class: "strip" });
      for (let k = 0; k < 14; k++) {
        symbols.forEach((sym) => strip.append(el("div", { class: "sym", style: `--c:${sym.color}` }, sym.text)));
      }
      const start = (Math.random() * N) | 0;
      strip.style.transform = `translateY(${-start * ROW}px)`;
      strip.dataset.pos = start;
      return { reel: el("div", { class: "reel" }, strip), strip };
    });
    const machine = el("div", { class: "slot-machine" },
      el("div", { class: "slot-top" }, "ماشین شانس زبانیاد"),
      el("div", { class: "reels" }, reels.map((r) => r.reel)),
      el("div", { class: "slot-line" }));
    const input = mobileField("mobile");
    const box = errorBox();
    const button = el("button", { class: "btn", type: "button" }, "اهرم رو بکش!");
    app.replaceChildren(machine, input, button, box, pastResult() || "");

    button.addEventListener("click", async () => {
      sfx.lever();
      const got = await start(input.querySelector("input"), box, button, `/api/games/${slug}/play`);
      if (!got) return;
      const { res, mobile } = got;
      button.textContent = "در حال چرخش…";
      const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
      const ticker = setInterval(() => sfx.reel(), 90);
      const stops = reels.map((r, i) => {
        const dur = reduced ? 0.6 + i * 0.2 : 1.4 + i * 0.6;
        const target = N * (6 + i * 2) + res.prize_index;
        r.strip.style.transition = `transform ${dur}s cubic-bezier(.15,.75,.2,1)`;
        r.strip.style.transform = `translateY(${-target * ROW}px)`;
        return new Promise((ok) => setTimeout(() => {
          sfx.stop();
          r.strip.style.transition = "none";   // jump back to the same symbol near the top for the next spin
          r.strip.style.transform = `translateY(${-res.prize_index * ROW}px)`;
          ok();
        }, dur * 1000));
      });
      await Promise.all(stops);
      clearInterval(ticker);
      machine.classList.add("win");
      setTimeout(() => {
        machine.classList.remove("win");
        remember(res, mobile);
        showResult({ ...res, mobile });
        button.textContent = "اهرم رو بکش!";
        button.disabled = false;
      }, 700);
    });
  }

  // ------------------------------------------------------------ hidden word: find the English word for a Persian meaning

  function renderWordle() {
    const ladder = el("div", { class: "ladder" },
      [...info.ladder].sort((a, b) => b.min_score - a.min_score).map((l) =>
        el("div", {}, el("span", {}, l.min_score > 0 ? `${fa(7 - l.min_score)} حدس یا کمتر` : "حتی اگه پیدا نکنی"),
          el("b", {}, l.label))));
    const input = mobileField("mobile");
    const box = errorBox();
    const button = el("button", { class: "btn", type: "button" }, "شروع بازی");
    const intro = el("p", { style: "margin:0;color:var(--dark-3)" },
      `معنی فارسی یک کلمه رو نشونت می‌دیم؛ کلمه‌ی انگلیسیش رو در ${fa(info.max_guesses)} حدس پیدا کن. سبز یعنی حرف درست سر جای درست، زرد یعنی این حرف هست ولی جای دیگه.`);
    app.replaceChildren(intro, ladder, input, button, box, pastResult() || "");
    button.addEventListener("click", async () => {
      sfx.tap();
      const got = await start(input.querySelector("input"), box, button, `/api/games/${slug}/wordle/start`);
      if (!got) return;
      if (wallet && typeof got.res.chances === "number") showWallet({ chances: got.res.chances });
      runWordle(got.res, got.mobile);
    });
  }

  function runWordle(run, mobile) {
    const L = run.length;
    let row = 0, current = "", busy = false, over = false;
    const tiles = [];
    const grid = el("div", { class: "wgrid", style: `--cols:${L}` });
    for (let r = 0; r < run.max_guesses; r++) {
      tiles.push([]);
      for (let c = 0; c < L; c++) {
        const t = el("div", { class: "wtile" });
        tiles[r].push(t);
        grid.append(t);
      }
    }
    const keys = {};
    const kb = el("div", { class: "wkeys" }, ["qwertyuiop", "asdfghjkl", "zxcvbnm"].map((line, i) =>
      el("div", { class: "wrow" },
        i === 2 ? el("button", { type: "button", class: "wkey wide", onclick: submit }, "تأیید") : "",
        [...line].map((ch) => (keys[ch] = el("button", { type: "button", class: "wkey", onclick: () => type(ch) }, ch.toUpperCase()))),
        i === 2 ? el("button", { type: "button", class: "wkey wide", onclick: back, "aria-label": "پاک کردن" }, "⌫") : "")));
    const msg = el("p", { class: "whint-msg" });
    app.replaceChildren(
      el("div", { class: "whint" }, el("span", {}, "معنی این کلمه:"), el("b", {}, run.hint),
        el("small", {}, `${fa(L)} حرف · ${fa(run.max_guesses)} حدس`)),
      grid, msg, kb);

    const onKey = (e) => {
      if (over || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === "Enter") { e.preventDefault(); submit(); }
      else if (e.key === "Backspace") { e.preventDefault(); back(); }
      else if (/^[a-zA-Z]$/.test(e.key)) type(e.key.toLowerCase());
    };
    document.addEventListener("keydown", onKey);

    function paint() {
      tiles[row].forEach((t, i) => { t.textContent = (current[i] || "").toUpperCase(); t.classList.toggle("filled", !!current[i]); });
    }
    function type(ch) {
      if (busy || over || current.length >= L) return;
      current += ch;
      sfx.key();
      paint();
    }
    function back() {
      if (busy || over) return;
      current = current.slice(0, -1);
      paint();
    }
    async function submit() {
      if (busy || over) return;
      if (current.length < L) {
        msg.textContent = `کلمه باید ${fa(L)} حرف باشه.`;
        sfx.bad();
        grid.classList.add("nudge");
        setTimeout(() => grid.classList.remove("nudge"), 400);
        return;
      }
      busy = true;
      msg.textContent = "";
      let res;
      try {
        res = await api(`/api/games/${slug}/wordle/guess`, { method: "POST", body: { token: run.token, guess: current } });
      } catch (e) {
        msg.textContent = e.message;
        busy = false;
        return;
      }
      const order = { absent: 0, present: 1, correct: 2 };
      res.feedback.forEach((f, i) => setTimeout(() => {
        tiles[row][i].classList.add("flip", f);
        sfx.flip();
        const k = keys[current[i]];
        if (k && (order[f] > (order[k.dataset.state] ?? -1))) { k.dataset.state = f; k.className = `wkey ${f}`; }
      }, i * 220));
      const settle = L * 220 + 250;
      setTimeout(() => {
        if (res.done) {
          over = true;
          document.removeEventListener("keydown", onKey);
          if (res.solved) sfx.good();
          remember(res, mobile);
          setTimeout(() => {
            showResult({ ...res, mobile });
            renderWordle();
          }, res.solved ? 600 : 300);
        } else {
          row += 1;
          current = "";
          busy = false;
          msg.textContent = `${fa(info.max_guesses - row)} حدس دیگه داری.`;
        }
      }, settle);
    }
  }


  // ------------------------------------------------------------ Black Friday vault: crack the 4-digit code, open a vault

  const loadedAt = Date.now();
  // event times are Tehran wall-clock strings; count against the server's own clock so a wrong phone clock does not matter
  const wall = (v) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/.exec(v || "");
    return m ? Date.UTC(+m[1], m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0)) : NaN;
  };
  function msLeft(target) {
    return wall(target) - wall(info.server_now) - (Date.now() - loadedAt);
  }
  function hms(ms) {
    const t = Math.max(0, Math.floor(ms / 1000));
    const d = Math.floor(t / 86400), h = Math.floor((t % 86400) / 3600), m = Math.floor((t % 3600) / 60), sec = t % 60;
    return { d, h, m, s: sec };
  }
  const pad = (n) => String(n).padStart(2, "0");
  const TIER_ART = { 3: "medal-gold", 2: "medal-silver", 1: "medal-bronze" };

  function vaultBox(tier) {
    return el("div", { class: `vault t${tier || 3}` },
      el("div", { class: "vault-prize" }),
      el("div", { class: "vault-door" }, el("div", { class: "vault-dial" })));
  }

  function tiersCard() {
    const rule = (t) => t === 3 ? `${fa(1)} تا ${fa(info.gold_max)} حدس`
      : t === 2 ? `${fa(info.gold_max + 1)} تا ${fa(info.silver_max)} حدس` : "حتی اگه پیدا نکنی";
    return el("div", { class: "bf-tiers" }, info.tiers.map((t) =>
      el("div", { class: `bf-tier t${t.tier}` }, art(TIER_ART[t.tier], "tier-art"), el("b", {}, t.name),
        el("small", {}, rule(t.tier)), el("em", {}, t.labels.map(shortLabel).join("، ")))));
  }

  function eventStrip() {
    const strip = el("div", { class: "bf-strip" });
    if (info.ends_at) {
      const clock = el("b");
      const upd = () => {
        const left = msLeft(info.ends_at);
        const t = hms(left);
        clock.replaceChildren(t.d ? `${fa(t.d)} روز و ` : "",
          el("span", { class: "ltr-time" }, fa(`${pad(t.h)}:${pad(t.m)}:${pad(t.s)}`)));
        if (left <= 0) { clearInterval(timer); clock.textContent = "تمام شد"; }
      };
      const timer = setInterval(upd, 1000);
      upd();
      strip.append(el("div", { class: "bf-count" }, el("span", {}, icon("hourglass"), " تا پایان جمعه سیاه"), clock));
    }
    const badges = el("div", { class: "bf-badges" });
    strip.append(badges);
    paintBadges(badges, info.limited, info.golden && info.golden.now);
    return { strip, badges };
  }

  function paintBadges(badges, limited, goldenNow) {
    const g = info.golden;
    const items = [];
    if (g) {
      const more = info.kind === "vault" ? `${fa(g.boost)} برابر` : "بیشتره";
      items.push(goldenNow
        ? el("span", { class: "bf-badge hot" }, `ساعت طلایی! شانس جایزه‌های بزرگ ${more}`)
        : el("span", { class: "bf-badge" }, `ساعت طلایی: هر شب ${fa(g.from)} تا ${fa(g.to)}`));
    }
    const below = info.show_left_below || 0;
    for (const l of limited || []) {
      const name = shortLabel(l.label);
      if (l.left_today === undefined) {
        items.push(l.left > 0 ? el("span", { class: "bf-badge" }, `فقط ${fa(l.left)} کد ${name} مونده`)
          : el("span", { class: "bf-badge off" }, `کدهای ${name} تموم شد`));
      } else if (l.left_today > 0) {
        if (!below || l.left_today <= below) items.push(el("span", { class: "bf-badge" }, `فقط ${fa(l.left_today)} کد ${name} امروز مونده`));
      } else if (l.left > 0 && l.next_day) {
        items.push(el("span", { class: "bf-badge off" }, `کدهای ${name} بعدی: ${dayName(l.next_day)}`));
      } else if (l.left === 0) {
        items.push(el("span", { class: "bf-badge off" }, `کدهای ${name} تموم شد`));
      }
    }
    badges.replaceChildren(...items);
  }

  // last winners scrolling under the game, refreshed every 20 s (also refreshes stock and golden hour)
  function winnersTicker(badges) {
    const track = el("div", { class: "bf-ticker-track" });
    const box = el("div", { class: "bf-ticker hidden" }, track);
    const ago = (s) => s < 60 ? "همین الان" : s < 3600 ? `${fa(Math.floor(s / 60))} دقیقه پیش` : `${fa(Math.floor(s / 3600))} ساعت پیش`;
    async function load() {
      if (!document.body.contains(box)) return clearInterval(timer);
      try {
        const w = await api(`/api/games/${encodeURIComponent(slug)}/winners`);
        if (badges) paintBadges(badges, w.limited, w.golden_now);
        if (!w.winners.length) return;
        track.replaceChildren(...w.winners.map((x) =>
          el("span", {}, icon("sparkle"), " ", el("span", { class: "m" }, fa(x.mobile)), " ", el("b", {}, x.prize), " برد · ", ago(x.ago))));
        track.style.setProperty("--dur", `${Math.max(18, w.winners.length * 5)}s`);
        box.classList.remove("hidden");
      } catch (e) { /* the ticker is decoration only */ }
    }
    const timer = setInterval(load, 20000);
    setTimeout(load, 50);  // after the box is on the page (load stops the timer once the box is gone)
    return box;
  }

  // Black Friday: other games are paused; send the player to the focus game
  function renderFocusNotice() {
    app.replaceChildren(el("div", { class: "bf-teaser" },
      art("bf-wheel", "art-big"),
      el("h3", {}, info.message),
      el("p", {}, "بقیه‌ی بازی‌ها بعد از جمعه سیاه دوباره باز می‌شن."),
      el("a", { class: "btn", href: `/g/${encodeURIComponent(info.focus.slug)}` }, `رفتن به ${info.focus.title}`)));
  }

  function renderVaultTeaser() {
    const units = [["d", "روز"], ["h", "ساعت"], ["m", "دقیقه"], ["s", "ثانیه"]];
    const cells = Object.fromEntries(units.map(([k]) => [k, el("b")]));
    const upd = () => {
      const left = msLeft(info.starts_at);
      if (left <= 0) { clearInterval(timer); location.reload(); return; }
      const t = hms(left);
      for (const [k] of units) cells[k].textContent = fa(pad(t[k]));
    };
    const timer = setInterval(upd, 1000);
    upd();
    const vault = info.kind === "vault";
    app.replaceChildren(el("div", { class: "bf-teaser" },
      art(vault ? "vault" : "bf-wheel", "art-big"),
      el("h3", {}, vault ? "گاوصندوق‌های جمعه سیاه به‌زودی باز می‌شن!" : `${info.title} به‌زودی شروع می‌شه!`),
      el("p", {}, vault ? `از ${jalaliDate(info.starts_at, true)} بیا رمز گاوصندوق رو پیدا کن و تا ۹۰٪ تخفیف ببر.`
        : `از ${dayName(info.starts_at)} ساعت ${fa(info.starts_at.slice(11, 16))} بچرخون و تا ۹۰٪ تخفیف بگیر.`),
      el("div", { class: "bf-clock" }, units.map(([k, label]) => el("div", {}, cells[k], el("small", {}, label))).reverse()),
      vault ? el("div", { style: "margin-top:18px" }, tiersCard()) : "",
      el("a", { class: "btn outline", href: "/" }, "تا اون موقع بقیه‌ی بازی‌ها رو امتحان کن")));
  }

  function renderVault() {
    const { strip, badges } = eventStrip();
    const input = mobileField("mobile");
    const box = errorBox();
    const button = el("button", { class: "btn", type: "button" }, icon("lock"), " رمز رو حدس بزن");
    const intro = el("p", { class: "bf-intro" },
      `رمز گاوصندوق ${fa(info.digits)} رقمه و هیچ رقمی تکرار نمی‌شه. ${fa(info.max_guesses)} حدس داری؛ سبز یعنی رقم درست سر جای درست، زرد یعنی این رقم هست ولی جای دیگه. هرچی زودتر پیدا کنی، گاوصندوق بهتری باز می‌کنی!`);
    app.replaceChildren(strip, vaultBox(3), intro, tiersCard(), input, button, box, pastResult() || "", winnersTicker(badges));
    button.addEventListener("click", async () => {
      sfx.tap();
      const got = await start(input.querySelector("input"), box, button, `/api/games/${slug}/vault/start`);
      if (!got) return;
      if (wallet && typeof got.res.chances === "number") showWallet({ chances: got.res.chances });
      runVault(got.res, got.mobile);
    });
  }

  function runVault(run, mobile) {
    const D = run.digits;
    let row = 0, current = "", busy = false, over = false, turn = 0;
    const tiles = [];
    const grid = el("div", { class: "vgrid" });
    for (let r = 0; r < run.max_guesses; r++) {
      tiles.push([]);
      for (let c = 0; c < D; c++) {
        const t = el("div", { class: "vtile" });
        tiles[r].push(t);
        grid.append(t);
      }
    }
    const vault = vaultBox(3);
    const dial = vault.querySelector(".vault-dial");
    const keys = {};
    const digitKey = (d) => (keys[d] = el("button", { type: "button", class: "vkey", onclick: () => type(d) }, d));
    const kb = el("div", { class: "vkeys" },
      ..."12345".split("").map(digitKey), ..."67890".split("").map(digitKey),
      el("button", { type: "button", class: "vkey wide", onclick: submit }, "تأیید"),
      el("button", { type: "button", class: "vkey back", onclick: back, "aria-label": "پاک کردن" }, "⌫ پاک کن"));
    const counter = el("b");
    const msg = el("p", { class: "vmsg" }, "یه رمز ۴ رقمی بزن.");
    app.replaceChildren(vault,
      el("div", { class: "vhead" }, el("span", {}, `رمز ${fa(D)} رقمی · رقم تکراری نداره`), el("span", {}, "حدس: ", counter)),
      grid, msg, kb);
    const count = () => { counter.textContent = `${fa(Math.min(row + 1, run.max_guesses))}/${fa(run.max_guesses)}`; };
    count();

    const toLatin = (k) => "۰۱۲۳۴۵۶۷۸۹".indexOf(k) >= 0 ? String("۰۱۲۳۴۵۶۷۸۹".indexOf(k)) : k;
    const onKey = (e) => {
      if (over || e.ctrlKey || e.metaKey || e.altKey) return;
      const k = toLatin(e.key);
      // preventDefault: Enter must not also "click" the last tapped on-screen key
      if (e.key === "Enter") { e.preventDefault(); submit(); }
      else if (e.key === "Backspace") { e.preventDefault(); back(); }
      else if (/^\d$/.test(k)) { e.preventDefault(); type(k); }
    };
    document.addEventListener("keydown", onKey);

    function paint() {
      tiles[row].forEach((t, i) => { t.textContent = current[i] || ""; t.classList.toggle("filled", !!current[i]); });
    }
    function type(d) {
      if (busy || over || current.length >= D) return;
      if (current.includes(d)) {
        msg.textContent = "هر رقم فقط یه بار توی رمز هست.";
        sfx.bad();
        return;
      }
      current += d;
      turn += 1;
      dial.style.transform = `rotate(${turn * 36}deg)`;
      sfx.dial();
      paint();
    }
    function back() {
      if (busy || over) return;
      current = current.slice(0, -1);
      paint();
    }
    async function submit() {
      if (busy || over) return;
      if (current.length < D) {
        msg.textContent = `رمز باید ${fa(D)} رقم باشه.`;
        sfx.bad();
        grid.classList.add("nudge");
        setTimeout(() => grid.classList.remove("nudge"), 400);
        return;
      }
      busy = true;
      msg.textContent = "";
      let res;
      try {
        res = await api(`/api/games/${slug}/vault/guess`, { method: "POST", body: { token: run.token, guess: current } });
      } catch (e) {
        msg.textContent = e.message;
        busy = false;
        return;
      }
      const order = { absent: 0, present: 1, correct: 2 };
      res.feedback.forEach((f, i) => setTimeout(() => {
        tiles[row][i].classList.add("flip", f);
        sfx.flip();
        const k = keys[current[i]];
        if (k && (order[f] > (order[k.dataset.state] ?? -1))) { k.dataset.state = f; k.className = `vkey ${f}`; }
      }, i * 220));
      setTimeout(() => {
        if (res.done) {
          over = true;
          document.removeEventListener("keydown", onKey);
          if (res.solved) sfx.good();
          remember(res, mobile);
          setTimeout(() => openVault(res, mobile), res.solved ? 500 : 250);
        } else {
          row += 1;
          current = "";
          busy = false;
          count();
          const left = run.max_guesses - row;
          msg.textContent = row === info.gold_max ? `${fa(left)} حدس دیگه داری؛ از اینجا به بعد گاوصندوق نقره‌ای!`
            : row === info.silver_max ? "آخرین حدس! پیدا نکنی هم گاوصندوق برنزی مال توئه."
            : `${fa(left)} حدس دیگه داری.`;
        }
      }, D * 220 + 250);
    }
  }

  function openVault(res, mobile) {
    const vault = vaultBox(res.tier);
    vault.style.width = "min(240px, 72%)";
    vault.querySelector(".vault-prize").append(
      res.result === "won" ? shortLabel(res.prize_label) : "—", el("small", {}, `گاوصندوق ${res.tier_name || ""}`));
    const title = el("p", { class: "vmsg", style: "font-size:15px;color:#fff;font-weight:700" },
      res.solved ? `رمز رو در ${fa(res.guesses)} حدس پیدا کردی! گاوصندوق ${res.tier_name} داره باز می‌شه…`
        : `رمز ${fa(res.answer || "")} بود. گاوصندوق ${res.tier_name || "برنزی"} داره باز می‌شه…`);
    app.replaceChildren(vault, title, res.golden ? el("p", { class: "vmsg" }, icon("flame"), " ساعت طلایی بود؛ شانس جایزه‌ی بزرگ بیشتر بود!") : "");
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dial = vault.querySelector(".vault-dial");
    vault.classList.add("shake");
    const clicks = setInterval(() => sfx.dial(), 110);
    setTimeout(() => { vault.classList.remove("shake"); dial.style.transform = "rotate(-540deg)"; }, reduced ? 100 : 700);
    setTimeout(() => { clearInterval(clicks); sfx.unlock(); vault.classList.add("open"); }, reduced ? 300 : 1400);
    setTimeout(() => {
      showResult({ ...res, mobile });
      renderVault();
    }, reduced ? 900 : 2700);
  }

  // ------------------------------------------------------------ result

  function percentOf(label) {
    const m = String(label || "").replace(/[۰-۹]/g, (d) => "۰۱۲۳۴۵۶۷۸۹".indexOf(d)).match(/\d+/);
    return m ? Number(m[0]) : 0;
  }

  function scorePill(res) {
    if (res.tier_name) {  // Black Friday vault
      return el("div", {},
        el("div", { class: "pill" }, art(TIER_ART[res.tier], "pill-art"), `گاوصندوق ${res.tier_name}`),
        el("p", { class: "muted" }, res.solved ? `رمز ${fa(res.answer)} رو در ${fa(res.guesses)} حدس پیدا کردی.`
          : `رمز ${fa(res.answer)} بود.`),
        res.earned_tier > res.tier ? el("p", { class: "muted" }, "جایزه‌های گاوصندوق بالاتر تموم شده بود؛ این یکی برات باز شد.") : "");
    }
    if (res.answer) {  // hidden word
      return el("div", {},
        el("div", { class: "pill" }, res.solved ? `پیدا شد در ${fa(res.guesses)} حدس` : "این بار پیدا نشد"),
        el("p", { class: "muted" }, "کلمه: ", el("b", { class: "latin" }, res.answer.toUpperCase()), ` (${res.meaning})`));
    }
    return res.total ? el("div", { class: "pill" }, "امتیاز:", el("span", {}, `${fa(res.score)}/${fa(res.total)}`)) : "";
  }

  function showResult(res) {
    const close = () => overlay.remove();
    if (res.result !== "won") sfx.meh();
    const body = [];
    if (res.result === "won") {
      const copyBtn = el("button", { type: "button" }, "کپی");
      copyBtn.addEventListener("click", async () => {
        copyBtn.textContent = (await copy(res.code)) ? "کپی شد ✓" : "کپی نشد";
      });
      const campaign = !!info.buy_url;
      body.push(
        art(percentOf(res.prize_label) >= 90 ? "trophy" : "gift", "art-big"),
        el("h2", {}, res.answer && !res.solved ? `پیدا نشد، ولی ${res.prize_label} بردی!` : `تبریک، ${res.prize_label} بردی!`),
        scorePill(res),
        campaign ? el("p", {}, "کد شخصی تو:") : "",
        el("div", { class: "code-box" }, el("b", {}, res.code), copyBtn),
        info.test_mode ? el("p", { class: "notice" }, "این کد آزمایشی است و در زبانیاد کار نمی‌کند.") : "",
        campaign
          ? el("p", { class: "muted" }, `تا ${dayName(res.valid_until)} اعتبار داره و فقط با همین شماره (${fa(res.mobile || "")}) کار می‌کنه.`)
          : el("p", { class: "muted" }, `این کد روی شماره‌ی ${fa(res.mobile || "")} فعال شده و تا ${jalaliDate(res.valid_until)} اعتبار دارد.`),
        el("a", { class: "btn", href: info.buy_url || info.shop_url, target: "_blank", rel: "noopener" }, campaign ? "خرید در اپ" : "وارد کردن کد در زبانیاد"),
        campaign && (info.store_links || []).length ? el("div", { class: "store-row" }, info.store_links.map((l) =>
          el("a", { class: "btn outline", href: l.url, target: "_blank", rel: "noopener" }, l.label))) : "",
      );
      confetti();
      sfx.win(percentOf(res.prize_label) >= 40);
    } else {
      body.push(
        art(res.late ? "clock" : "smile", "art-big"),
        el("h2", {}, res.late ? "وقت تمام شد!" : (res.prize_label || "این بار نشد!")),
        scorePill(res),
        el("p", { class: "muted" }, "ممنون که بازی کردی. حتماً به زبانیاد سر بزن!"),
        el("a", { class: "btn", href: info.shop_url, target: "_blank", rel: "noopener" }, "رفتن به زبانیاد"),
      );
    }
    if (wallet && wallet.chances === 0 && wallet.referral_enabled) {
      body.push(el("div", { class: "invite-cta" },
        el("p", {}, `شانس‌هات تموم شد! با دعوت هر دوست ${fa(wallet.referral_reward)} شانس تازه بگیر.`),
        el("button", { class: "btn outline", type: "button", onclick: () => { close(); showInvite(); } }, icon("gift"), " دعوت دوستان")));
    }
    body.push(el("a", { class: "link", href: "/my" }, "همه‌ی کدهای تخفیف من"));
    body.push(el("button", { class: "link", type: "button", onclick: close }, "بستن"));
    const overlay = el("div", { class: "overlay", onclick: (e) => e.target === overlay && close() },
      el("div", { class: "sheet", role: "dialog", "aria-modal": "true" }, body));
    document.body.append(overlay);
  }

  function confetti() {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const canvas = el("canvas", { class: "confetti" });
    document.body.append(canvas);
    const ctx = canvas.getContext("2d");
    const W = (canvas.width = innerWidth), H = (canvas.height = innerHeight);
    const colors = ["#f26600", "#f7a366", "#ffcc00", "#06c270", "#33357d", "#fce0cc"];
    const parts = Array.from({ length: 140 }, () => ({
      x: W / 2, y: H / 3, vx: (Math.random() - 0.5) * 14, vy: Math.random() * -14 - 4,
      s: 5 + Math.random() * 6, c: colors[(Math.random() * colors.length) | 0], r: Math.random() * 6,
    }));
    const t0 = performance.now();
    (function frame(t) {
      ctx.clearRect(0, 0, W, H);
      for (const p of parts) {
        p.vy += 0.4; p.x += p.vx; p.y += p.vy; p.r += 0.2;
        ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.r);
        ctx.fillStyle = p.c; ctx.fillRect(-p.s / 2, -p.s / 4, p.s, p.s / 2); ctx.restore();
      }
      if (t - t0 < 2600) requestAnimationFrame(frame); else canvas.remove();
    })(t0);
  }
})();
