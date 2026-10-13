"""Admin panel API (/api/admin/...): one password from ADMIN_PASSWORD, signed cookie session."""
import csv
import hmac
import io
import json
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from itsdangerous import BadSignature, TimestampSigner
from pydantic import BaseModel, Field, field_validator

from . import config, db, discount, games, wallet
from .util import TZ, code_validity, normalize_mobile, now_iso, utcnow

router = APIRouter(prefix="/api/admin")
COOKIE = "zg_admin"
SESSION_DAYS = 7
_signer = TimestampSigner(config.SESSION_SECRET, salt="zg-admin")
_login_attempts: dict[str, list[float]] = defaultdict(list)


def client_ip(request: Request) -> str:
    if config.TRUST_PROXY:
        real = request.headers.get("x-real-ip")
        if real:
            return real.strip()
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[-1].strip()
    return request.client.host if request.client else ""


def require_admin(request: Request) -> None:
    token = request.cookies.get(COOKIE, "")
    try:
        _signer.unsign(token, max_age=SESSION_DAYS * 86400)
    except BadSignature:
        raise HTTPException(401, "ابتدا وارد پنل شوید.")


# ---------------------------------------------------------------- auth


class LoginIn(BaseModel):
    password: str


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response):
    if not config.ADMIN_PASSWORD:
        raise HTTPException(503, "رمز پنل روی سرور تنظیم نشده (ADMIN_PASSWORD).")
    ip = client_ip(request)
    now = time.time()
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < 900]
    if len(_login_attempts[ip]) >= 10:
        raise HTTPException(429, "تلاش زیاد بود. ۱۵ دقیقه بعد دوباره امتحان کنید.")
    if not hmac.compare_digest(body.password.encode(), config.ADMIN_PASSWORD.encode()):
        _login_attempts[ip].append(now)
        raise HTTPException(401, "رمز درست نیست.")
    _login_attempts.pop(ip, None)
    response.set_cookie(COOKIE, _signer.sign("admin").decode(), max_age=SESSION_DAYS * 86400,
                        httponly=True, samesite="strict", secure=request.url.scheme == "https"
                        or request.headers.get("x-forwarded-proto") == "https", path="/")
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me", dependencies=[Depends(require_admin)])
def me():
    return {
        "ok": True,
        "mode": discount.mode(),
        "secret_set": bool(config.DISCOUNT_API_SECRET),
        "api_url": config.DISCOUNT_API_URL,
        "shop_url": config.SHOP_URL,
        "otp_required": config.OTP_REQUIRED,
        "sms_mode": config.SMS_MODE,
    }


# ---------------------------------------------------------------- games


class PrizeIn(BaseModel):
    id: int | None = None
    label: str = Field(min_length=1, max_length=40)
    kind: Literal["percentage", "amount", "none"]
    amount: int = Field(0, ge=0)
    max_amount: int = Field(0, ge=0)
    usage_count: int = Field(1, ge=1, le=100)
    weight: int = Field(1, ge=0, le=100000)
    stock: int | None = Field(None, ge=0)
    min_score: int = Field(0, ge=0, le=100)
    color: str = ""
    active: bool = True

    @field_validator("color")
    @classmethod
    def _color(cls, v: str) -> str:
        return v if re.fullmatch(r"#[0-9a-fA-F]{6}", v or "") else ""


class QuestionIn(BaseModel):
    id: int | None = None
    word: str = Field(min_length=1, max_length=80)
    answer: str = Field(min_length=1, max_length=80)
    wrong: list[str] = Field(min_length=1, max_length=3)
    active: bool = True


class GameIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    subtitle: str = Field("", max_length=200)
    rules: str = Field("", max_length=1000)
    enabled: bool = False
    starts_at: str | None = None
    ends_at: str | None = None
    plays_per_mobile: int = Field(1, ge=1, le=1000)
    period_days: int = Field(0, ge=0, le=365)
    code_valid_days: int = Field(7, ge=1, le=365)
    daily_code_limit: int = Field(0, ge=0)
    settings: dict = {}
    prizes: list[PrizeIn] = []
    questions: list[QuestionIn] | None = None


class NewGameIn(BaseModel):
    slug: str
    kind: Literal["wheel", "scratch", "quiz"]
    title: str = Field(min_length=1, max_length=80)


