# Zabanyad discount games — notes for Claude Code

Small games (wheel of fortune, scratch card, English word quiz) that give Zabanyad users a real discount code
when they win. Owner is non-technical: reply in Persian, plain words. All UI text Persian, RTL, Persian digits
(`ZG.fa`), Jalali dates (`ZG.jalaliDate`).

## Layout
- `app/` FastAPI + SQLite (stdlib sqlite3, no ORM). `db.py` schema (CREATE IF NOT EXISTS; add columns with ALTER in
  `init()` if needed) + seed of the 3 games. `games.py` all play logic; `discount.py` Zabanyad API client;
  `admin.py` panel API (password `ADMIN_PASSWORD`, signed cookie); `main.py` routes.
- `static/` plain JS, no build: `play.html`+`js/play.js` (all three games), `index.html`, `admin/` panel.
- Tests: `pytest` (mock discount mode, temp DATA_DIR).

## Design
Follows the Zabanyad app's Figma design system (file WDJnVGefUtwnVJ91J4AgAm, page "Design System" 5633:11079,
Farsi app screens 14240:65435): brand #F26600 (darker #572401, lighter #FCE0CC, subtle #F7A366), info #33357D,
success #06C270, warning #FFCC00, error #FF3B3B, darks #212228/#3A4046/#6B7588, light bg #F9FAFF; font Vazir
(we ship Vazirmatn). Patterns copied from the app: white app bar, orange 8px-radius buttons with a darker 4px bottom
edge, outlined answer buttons that turn dark #3A4046 when picked, orange progress bar + mm:ss timer (placement
test), result as a bottom sheet (Daily Gift), score pill on #FCE0CC, gradient cards (Levels row).
Tokens are at the top of `static/css/game.css` and `static/admin/admin.css`; logo `static/img/logo-mark.png`.

## Discount API (from Zabanyad backend)
POST `DISCOUNT_API_URL` (host confirmed api.zabanyad.com; path `/api/v1/discount/generateDiscountForUser` assumed from the doc's `comapi` typo),
headers `Content-Type: application/json`, `X-Client-Secret`. Body: mobile, email "", type percentage|amount,
amount, max_amount, usage_count, start_date/end_date `YYYY-MM-DD HH:mm:ss` (Tehran). 201 → `{promotion_code}`;
401 bad secret, 404 user not found (→ "sign up first", play not counted, prize stock released), 500.
Amounts are RIALS (confirmed); the panel shows the toman value under each amount. Server check (v3): URL correct
(POST without secret → 401), mode live, secret set; yet the first real test code was "not valid" in the app. v4: start_date =
yesterday 00:00 Tehran (in case Zabanyad reads dates as UTC), percentage prizes need max_amount > 0 (0 may mean a 0-rial
cap; test form used to send 0), and every API call is logged in `api_log` (body + status + response, never the secret),
shown on the panel's «اتصال به زبانیاد» page. Ask the backend team about timezone / validity if it still fails. Prize labels shown to players may say toman.

## SMS verification (`app/otp.py`, `app/sms.py`)
Each player's mobile is confirmed by SMS before playing. `/api/otp/send` → 5-digit code (2 min, resend after 60 s,
5/hour per mobile, 20/hour per IP, 5 wrong tries), `/api/otp/verify` → signed token (30 days, the player's sign-in on
that browser) bound to the mobile; play/quiz-start/me/my-codes require it when `OTP_REQUIRED=1`.
Real SMS = Kavenegar Verify Lookup (Zabanyad's provider): `KAVENEGAR_API_KEY` + `KAVENEGAR_TEMPLATE` (a template with
%token, made in the Kavenegar panel), typed on the server with `set-credentials.sh` → `SMS_MODE=kavenegar`. Every send
is logged in `api_log` (mode "sms", receptor + template + Kavenegar status; never the key, which is in the URL path).
A failed send deletes its otp row (no resend wait). `SMS_MODE=mock` shows the code on the page (testing).
Front end: `static/js/otp.js` (`ZG.verifyMobile`, `ZG.session`) shared by the game pages and `/my`.
Game pages show a yellow "test mode" notice while `DISCOUNT_MODE=mock` (codes start with T and do not work).

