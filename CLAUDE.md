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

## Discount API (from Zabanyad backend)
POST `DISCOUNT_API_URL` (`.../api/v1/discount/generateDiscountForUser`; the doc had a typo `comapi`, confirm),
headers `Content-Type: application/json`, `X-Client-Secret`. Body: mobile, email "", type percentage|amount,
amount, max_amount, usage_count, start_date/end_date `YYYY-MM-DD HH:mm:ss` (Tehran). 201 → `{promotion_code}`;
401 bad secret, 404 user not found (→ "sign up first", play not counted, prize stock released), 500.
Amount unit (toman vs rial) not confirmed yet; panel labels say toman.

## Rules
- The server decides every result; the page only animates it. Never send prize odds/answers that let a client choose.
- The secret lives only in `.env` on the server; never in the repo, logs, responses or chat.
- `DISCOUNT_MODE=mock` gives fake `T…` codes for trying things out.
- Plan: may become a multi-business product later (Instagram pages, small shops) — keep the discount provider
  behind `discount.py` and game config per game row.