def _game_full(conn, game_id: int) -> dict:
    game = db.row(conn.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone())
    if not game:
        raise HTTPException(404, "بازی پیدا نشد.")
    game["prizes"] = games.prizes_of(conn, game_id, active_only=False)
    if game["kind"] == "quiz":
        game["questions"] = db.rows(conn.execute("SELECT * FROM questions WHERE game_id=? ORDER BY id", (game_id,)))
    return game


def _check_prizes(kind: str, prizes: list[PrizeIn]) -> None:
    active = [p for p in prizes if p.active]
    if kind in ("wheel", "scratch"):
        if len(active) < 2:
            raise HTTPException(400, "حداقل دو گزینه‌ی فعال لازم است.")
        if kind == "wheel" and len(active) > 12:
            raise HTTPException(400, "گردونه حداکثر ۱۲ خانه دارد.")
        if not any(p.weight > 0 for p in active):
            raise HTTPException(400, "حداقل یک گزینه باید شانس بیشتر از صفر داشته باشد.")
    for p in prizes:
        if p.kind == "percentage" and not 1 <= p.amount <= 100:
            raise HTTPException(400, f"«{p.label}»: درصد باید بین ۱ تا ۱۰۰ باشد.")
        if p.kind == "amount" and p.amount <= 0:
            raise HTTPException(400, f"«{p.label}»: مبلغ تخفیف را وارد کنید.")
        if p.kind == "percentage" and p.max_amount <= 0 and p.active:
            raise HTTPException(400, f"«{p.label}»: سقف تخفیف (ریال) را وارد کنید.")


@router.get("/games", dependencies=[Depends(require_admin)])
def list_games():
    with db.session() as conn:
        out = []
        for g in db.rows(conn.execute("SELECT * FROM games ORDER BY id")):
            ok, message = games.availability(g)
            g["open"], g["message"] = ok, message
            g.update(_game_stats(conn, g["id"]))
            out.append(g)
        return out


@router.post("/games", dependencies=[Depends(require_admin)])
def create_game(body: NewGameIn):
    slug = body.slug.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,39}", slug):
        raise HTTPException(400, "نشانی بازی فقط حروف انگلیسی کوچک، عدد و خط تیره (۲ تا ۴۰ حرف).")
    settings = {"question_count": 5, "time_limit": 60} if body.kind == "quiz" else {}
    with db.session() as conn:
        if conn.execute("SELECT 1 FROM games WHERE slug=?", (slug,)).fetchone():
            raise HTTPException(400, "این نشانی قبلاً استفاده شده.")
        cur = conn.execute(
            "INSERT INTO games (slug, kind, title, settings, created_at) VALUES (?,?,?,?,?)",
            (slug, body.kind, body.title, json.dumps(settings), now_iso()))
        gid = cur.lastrowid
        defaults = ([("تلاش خوبی بود!", "none", 0, 0), ("۱۰٪ تخفیف", "percentage", 10, 3)] if body.kind == "quiz"
                    else [("۱۰٪ تخفیف", "percentage", 10, 0), ("پوچ", "none", 0, 0)])
        for i, (label, kind, amount, min_score) in enumerate(defaults):
            conn.execute("INSERT INTO prizes (game_id, label, kind, amount, min_score, color, sort)"
                         " VALUES (?,?,?,?,?,?,?)",
                         (gid, label, kind, amount, min_score, db.DEFAULT_COLORS[i], i))
        return _game_full(conn, gid)


@router.get("/games/{game_id}", dependencies=[Depends(require_admin)])
def get_game(game_id: int):
    with db.session() as conn:
        return _game_full(conn, game_id)


