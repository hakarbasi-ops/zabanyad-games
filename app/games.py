"""Game rules: who may play, which prize they get, and turning a prize into a real discount code.

Every result is decided here on the server; the browser only shows it.
"""
import json
import random
import secrets
from datetime import datetime, timedelta

from . import config, db, discount, wallet
from .errors import PlayError  # noqa: F401  (re-exported: games.PlayError)
from .util import code_validity, local_day_start_utc, local_now, now_iso, parse_local, utcnow

RNG = random.SystemRandom()
QUIZ_GRACE_SECONDS = 10


# ---------------------------------------------------------------- loading


def get_game(conn, slug: str) -> dict:
    game = db.row(conn.execute("SELECT * FROM games WHERE slug=?", (slug,)).fetchone())
    if not game:
        raise PlayError("not_found", "این بازی پیدا نشد.", 404)
    return game


def prizes_of(conn, game_id: int, active_only: bool = True) -> list[dict]:
    sql = "SELECT * FROM prizes WHERE game_id=? AND deleted=0"
    if active_only:
        sql += " AND active=1"
    return db.rows(conn.execute(sql + " ORDER BY sort, id", (game_id,)))


def availability(game: dict) -> tuple[bool, str]:
    if not game["enabled"]:
        return False, "این بازی فعلاً فعال نیست."
    now = local_now()
    start, end = parse_local(game["starts_at"]), parse_local(game["ends_at"])
    if start and now < start:
        return False, "این بازی هنوز شروع نشده."
    if end and now > end:
        return False, "مهلت این بازی تمام شده."
    return True, ""


def public_view(conn, game: dict) -> dict:
    ok, message = availability(game)
    prizes = prizes_of(conn, game["id"])
    view = {
        "slug": game["slug"],
        "kind": game["kind"],
        "title": game["title"],
        "subtitle": game["subtitle"],
        "rules": game["rules"],
        "open": ok,
        "message": message,
        "color": game["settings"].get("color", ""),
        "ends_at": game["ends_at"],
    }
    if game["kind"] == "quiz":
        view["question_count"] = quiz_count(conn, game)
        view["time_limit"] = int(game["settings"].get("time_limit", 60))
        view["ladder"] = [{"label": p["label"], "min_score": p["min_score"], "win": p["kind"] != "none"}
                          for p in sorted(prizes, key=lambda p: p["min_score"])]
    else:
        view["slices"] = [{"label": p["label"], "color": p["color"], "win": p["kind"] != "none"} for p in prizes]
    return view


# ---------------------------------------------------------------- limits


def _check_limits(conn, game: dict, mobile: str, ip: str) -> None:
    ok, message = availability(game)
    if not ok:
        raise PlayError("closed", message)

    # how often a mobile may play is set by its chances (wallet.py), shared by all games

    hour_ago = (utcnow() - timedelta(hours=1)).isoformat(timespec="seconds")
    from_ip = conn.execute("SELECT COUNT(*) FROM plays WHERE ip=? AND created_at >= ?", (ip, hour_ago)).fetchone()[0]
    if ip and from_ip >= config.IP_PLAYS_PER_HOUR:
        raise PlayError("rate", "تعداد بازی از این اینترنت زیاد شده. کمی بعد دوباره امتحان کنید.", 429)


def _codes_today(conn, game_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM plays WHERE game_id=? AND prize_id IN"
        " (SELECT id FROM prizes WHERE kind!='none') AND status IN ('won','pending') AND created_at >= ?",
        (game_id, local_day_start_utc()),
    ).fetchone()[0]


def _in_stock(p: dict) -> bool:
    return p["stock"] is None or p["given"] < p["stock"]


def _usable(conn, game: dict, prizes: list[dict]) -> list[dict]:
    """Prizes that can be handed out right now (stock left, daily code budget left)."""
    usable = [p for p in prizes if _in_stock(p)]
    if game["daily_code_limit"] > 0 and _codes_today(conn, game["id"]) >= game["daily_code_limit"]:
        usable = [p for p in usable if p["kind"] == "none"]
    return usable


def draw(prizes: list[dict]) -> dict | None:
    pool = [p for p in prizes if p["weight"] > 0]
    if not pool:
        return None
    return RNG.choices(pool, weights=[p["weight"] for p in pool], k=1)[0]


def _reserve(conn, prize: dict) -> None:
    if prize["kind"] != "none" and prize["stock"] is not None:
        conn.execute("UPDATE prizes SET given = given + 1 WHERE id=?", (prize["id"],))


