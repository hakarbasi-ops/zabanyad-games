# Zabanyad discount games — notes for Claude Code

Eight games: wheel of fortune, scratch card, chest (pick 1 of 3), slot machine, English word quiz, hidden word (Wordle-style), Black Friday vault, Black Friday wheel that give Zabanyad users a real discount code
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

## Games (v7)
- Chance games (`games.CHANCE_KINDS` wheel/scratch/chest/slot) all go through `play_chance` (weights); scored games
  (`SCORED_KINDS` quiz/wordle) through `_finish_scored` (best prize whose min_score the score reaches).
- Hidden word (`kind=wordle`, slug hidden-word): Persian meaning shown as hint, 6 guesses, server holds the word and
  answers each guess (`/wordle/start`, `/wordle/guess`, feedback correct/present/absent); score = 7 − guesses when
  solved, 0 when not (still 10%). Words = questions rows (word 4-6 latin letters | meaning, no wrong options).
- Chest/slot: purely visual over the drawn prize (other chests show random labels; slot reels land on the prize).
- Built-in games added in later versions appear on old installs disabled (`db.add_missing_games`); prize plans are
  applied once per game (`settings` key `prize_plan:<slug>`), never touching games the owner already edited.
- Pictures (v11, owner asked to drop Apple emoji): drawn SVG illustrations in `static/img/art/` (wheel, bf-wheel, ticket,
  quiz, chest, slot, wordle, vault, gift, trophy, clock, smile, medal-gold/silver/bronze; brand palette) via `ZG.art(name, cls)`,
  and small line icons via `ZG.icon(name)` (common.js ICONS: ticket, gift, play, sound, mute, hourglass, flame, sparkle, lock,
  trophy; take the text colour). Pages carry `<meta name="zg-version">` so art URLs get ?v= too. Admin panel still uses emoji.
- Sounds: `static/js/sound.js` (Web Audio, generated; `ZG.sfx.*`, mute in header, `zg:muted`). Header shows the
  signed-in mobile + «خروج» + mute (`otp.js renderHeader`). «وارد کردن کد در زبانیاد» → `CODE_URL`
  (default https://zabanyad.com/install; owner said he'd confirm the address).

## Black Friday vault (v8, kind=vault, slug black-friday; owner approved the scenario)
- Crack a 4-digit code (distinct digits, 6 guesses, 10 min; server holds it, feedback = `wordle_feedback`) → tier:
  solved ≤ gold_max (3) gold, ≤ silver_max (5) silver, else bronze (never empty). prize.min_score = tier (1/2/3); the prize
  is a weighted draw inside the tier (`games._finish_vault`); a sold-out tier falls back to the tier below.
  Plan `db.VAULT_PLAN`: bronze 20%(80)/30%(20); silver 30%(60)/40%(30)/50%(10); gold 50%(70)/70%(28)/90%(2, stock 10).
- Event: seeded ENABLED with starts_at 2026-11-23 00:00 (2 Azar) / ends_at 2026-11-29 23:59 (8 Azar); before the start the
  home card says «به‌زودی» and the game page shows a countdown (`settings.teaser`). Golden hour 20–22 (`golden_from/to`):
  every prize above the tier's smallest gets ×`golden_boost` (2). `bonus_date` 2026-11-27 (Friday 6 Azar) +`bonus_chances` 1
  added to that day's chance (`wallet.bonus_today`). Live winners ticker + stock badges: `GET /api/games/{slug}/winners`.
  API: `/vault/start`, `/vault/guess`. Page: dark/gold `.theme-bf` (game.css), `renderVault` in play.js, sfx dial/unlock.
  Panel: tier select per prize, «تنظیمات جمعه سیاه» card. Not answered by the owner yet (defaults used): dates, 90% stock,
  whether game codes stack with Zabanyad's own Black Friday discount (ask the backend team).

## Black Friday wheel (v9, slug black-friday-wheel, kind wheel; marketing spec approved by the owner)
- 5–7 Azar (2026-11-26 00:00 → 11-28 23:59). Generic game settings it uses (any game can): `theme: "bf"` (dark/gold page,
  event strip, ticker), `own_spins` (daily spins counted per game instead of the shared wallet; `bonus_date`+`bonus_spins` =
  Friday 2 spins; plays with status need_signup/error do not count), `code_until` (every code ends 9 Azar 23:59 instead of
  code_valid_days), `slice_repeat` 2 (8 slices = each prize twice; the page picks a copy), `golden_from/to` + per-prize
  `prizes.golden_weight` (weights 60/25/13/2 → 45/30/20/5 at 20–22), `jackpot_days` (cumulative day caps for stocked prizes:
  26th 3, 27th 4, 28th 3 = 10; also on the vault, so the 90% exists only on 5–7 Azar), `show_left_below` 4, `focus` +
  `focus_keep` ["black-friday"] + `focus_message` (while open, /api/games lists only those and other games refuse plays),
  `buy_url` (zabanyad.com/sub) + `store_links` (default one link to zabanyad.com/links: the sandbox cannot reach zabanyad.com,
  the three store links are to be typed in the panel). `GET /api/jackpot-winners` = «برنده‌های ۹۰٪» board (home + bf pages).
  Tracking: `?utm_source=` kept 7 days (common.js `ZG.src`), sent as `src` → `plays.source`; `POST /api/visit` counts page
  views per day/page/source (table visits); `GET /api/admin/games/{id}/report` (daily: visits, plays, codes per prize,
  sources, need_signup, signed up after the prompt) shown under every game in the panel; CSV has a «منبع» column.
- Not possible on our side (tell marketing): code prefix BFW- (Zabanyad makes the code text), «all plans» and «no stacking»
  (Zabanyad backend rules), «codes used in purchase» (only Nova knows). Spec said «یکشنبه ۹ آذر» but 9 Azar 1405 is Monday;
  kept 9 Azar (code_until) — owner may change it to 8 Azar in the panel.
- Vault (v8) now ends 7 Azar too (`db.black_friday_v9` moves 11-29 → 11-28 once on old installs and adds jackpot_days).
- Marketing guide for both games: `docs/black-friday-fa.md`.

## Allowed percentages (v12, owner: store SKUs)
Zabanyad's discounts exist in the app stores only as 10/20/30/40/50/90%: `db.ALLOWED_PERCENTS`; the panel refuses any
other percentage (prizes and the test-code form, now a select). `db.allowed_percents_v12` (once): vault gold 70% removed,
its weight moved to gold 50% (gold = 50 (98) + 90 (2)); the BF wheel, if still on the v9 plan 50/60/70/90, becomes
`BF_WHEEL_PLAN` 30/40/50/90 = weights 60/28/10/2, golden 45/32/18/5 (owner chose it; min 30% even though Mark's spec
wanted ≥ the campaign's 50%). Vault plan in the section above is outdated on the gold tier.
v13: every code is single use (owner: one subscription purchase): `_issue` always sends usage_count 1, the panel
shows «۱ بار» instead of an input and saves 1.

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
Caching: nginx sends /static/ with `expires 7d` (Cloudflare caches .js/.css too). v9 shipped without busting and the new
pages ran the old cached common.js → empty home page. Since v10 `main._page` serves every HTML page with `?v=<VERSION>` on
each /static .js/.css link and `Cache-Control: no-cache`: ALWAYS bump app/VERSION on a release, or browsers keep old files.
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
