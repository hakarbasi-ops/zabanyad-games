// Game page: /g/<slug>. Loads the game, asks for the mobile number, plays, shows the code.
(function () {
  const { fa, jalaliDate, api, el, store, copy } = window.ZG;
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
    if (info.color) document.documentElement.style.setProperty("--brand", info.color);
    document.getElementById("eyebrow").textContent = { wheel: "گردونه شانس", scratch: "کارت خراشی", quiz: "چالش کلمه" }[info.kind] || "";
    document.getElementById("title").textContent = info.title;
    document.getElementById("subtitle").textContent = info.subtitle || "";
    document.getElementById("rules").textContent = info.rules || "";
    if (!info.open) {
      app.replaceChildren(el("div", { class: "closed" }, info.message));
      return;
    }
    ({ wheel: renderWheel, scratch: renderScratch, quiz: renderQuiz })[info.kind]();
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
    if (err.code === "need_signup" && info.signup_url) {
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
    try {
      return { mobile, res: await api(path, { method: "POST", body: { mobile, ...(extraBody || {}) } }) };
    } catch (e) {
      showError(box, e);
      button.disabled = false;
      return null;
    }
  }

  function remember(res, mobile) {
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

  function renderWheel() {
    const slices = info.slices;
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
      const target = 360 - (res.prize_index + 0.5) * seg + jitter;
      rotation = rotation - (rotation % 360) + 360 * 6 + target;
      svg.style.transform = `rotate(${rotation}deg)`;
      button.textContent = "در حال چرخش…";
      const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
      setTimeout(() => {
        remember(res, mobile);
        showResult({ ...res, mobile });
        button.textContent = "بچرخون!";
        button.disabled = false;
      }, reduced ? 1100 : 5400);
    });

    app.replaceChildren(wrap, input, button, box, pastResult() || "");
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
      hint.textContent = "با انگشت روی کارت بکشید 👆";
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
      if (got) runQuiz(got.res, got.mobile);
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

    function updClock() {
      const left = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
      clock.textContent = `${String(Math.floor(left / 60)).padStart(2, "0")}:${String(left % 60).padStart(2, "0")}`;
      clock.classList.toggle("timer-low", left <= 10);
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

  // ------------------------------------------------------------ result

  function showResult(res) {
    const close = () => overlay.remove();
    const body = [];
    if (res.result === "won") {
      const copyBtn = el("button", { type: "button" }, "کپی");
      copyBtn.addEventListener("click", async () => {
        copyBtn.textContent = (await copy(res.code)) ? "کپی شد ✓" : "کپی نشد";
      });
      body.push(
        el("div", { class: "big" }, "🎁"),
        el("h2", {}, `تبریک، ${res.prize_label} بردی!`),
        res.total ? el("div", { class: "pill" }, "امتیاز:", el("span", {}, `${fa(res.score)}/${fa(res.total)}`)) : "",
        el("div", { class: "code-box" }, el("b", {}, res.code), copyBtn),
        el("p", { class: "muted" }, `این کد روی شماره‌ی ${fa(res.mobile || "")} فعال شده و تا ${jalaliDate(res.valid_until)} اعتبار دارد.`),
        el("a", { class: "btn", href: info.shop_url, target: "_blank", rel: "noopener" }, "استفاده از کد در زبانیاد"),
      );
      confetti();
    } else {
      body.push(
        el("div", { class: "big" }, res.late ? "⏰" : "🙂"),
        el("h2", {}, res.late ? "وقت تمام شد!" : (res.prize_label || "این بار نشد!")),
        res.total ? el("div", { class: "pill" }, "امتیاز:", el("span", {}, `${fa(res.score)}/${fa(res.total)}`)) : "",
        el("p", { class: "muted" }, "ممنون که بازی کردی. حتماً به زبانیاد سر بزن!"),
        el("a", { class: "btn", href: info.shop_url, target: "_blank", rel: "noopener" }, "رفتن به زبانیاد"),
      );
    }
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