def _release(conn, prize_id: int) -> None:
    conn.execute("UPDATE prizes SET given = MAX(given - 1, 0) WHERE id=? AND stock IS NOT NULL AND kind!='none'", (prize_id,))


# ---------------------------------------------------------------- issuing codes


def _issue(conn, game: dict, play_id: int, prize: dict, mobile: str) -> dict:
    """Asks Zabanyad for the code of a reserved prize and finishes the play row."""
    if prize["kind"] == "none":
        conn.execute("UPDATE plays SET status='lost', finished_at=? WHERE id=?", (now_iso(), play_id))
        return {"result": "lost"}

    start, end = code_validity(game["code_valid_days"])
    req = discount.CodeRequest(
        mobile=mobile, type=prize["kind"], amount=prize["amount"],
        max_amount=prize["max_amount"] or (prize["amount"] if prize["kind"] == "amount" else 0),
        usage_count=max(prize["usage_count"], 1), start_date=start, end_date=end,
    )
    try:
        code = discount.generate(req)
    except discount.DiscountError as exc:
        status = "need_signup" if exc.kind == "user_not_found" else "error"
        with db.transaction(conn):
            conn.execute("UPDATE plays SET status=?, error=?, finished_at=? WHERE id=?",
                         (status, f"{exc.kind}: {exc.detail}"[:300], now_iso(), play_id))
            _release(conn, prize["id"])
            wallet.refund(conn, mobile)  # this play does not count
        if status == "need_signup":
            raise PlayError("need_signup",
                            "این شماره در زبانیاد ثبت‌نام نکرده. اول با همین شماره در زبانیاد ثبت‌نام کنید و "
                            "دوباره بازی کنید؛ این دست حساب نشد.", 404)
        raise PlayError("api_error", "ساخت کد تخفیف الان ممکن نشد. چند دقیقه بعد دوباره امتحان کنید؛ "
                                     "این دست حساب نشد.", 503)

    conn.execute("UPDATE plays SET status='won', code=?, valid_until=?, finished_at=? WHERE id=?",
                 (code, end, now_iso(), play_id))
    return {"result": "won", "code": code, "valid_until": end}


