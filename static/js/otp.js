// SMS code step shared by the game pages and «کدهای من»: proves the mobile belongs to the player.
// Resolves with a token (kept 30 days in this browser) or null when the player changes the number.
(function () {
  const { fa, api, el, store } = window.ZG;

  function errorBox() {
    return el("div", { class: "error hidden", role: "alert" });
  }

  function showError(box, err) {
    box.replaceChildren(err.message);
    box.classList.remove("hidden");
  }

  /** The saved sign-in on this browser, if still valid: {mobile, token}. */
  function session() {
    const saved = store.get("zg:otp");
    return saved && saved.until > Date.now() + 60000 ? saved : null;
  }

  async function verifyMobile(mobile, { input, button, onError, onWallet }) {
    const saved = store.get("zg:otp");
    if (saved && saved.mobile === mobile && saved.until > Date.now() + 60000) return saved.token;

    let sent;
    try {
      sent = await api("/api/otp/send", { method: "POST", body: { mobile } });
    } catch (e) {
      onError(e);
      return null;
    }

    return new Promise((resolve) => {
      const field = input.closest(".field");
      const code = el("input", {
        class: "input otp-input", type: "text", inputmode: "numeric", autocomplete: "one-time-code",
        maxlength: String(sent.digits || 5), placeholder: "–".repeat(sent.digits || 5),
      });
      const ok = el("button", { class: "btn", type: "button" }, "تأیید و ادامه");
      const resend = el("button", { class: "link", type: "button", disabled: true });
      const change = el("button", { class: "link", type: "button" }, "تغییر شماره");
      const err = errorBox();
      const panel = el("div", { class: "otp" },
        el("p", {}, `کد ${fa(sent.digits || 5)} رقمی‌ای که به ${fa(mobile)} پیامک شد را وارد کنید.`),
        sent.test_code ? el("p", { class: "notice" }, `حالت آزمایشی (بدون پیامک): کد شما ${fa(sent.test_code)}`) : "",
        code, ok, err, el("div", { class: "otp-links" }, resend, change));
      field.after(panel);
      button.classList.add("hidden");
      input.disabled = true;
      code.focus();

      let left = sent.resend_after || 60;
      const timer = setInterval(() => {
        left -= 1;
        resend.disabled = left > 0;
        resend.textContent = left > 0 ? `ارسال دوباره (${fa(left)})` : "ارسال دوباره‌ی کد";
        if (left <= 0) clearInterval(timer);
      }, 1000);
      resend.textContent = `ارسال دوباره (${fa(left)})`;

      const finish = (token) => {
        clearInterval(timer);
        panel.remove();
        button.classList.remove("hidden");
        input.disabled = false;
        resolve(token);
      };
      const submit = async () => {
        err.classList.add("hidden");
        const value = code.value.replace(/[۰-۹]/g, (d) => "۰۱۲۳۴۵۶۷۸۹".indexOf(d)).replace(/\D/g, "");
        if (value.length < (sent.digits || 5)) {
          showError(err, { message: "کد را کامل وارد کنید." });
          return;
        }
        ok.disabled = true;
        try {
          const r = await api("/api/otp/verify", { method: "POST", body: { mobile, code: value, ref: store.get("zg:ref") } });
          store.set("zg:otp", { mobile, token: r.token, until: Date.now() + r.valid_minutes * 60000 });
          renderHeader();
          if (r.wallet && onWallet) onWallet(r.wallet);
          finish(r.token);
        } catch (e) {
          showError(err, e);
          ok.disabled = false;
        }
      };
      ok.addEventListener("click", submit);
      code.addEventListener("keydown", (e) => e.key === "Enter" && submit());
      code.addEventListener("input", () => {
        const digits = code.value.replace(/[۰-۹]/g, (d) => "۰۱۲۳۴۵۶۷۸۹".indexOf(d)).replace(/\D/g, "");
        if (digits.length === (sent.digits || 5)) submit();
      });
      change.addEventListener("click", () => finish(null));
      resend.addEventListener("click", async () => {
        try {
          const again = await api("/api/otp/send", { method: "POST", body: { mobile } });
          if (again.test_code) panel.querySelector(".notice").textContent = `حالت آزمایشی (بدون پیامک): کد شما ${fa(again.test_code)}`;
          left = again.resend_after || 60;
          resend.disabled = true;
        } catch (e) {
          showError(err, e);
        }
      });
    });
  }

  // header: who is signed in + a small «خروج», and the sound on/off switch
  function renderHeader() {
    const bar = document.querySelector(".appbar-inner");
    if (!bar) return;
    bar.querySelectorAll(".acct, .mute").forEach((n) => n.remove());
    const s = session();
    const header = bar.closest(".appbar");
    header.classList.toggle("signed-in", !!s);
    if (s) {
      bar.append(el("span", { class: "acct" },
        el("span", { class: "acct-mobile" }, fa(s.mobile)),
        el("button", { type: "button", class: "acct-out", onclick: () => { signOut(); location.reload(); } }, "خروج")));
    }
    if (window.ZG.sfx) {
      const btn = el("button", { type: "button", class: "mute", "aria-label": "صدا" });
      const paint = () => { btn.textContent = ZG.sfx.isMuted() ? "🔇" : "🔊"; };
      btn.addEventListener("click", () => { ZG.sfx.setMuted(!ZG.sfx.isMuted()); paint(); });
      paint();
      bar.append(btn);
    }
  }

  function signOut() {
    store.set("zg:otp", null);
  }

  window.ZG.verifyMobile = verifyMobile;
  window.ZG.session = session;
  window.ZG.signOut = () => { signOut(); renderHeader(); };
  window.ZG.renderHeader = renderHeader;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", renderHeader);
  else renderHeader();
})();
