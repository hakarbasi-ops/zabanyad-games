// «کدهای من»: sign in with the SMS code, then every won code with how long it is still valid.
(function () {
  const { fa, jalaliDate, api, el, store, copy } = window.ZG;
  const root = document.getElementById("my");
  const DAY = 86400000;

  start();

  function start() {
    const s = ZG.session();
    if (s) load(s.mobile, s.token);
    else signIn();
  }

  function signIn() {
    const input = el("input", {
      class: "input", id: "mobile", type: "tel", inputmode: "numeric", autocomplete: "tel",
      placeholder: "۰۹۱۲۳۴۵۶۷۸۹", maxlength: "14", value: store.get("zg:mobile") || "",
    });
    const box = el("div", { class: "error hidden", role: "alert" });
    const button = el("button", { class: "btn", type: "button" }, "دریافت کد ورود");
    root.replaceChildren(el("section", { class: "card" },
      el("div", { class: "field", style: "margin-top:0" },
        el("label", { for: "mobile" }, "شماره موبایلی که با آن بازی کرده‌ای"), input),
      button, box));
    button.addEventListener("click", async () => {
      box.classList.add("hidden");
      const mobile = readMobile(input.value);
      if (!mobile) {
        box.replaceChildren("شماره موبایل درست نیست. مثل ۰۹۱۲۳۴۵۶۷۸۹ وارد کنید.");
        box.classList.remove("hidden");
        return;
      }
      store.set("zg:mobile", mobile);
      button.disabled = true;
      const token = await ZG.verifyMobile(mobile, {
        input, button,
        onError: (e) => { box.replaceChildren(e.message); box.classList.remove("hidden"); },
      });
      button.disabled = false;
      if (token) load(mobile, token);
    });
  }

  function readMobile(value) {
    const d = value.replace(/[۰-۹]/g, (c) => "۰۱۲۳۴۵۶۷۸۹".indexOf(c)).replace(/[٠-٩]/g, (c) => "٠١٢٣٤٥٦٧٨٩".indexOf(c));
    const clean = d.replace(/[\s\-()]/g, "").replace(/^(\+98|0098)/, "0").replace(/^9(\d{9})$/, "09$1");
    return /^09\d{9}$/.test(clean) ? clean : null;
  }

  async function load(mobile, token) {
    root.replaceChildren(el("div", { class: "closed" }, "در حال بارگذاری…"));
    let data;
    try {
      data = await api("/api/my-codes", { method: "POST", body: { mobile, otp_token: token } });
    } catch (e) {
      if (e.code === "need_otp") { ZG.signOut(); return signIn(); }
      root.replaceChildren(el("div", { class: "card closed" }, e.message));
      return;
    }
    const w = data.wallet;
    const active = data.codes.filter((c) => !c.expired);
    const expired = data.codes.filter((c) => c.expired);
    root.replaceChildren(
      el("div", { class: "wallet" },
        el("div", { class: "wallet-count" }, el("span", { class: "wallet-icon" }, "🎟️"),
          w.chances > 0 ? el("span", {}, el("b", {}, fa(w.chances)), " شانس داری") : el("span", {}, "فردا یه شانس تازه داری")),
        el("a", { class: "wallet-invite", href: "/" }, w.chances > 0 ? "🎮 بازی کن" : "🎮 بازی‌ها")),
      data.test_mode ? el("p", { class: "notice" }, "حالت آزمایشی: این کدها ساختگی‌اند و در زبانیاد کار نمی‌کنند.") : "",
      active.length
        ? el("div", { class: "codes" }, active.map((c) => codeCard(c, data.shop_url)))
        : el("div", { class: "card closed" }, "هنوز کد فعالی نداری. یه بازی کن و کد تخفیف ببر!",
          el("a", { class: "btn", href: "/" }, "رفتن به بازی‌ها")),
      expired.length ? el("h3", { class: "codes-title" }, "کدهای منقضی‌شده") : "",
      expired.length ? el("div", { class: "codes" }, expired.map((c) => codeCard(c, data.shop_url))) : "",
      el("p", { class: "rules" }, `وارد شده با ${fa(mobile)} · `,
        el("button", { class: "link inline", type: "button", onclick: () => { ZG.signOut(); signIn(); } }, "خروج")),
    );
  }

  function codeCard(c, shopUrl) {
    const end = new Date(c.valid_until.replace(" ", "T") + "+03:30");
    const left = end - Date.now();
    const days = Math.ceil(left / DAY);
    let badge, cls = "";
    if (c.expired) { badge = "منقضی شده"; cls = "off"; }
    else if (left < DAY) { badge = "امروز آخرین روزه!"; cls = "hot"; }
    else if (days <= 2) { badge = `فقط ${fa(days)} روز مونده!`; cls = "hot"; }
    else badge = `${fa(days)} روز مونده`;
    const copyBtn = el("button", { type: "button" }, "کپی");
    copyBtn.addEventListener("click", async () => { copyBtn.textContent = (await copy(c.code)) ? "کپی شد ✓" : "کپی نشد"; });
    return el("article", { class: `code-card ${c.expired ? "expired" : ""}` },
      el("div", { class: "code-head" },
        el("b", {}, c.prize_label),
        el("span", { class: `code-badge ${cls}` }, badge)),
      el("div", { class: "code-box" }, el("b", {}, c.code), c.expired ? "" : copyBtn),
      el("p", { class: "code-meta" }, `${c.game} · اعتبار تا ${jalaliDate(c.valid_until, true)}`),
      c.expired ? "" : el("a", { class: "btn", href: shopUrl, target: "_blank", rel: "noopener" }, "خرید اشتراک با این کد"));
  }
})();