def _new_play(conn, game: dict, mobile: str, ip: str, prize: dict | None, status: str = "pending",
              token: str | None = None, data: dict | None = None, total: int | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO plays (game_id, mobile, status, prize_id, prize_label, ip, token, data, total, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (game["id"], mobile, status, prize["id"] if prize else None, prize["label"] if prize else "",
         ip, token, json.dumps(data or {}, ensure_ascii=False), total, now_iso()),
    )
    return cur.lastrowid


# ---------------------------------------------------------------- wheel / scratch


def play_chance(conn, slug: str, mobile: str, ip: str) -> dict:
    game = get_game(conn, slug)
    if game["kind"] not in ("wheel", "scratch"):
        raise PlayError("bad_game", "این بازی از این راه بازی نمی‌شود.")
    prizes = prizes_of(conn, game["id"])
    with db.LOCK, db.transaction(conn):
        _check_limits(conn, game, mobile, ip)
        prize = draw(_usable(conn, game, prizes))
        if not prize:
            raise PlayError("no_prizes", "جایزه‌های این بازی تمام شده.", 409)
        wallet.spend(conn, mobile)
        _reserve(conn, prize)
        play_id = _new_play(conn, game, mobile, ip, prize)

    outcome = _issue(conn, game, play_id, prize, mobile)
    index = next(i for i, p in enumerate(prizes) if p["id"] == prize["id"])
    return {**outcome, "prize_index": index, "prize_label": prize["label"], "chances": wallet.chances(conn, mobile)}


# ---------------------------------------------------------------- quiz


def quiz_questions(conn, game_id: int) -> list[dict]:
    return db.rows(conn.execute("SELECT * FROM questions WHERE game_id=? AND active=1", (game_id,)))


def quiz_count(conn, game: dict) -> int:
    available = len(quiz_questions(conn, game["id"]))
    return min(int(game["settings"].get("question_count", 5)), available)


def quiz_start(conn, slug: str, mobile: str, ip: str) -> dict:
    game = get_game(conn, slug)
    if game["kind"] != "quiz":
        raise PlayError("bad_game", "این بازی چالش کلمه نیست.")
    pool = [q for q in quiz_questions(conn, game["id"]) if len(q["wrong"]) >= 1]
    count = min(int(game["settings"].get("question_count", 5)), len(pool))
    if count < 1:
        raise PlayError("no_questions", "هنوز سؤالی برای این بازی ثبت نشده.", 409)
    picked = RNG.sample(pool, count)
    shown = []
    for q in picked:
        options = [q["answer"], *q["wrong"][:3]]
        RNG.shuffle(options)
        shown.append({"id": q["id"], "word": q["word"], "options": options})
    token = secrets.token_urlsafe(24)
    time_limit = int(game["settings"].get("time_limit", 60))
    with db.LOCK, db.transaction(conn):
        _check_limits(conn, game, mobile, ip)
        wallet.spend(conn, mobile)
        _new_play(conn, game, mobile, ip, None, token=token, total=count,
                  data={"questions": [q["id"] for q in picked], "time_limit": time_limit})
    return {"token": token, "questions": shown, "time_limit": time_limit, "chances": wallet.chances(conn, mobile)}


def quiz_finish(conn, slug: str, token: str, answers: dict) -> dict:
    game = get_game(conn, slug)
    play = db.row(conn.execute("SELECT * FROM plays WHERE token=? AND game_id=?", (token, game["id"])).fetchone())
    if not play:
        raise PlayError("bad_token", "این دست بازی پیدا نشد. صفحه را دوباره باز کنید.", 404)
    if play["status"] != "pending":
        raise PlayError("finished", "این دست قبلاً تمام شده.", 409)

    started = datetime.fromisoformat(play["created_at"])
    elapsed = (utcnow() - started).total_seconds()
    late = elapsed > play["data"].get("time_limit", 60) + QUIZ_GRACE_SECONDS

    qids = play["data"]["questions"]
    by_id = {q["id"]: q for q in db.rows(conn.execute(
        f"SELECT * FROM questions WHERE id IN ({','.join('?' * len(qids))})", qids))}
    score = 0 if late else sum(
        1 for qid in qids if qid in by_id and str(answers.get(str(qid), "")).strip() == by_id[qid]["answer"]
    )

    prizes = prizes_of(conn, game["id"])
    with db.LOCK, db.transaction(conn):
        # re-check inside the lock: two finishes for the same token must not both pass
        fresh = conn.execute("SELECT status FROM plays WHERE id=?", (play["id"],)).fetchone()
        if fresh["status"] != "pending":
            raise PlayError("finished", "این دست قبلاً تمام شده.", 409)
        reachable = sorted((p for p in prizes if p["min_score"] <= score), key=lambda p: -p["min_score"])
        usable = {p["id"] for p in _usable(conn, game, reachable)}
        # best prize the score reaches that still has stock; else the best "no prize" row
        prize = next((p for p in reachable if p["id"] in usable), None)
        if prize:
            _reserve(conn, prize)
        conn.execute("UPDATE plays SET score=?, prize_id=?, prize_label=? WHERE id=?",
                     (score, prize["id"] if prize else None, prize["label"] if prize else "", play["id"]))
        if not prize:
            conn.execute("UPDATE plays SET status='lost', finished_at=? WHERE id=?", (now_iso(), play["id"]))

    result = {"score": score, "total": play["total"], "late": late}
    if not prize:
        return {**result, "result": "lost", "prize_label": "", "chances": wallet.chances(conn, play["mobile"])}
    outcome = _issue(conn, game, play["id"], prize, play["mobile"])
    return {**result, **outcome, "prize_label": prize["label"], "chances": wallet.chances(conn, play["mobile"])}


def expire_stale(conn) -> None:
    """Quiz runs never finished (closed tab) become 'lost'; a chance play stuck half way (server restart
    during the API call) becomes 'error' and gives its prize back."""
    cutoff = (utcnow() - timedelta(minutes=30)).isoformat(timespec="seconds")
    with db.LOCK, db.transaction(conn):
        conn.execute("UPDATE plays SET status='lost', score=0, finished_at=? WHERE status='pending'"
                     " AND token IS NOT NULL AND prize_id IS NULL AND created_at < ?", (now_iso(), cutoff))
        stuck = conn.execute("SELECT id, prize_id FROM plays WHERE status='pending' AND created_at < ?",
                             (cutoff,)).fetchall()
        for r in stuck:
            conn.execute("UPDATE plays SET status='error', error='interrupted', finished_at=? WHERE id=?",
                         (now_iso(), r["id"]))
            if r["prize_id"]:
                _release(conn, r["prize_id"])
