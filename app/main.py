"""Zabanyad games: public game pages + admin panel, one FastAPI app."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import admin, config, db, discount, games, otp, wallet
from .util import local_now, normalize_mobile

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

STATIC = config.ROOT / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    with db.session() as conn:
        games.expire_stale(conn)
    yield


app = FastAPI(title="Zabanyad Games", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.include_router(admin.router)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def _no_cache_api(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "private, no-store"
    return response


@app.exception_handler(games.PlayError)
async def _play_error(_: Request, exc: games.PlayError):
    return JSONResponse({"detail": exc.message, "code": exc.code}, status_code=exc.status)


# ---------------------------------------------------------------- pages


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/g/{slug}", include_in_schema=False)
def game_page(slug: str):
    return FileResponse(STATIC / "play.html")


@app.get("/my", include_in_schema=False)
def my_page():
    return FileResponse(STATIC / "my.html")


@app.get("/admin", include_in_schema=False)
def admin_page():
    return FileResponse(STATIC / "admin" / "index.html")


@app.get("/admin/", include_in_schema=False)
def admin_slash():
    return RedirectResponse("/admin")


@app.get("/healthz", include_in_schema=False)
def health():
    return {"ok": True}


# ---------------------------------------------------------------- public API


@app.get("/api/games")
def list_open_games():
    with db.session() as conn:
        out = []
        for g in db.rows(conn.execute("SELECT * FROM games WHERE enabled=1 ORDER BY id")):
            ok, _ = games.availability(g)
            if ok:
                out.append({"slug": g["slug"], "kind": g["kind"], "title": g["title"], "subtitle": g["subtitle"]})
        return {"games": out, "shop_url": config.SHOP_URL}


@app.get("/api/games/{slug}")
def game_info(slug: str):
    with db.session() as conn:
        view = games.public_view(conn, games.get_game(conn, slug))
        return {**view, "shop_url": config.SHOP_URL, "signup_url": config.SIGNUP_URL,
                "otp": otp.required(), "test_mode": discount.mode() == "mock"}


class MobileIn(BaseModel):
    mobile: str
    otp_token: str | None = None


class OtpVerifyIn(BaseModel):
    mobile: str
    code: str
    ref: str | None = None


def _mobile(raw: str) -> str:
    mobile = normalize_mobile(raw)
    if not mobile:
        raise games.PlayError("bad_mobile", "شماره موبایل درست نیست. مثل ۰۹۱۲۳۴۵۶۷۸۹ وارد کنید.")
    return mobile


@app.post("/api/otp/send")
def otp_send(body: MobileIn, request: Request):
    return otp.send(_mobile(body.mobile), admin.client_ip(request))


@app.post("/api/otp/verify")
def otp_verify(body: OtpVerifyIn):
    return otp.verify(_mobile(body.mobile), body.code, body.ref)


@app.post("/api/me")
def me(body: MobileIn):
    """The player's chances and invite code (also adds today's chance)."""
    mobile = _mobile(body.mobile)
    otp.check(mobile, body.otp_token)
    with db.session() as conn, db.LOCK, db.transaction(conn):
        return wallet.view(conn, wallet.ensure(conn, mobile))


@app.post("/api/my-codes")
def my_codes(body: MobileIn):
    """Every code this mobile has won, the soonest to expire first, then the expired ones."""
    mobile = _mobile(body.mobile)
    otp.check(mobile, body.otp_token)
    now = local_now().strftime("%Y-%m-%d %H:%M:%S")
    with db.session() as conn:
        rows = db.rows(conn.execute(
            "SELECT p.id, p.prize_label, p.code, p.valid_until, p.created_at, g.title AS game, g.kind"
            " FROM plays p JOIN games g ON g.id=p.game_id WHERE p.mobile=? AND p.status='won' AND p.code IS NOT NULL",
            (mobile,)))
        with db.LOCK, db.transaction(conn):
            view = wallet.view(conn, wallet.ensure(conn, mobile))
    active = sorted((r for r in rows if (r["valid_until"] or "") >= now), key=lambda r: r["valid_until"])
    expired = sorted((r for r in rows if (r["valid_until"] or "") < now), key=lambda r: r["valid_until"] or "",
                     reverse=True)
    for r in active:
        r["expired"] = False
    for r in expired:
        r["expired"] = True
    return {"codes": active + expired, "wallet": view, "shop_url": config.SHOP_URL,
            "test_mode": discount.mode() == "mock"}


@app.post("/api/games/{slug}/play")
def play(slug: str, body: MobileIn, request: Request):
    mobile = _mobile(body.mobile)
    otp.check(mobile, body.otp_token)
    with db.session() as conn:
        return games.play_chance(conn, slug, mobile, admin.client_ip(request))


@app.post("/api/games/{slug}/quiz/start")
def quiz_start(slug: str, body: MobileIn, request: Request):
    mobile = _mobile(body.mobile)
    otp.check(mobile, body.otp_token)
    with db.session() as conn:
        return games.quiz_start(conn, slug, mobile, admin.client_ip(request))


class QuizFinishIn(BaseModel):
    token: str
    answers: dict[str, str] = {}


@app.post("/api/games/{slug}/quiz/finish")
def quiz_finish(slug: str, body: QuizFinishIn):
    with db.session() as conn:
        return games.quiz_finish(conn, slug, body.token, body.answers)