## My codes (`/my`, `POST /api/my-codes`)
Sign in with the SMS code; lists every won code, active ones soonest-to-expire first («امروز آخرین روزه!», «فقط ۲ روز
مونده!»), then expired; buy button → SHOP_URL. Linked from the app bar («کدهای من») and every result sheet.
Out of chances → bottom sheet pushing the invite (when referrals are on) + link to /my.

## Prizes and chances (owner-approved plan, v5)
- Wheel/scratch (6 slices, NO "empty" prize, min 10%): weights per 1000 → 10%:500, 20%:280, 30%:140, 40%:60,
  50%:19, 90%:1 (0.1%, no stock cap). Quiz ladder: 0-1 correct 10%, 2→20, 3→30, 4→40, 5→50. max_amount =
  `db.NO_CAP` 10,000,000 rial (≈ one course; owner wants no cap but the API needs a number). `db.apply_prize_plan`
  installs this once (settings key prize_plan=2) on wheel/scratch/words; old prize rows kept as deleted.
- Chances (`app/wallet.py`, tables players/referrals/settings): new player 3, invited player 3+1=4, +1 per day
  visited (no pile-up), inviter +3 per new verified player (only mobiles that never played; max 10/day; no self-invite).
  Every play costs 1 chance (shared by all games), refunded when the play does not count. Replaces the old per-game
  plays_per_mobile limit (fields hidden in the editor). Referral switch `referral_enabled` stays OFF until real SMS
  exists. Panel tab «شانس‌ها و دعوت». Invite link = `/?r=<ref_code>` (common.js stores it; sent with /api/otp/verify).
  OTP token now lasts 30 days (it is the player's login on that device).

## Production
ArvanCloud server 85.198.52.230 (Ubuntu 24.04, min 1 vCPU / 1 GB / 20 GB), `games.zabanyad.com`. Owner deploys himself as root (scp+ssh from a Mac, files in ~/Downloads; I cannot reach the server): always give commands with root@85.198.52.230, no sudo.
Iranian servers may not reach PyPI/Docker Hub: `deploy/install.sh` installs from `deploy/wheels` (cp312 manylinux;
refresh with `pip download ... --python-version 3.12 --only-binary=:all:` when requirements change) into
/opt/zabanyad-games (.venv, data/, backups/, .env read by the app itself, not systemd). Release = bump `app/VERSION`,
commit, `bash deploy/make-package.sh` → `dist/zabanyad-games-<N>.zip` (single top folder `zabanyad-games/`), send it;
steps for the owner in `docs/deploy-fa.md`. Secrets only via `deploy/set-credentials.sh` on the server.
DNS of zabanyad.com is on CLOUDFLARE (not Arvan). First try gave Cloudflare 521 (SSL mode Full → origin:443 closed,
and/or Iranian server not reachable from abroad). HTTPS: `deploy/enable-https.sh` (Let's Encrypt; webroot, else DNS-01
via a Cloudflare token typed on the server into /root/.secrets/cloudflare.ini). `deploy/nginx-setup.sh` writes
nginx-ssl.conf when /etc/letsencrypt/live/games.zabanyad.com exists, else nginx.conf (snippets: maps + app);
install.sh calls it, so updates keep HTTPS. Visitor IP: CF-Connecting-IP > ar-real-ip > remote_addr.

## Rules
- The server decides every result; the page only animates it. Never send prize odds/answers that let a client choose.
- The secret lives only in `.env` on the server; never in the repo, logs, responses or chat.
- `DISCOUNT_MODE=mock` gives fake `T…` codes for trying things out.
- Plan: may become a multi-business product later (Instagram pages, small shops) — keep the discount provider
  behind `discount.py` and game config per game row.