@router.put("/games/{game_id}", dependencies=[Depends(require_admin)])
def update_game(game_id: int, body: GameIn):
    with db.session() as conn:
        game = _game_full(conn, game_id)
        _check_prizes(game["kind"], body.prizes)
        for key in ("starts_at", "ends_at"):
            value = getattr(body, key)
            if value and not games.parse_local(value):
                raise HTTPException(400, "تاریخ شروع/پایان درست نیست.")
        settings = {**game["settings"], **body.settings}
        if game["kind"] == "quiz":
            settings["question_count"] = max(1, min(int(settings.get("question_count", 5)), 20))
            settings["time_limit"] = max(10, min(int(settings.get("time_limit", 60)), 600))
        if "color" in settings and not re.fullmatch(r"#[0-9a-fA-F]{6}", str(settings["color"] or "")):
            settings["color"] = ""

        with db.LOCK, db.transaction(conn):
            conn.execute(
                "UPDATE games SET title=?, subtitle=?, rules=?, enabled=?, starts_at=?, ends_at=?, plays_per_mobile=?,"
                " period_days=?, code_valid_days=?, daily_code_limit=?, settings=? WHERE id=?",
                (body.title, body.subtitle, body.rules, int(body.enabled), body.starts_at or None,
                 body.ends_at or None, body.plays_per_mobile, body.period_days, body.code_valid_days,
                 body.daily_code_limit, json.dumps(settings, ensure_ascii=False), game_id))

            existing = {p["id"] for p in game["prizes"]}
            kept = set()
            for i, p in enumerate(body.prizes):
                values = (p.label, p.kind, p.amount, p.max_amount, p.usage_count, p.weight, p.stock,
                          p.min_score, p.color or db.DEFAULT_COLORS[i % len(db.DEFAULT_COLORS)], i, int(p.active))
                if p.id in existing:
                    kept.add(p.id)
                    conn.execute("UPDATE prizes SET label=?, kind=?, amount=?, max_amount=?, usage_count=?, weight=?,"
                                 " stock=?, min_score=?, color=?, sort=?, active=? WHERE id=?", (*values, p.id))
                else:
                    conn.execute("INSERT INTO prizes (label, kind, amount, max_amount, usage_count, weight, stock,"
                                 " min_score, color, sort, active, game_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                                 (*values, game_id))
            for pid in existing - kept:  # removed rows stay for old plays' history
                conn.execute("UPDATE prizes SET deleted=1, active=0 WHERE id=?", (pid,))

            if game["kind"] == "quiz" and body.questions is not None:
                q_existing = {q["id"] for q in game["questions"]}
                q_kept = set()
                for q in body.questions:
                    wrong = json.dumps([w.strip() for w in q.wrong if w.strip()], ensure_ascii=False)
                    if q.id in q_existing:
                        q_kept.add(q.id)
                        conn.execute("UPDATE questions SET word=?, answer=?, wrong=?, active=? WHERE id=?",
                                     (q.word.strip(), q.answer.strip(), wrong, int(q.active), q.id))
                    else:
                        conn.execute("INSERT INTO questions (game_id, word, answer, wrong, active) VALUES (?,?,?,?,?)",
                                     (game_id, q.word.strip(), q.answer.strip(), wrong, int(q.active)))
                for qid in q_existing - q_kept:
                    conn.execute("UPDATE questions SET active=0 WHERE id=?", (qid,))
                    conn.execute("DELETE FROM questions WHERE id=? AND id NOT IN (SELECT value FROM plays,"
                                 " json_each(json_extract(plays.data, '$.questions')))", (qid,))
        return _game_full(conn, game_id)


@router.delete("/games/{game_id}", dependencies=[Depends(require_admin)])
def delete_game(game_id: int):
    with db.session() as conn:
        if conn.execute("SELECT 1 FROM plays WHERE game_id=? LIMIT 1", (game_id,)).fetchone():
            raise HTTPException(400, "این بازی سابقه‌ی بازی دارد؛ به‌جای حذف، غیرفعالش کنید.")
        with db.transaction(conn):
            conn.execute("DELETE FROM prizes WHERE game_id=?", (game_id,))
            conn.execute("DELETE FROM questions WHERE game_id=?", (game_id,))
            conn.execute("DELETE FROM games WHERE id=?", (game_id,))
        return {"ok": True}


# ---------------------------------------------------------------- reports


def _game_stats(conn, game_id: int) -> dict:
    r = conn.execute(
        "SELECT COUNT(*) FILTER (WHERE status IN ('won','lost')) AS plays,"
        " COUNT(*) FILTER (WHERE status='won') AS codes,"
        " COUNT(*) FILTER (WHERE status='need_signup') AS need_signup,"
        " COUNT(*) FILTER (WHERE status='error') AS errors,"
        " COUNT(DISTINCT mobile) FILTER (WHERE status IN ('won','lost')) AS players"
        " FROM plays WHERE game_id=?", (game_id,)).fetchone()
    return dict(r)


@router.get("/stats", dependencies=[Depends(require_admin)])
def stats(days: int = 14):
    days = max(1, min(days, 90))
    since = (utcnow() - timedelta(days=days + 1)).isoformat(timespec="seconds")
    with db.session() as conn:
        games.expire_stale(conn)
        per_day: dict[str, dict] = {}
        today = datetime.now(TZ).date()
        for i in range(days - 1, -1, -1):
            d = (today - timedelta(days=i)).isoformat()
            per_day[d] = {"day": d, "plays": 0, "codes": 0}
        for r in conn.execute("SELECT status, created_at FROM plays WHERE created_at >= ?"
                              " AND status IN ('won','lost')", (since,)):
            d = datetime.fromisoformat(r["created_at"]).astimezone(TZ).date().isoformat()
            if d in per_day:
                per_day[d]["plays"] += 1
                per_day[d]["codes"] += r["status"] == "won"
        totals = dict(conn.execute(
            "SELECT COUNT(*) FILTER (WHERE status IN ('won','lost')) AS plays,"
            " COUNT(*) FILTER (WHERE status='won') AS codes,"
            " COUNT(*) FILTER (WHERE status='need_signup') AS need_signup,"
            " COUNT(*) FILTER (WHERE status='error') AS errors,"
            " COUNT(DISTINCT mobile) FILTER (WHERE status IN ('won','lost')) AS players FROM plays").fetchone())
        by_prize = db.rows(conn.execute(
            "SELECT g.title AS game, p.label, p.kind, p.amount, p.stock, p.given, p.active,"
            " (SELECT COUNT(*) FROM plays WHERE prize_id=p.id AND status='won') AS won,"
            " (SELECT COUNT(*) FROM plays WHERE prize_id=p.id AND status IN ('won','lost')) AS hits"
            " FROM prizes p JOIN games g ON g.id=p.game_id WHERE p.deleted=0 ORDER BY g.id, p.sort"))
        return {"days": list(per_day.values()), "totals": totals, "by_prize": by_prize}


STATUS_FA = {"won": "برنده", "lost": "بدون جایزه", "need_signup": "ثبت‌نام نکرده", "error": "خطا", "pending": "در حال بازی"}


def _plays_query(game_id: int | None, status: str | None, q: str | None):
    where, params = ["1=1"], []
    if game_id:
        where.append("p.game_id=?")
        params.append(game_id)
    if status:
        where.append("p.status=?")
        params.append(status)
    if q:
        mobile = normalize_mobile(q)
        where.append("(p.mobile LIKE ? OR p.code LIKE ?)")
        params += [f"%{mobile or q.strip()}%", f"%{q.strip().upper()}%"]
    return " AND ".join(where), params


@router.get("/plays", dependencies=[Depends(require_admin)])
def plays(game_id: int | None = None, status: str | None = None, q: str | None = None,
          limit: int = 50, offset: int = 0):
    where, params = _plays_query(game_id, status, q)
    limit = max(1, min(limit, 200))
    with db.session() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM plays p WHERE {where}", params).fetchone()[0]
        items = db.rows(conn.execute(
            f"SELECT p.id, p.mobile, p.status, p.prize_label, p.code, p.valid_until, p.score, p.total, p.error,"
            f" p.created_at, g.title AS game FROM plays p JOIN games g ON g.id=p.game_id WHERE {where}"
            f" ORDER BY p.id DESC LIMIT ? OFFSET ?", [*params, limit, max(offset, 0)]))
        return {"total": total, "items": items}


@router.get("/plays.csv", dependencies=[Depends(require_admin)])
def plays_csv(game_id: int | None = None, status: str | None = None, q: str | None = None):
    where, params = _plays_query(game_id, status, q)
    with db.session() as conn:
        items = db.rows(conn.execute(
            f"SELECT p.*, g.title AS game FROM plays p JOIN games g ON g.id=p.game_id WHERE {where}"
            f" ORDER BY p.id DESC", params))
    buf = io.StringIO()
    buf.write("﻿")  # Excel opens Persian UTF-8 correctly with a BOM
    w = csv.writer(buf)
    w.writerow(["ردیف", "زمان (تهران)", "بازی", "موبایل", "وضعیت", "جایزه", "کد تخفیف", "اعتبار تا", "امتیاز"])
    for p in items:
        when = datetime.fromisoformat(p["created_at"]).astimezone(TZ).strftime("%Y-%m-%d %H:%M")
        score = f"{p['score']}/{p['total']}" if p["score"] is not None else ""
        w.writerow([p["id"], when, p["game"], p["mobile"], STATUS_FA.get(p["status"], p["status"]),
                    p["prize_label"], p["code"] or "", p["valid_until"] or "", score])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": 'attachment; filename="plays.csv"'})


# ---------------------------------------------------------------- API check


class TestCodeIn(BaseModel):
    mobile: str
    type: Literal["percentage", "amount"] = "percentage"
    amount: int = Field(5, ge=1)
    max_amount: int = Field(1_000_000, ge=1)
    days: int = Field(1, ge=1, le=365)


@router.post("/test-code", dependencies=[Depends(require_admin)])
def test_code(body: TestCodeIn):
    """Makes one code through the same API the games use, to check the connection and the secret."""
    mobile = normalize_mobile(body.mobile)
    if not mobile:
        raise HTTPException(400, "شماره موبایل درست نیست.")
    start, end = code_validity(body.days)
    req = discount.CodeRequest(mobile=mobile, type=body.type, amount=body.amount, max_amount=body.max_amount,
                               usage_count=1, start_date=start, end_date=end)
    try:
        code = discount.generate(req)
    except discount.DiscountError as exc:
        messages = {
            "unauthorized": "کلید (Secret) پذیرفته نشد یا روی سرور تنظیم نشده.",
            "user_not_found": "زبانیاد این شماره را پیدا نکرد (۴۰۴). اگر شماره ثبت‌نام کرده، نشانی API را چک کنید.",
            "network": "به سرور زبانیاد وصل نشد.",
            "server": "سرور زبانیاد خطا داد.",
            "bad_response": "جواب سرور زبانیاد کد تخفیف نداشت.",
        }
        return {"ok": False, "kind": exc.kind, "message": messages.get(exc.kind, exc.kind), "detail": exc.detail}
    return {"ok": True, "code": code, "mode": discount.mode(), "valid_from": start, "valid_until": end}


@router.get("/api-log", dependencies=[Depends(require_admin)])
def api_log(limit: int = 30):
    with db.session() as conn:
        return db.rows(conn.execute("SELECT * FROM api_log ORDER BY id DESC LIMIT ?", (max(1, min(limit, 200)),)))


# ---------------------------------------------------------------- chances and invites


@router.get("/chance-settings", dependencies=[Depends(require_admin)])
def get_chance_settings():
    with db.session() as conn:
        return wallet.settings(conn)


@router.put("/chance-settings", dependencies=[Depends(require_admin)])
def put_chance_settings(body: dict):
    try:
        values = {k: int(v) for k, v in body.items() if k in wallet.LIMITS}
    except (TypeError, ValueError):
        raise HTTPException(400, "عددها درست نیستند.")
    with db.session() as conn, db.transaction(conn):
        return wallet.save_settings(conn, values)


class GrantIn(BaseModel):
    mobile: str
    count: int = Field(ge=-100, le=100)


@router.post("/grant-chances", dependencies=[Depends(require_admin)])
def grant_chances(body: GrantIn):
    mobile = normalize_mobile(body.mobile)
    if not mobile:
        raise HTTPException(400, "شماره موبایل درست نیست.")
    with db.session() as conn, db.LOCK, db.transaction(conn):
        player = wallet.grant(conn, mobile, body.count)
    return {"mobile": mobile, "chances": player["chances"]}


@router.get("/referrals", dependencies=[Depends(require_admin)])
def referrals():
    with db.session() as conn:
        top = db.rows(conn.execute(
            "SELECT mobile, invites, chances, ref_code FROM players WHERE invites > 0 ORDER BY invites DESC LIMIT 30"))
        recent = db.rows(conn.execute(
            "SELECT inviter, invitee, reward, created_at FROM referrals ORDER BY id DESC LIMIT 30"))
        totals = dict(conn.execute(
            "SELECT (SELECT COUNT(*) FROM players) AS players, (SELECT COUNT(*) FROM referrals) AS referrals,"
            " (SELECT COALESCE(SUM(chances), 0) FROM players) AS open_chances").fetchone())
    return {"top": top, "recent": recent, "totals": totals}
