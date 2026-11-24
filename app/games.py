"""Game rules: who may play, which prize they get, and turning a prize into a real discount code.

Every result is decided here on the server; the browser only shows it.
"""
import json
import random
import secrets
from datetime import datetime, timedelta

from . import config, db, discount, wallet
from .errors import PlayError  # noqa: F401  (re-exported: games.PlayError)
from .util import (code_validity, latin_digits, local_day_start_utc, local_now, mask_mobile, now_iso, parse_local,
                   utcnow)

RNG = random.SystemRandom()
QUIZ_GRACE_SECONDS = 10
CHANCE_KINDS = ("wheel", "scratch", "chest", "slot")   # result drawn by weight
SCORED_KINDS = ("quiz", "wordle")                       # result from the player's score (prize.min_score)
WORDLE_MAX_GUESSES = 6
WORDLE_MINUTES = 10
VAULT_DIGITS = 4
VAULT_MAX_GUESSES = 6
VAULT_MINUTES = 10
VAULT_TIERS = {1: "برنزی", 2: "نقره‌ای", 3: "طلایی"}   # prize.min_score = the tier it belongs to


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
    focus = blocked_by_focus(conn, game) if ok else None
    if focus:
        ok, message = False, focus["settings"].get("focus_message") or f"الان فقط «{focus['title']}» فعال است."
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
        "starts_at": game["starts_at"],
        "teaser": bool(game["settings"].get("teaser")),
        "theme": "bf" if game["kind"] == "vault" else game["settings"].get("theme", ""),
        "server_now": local_now().strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if focus:
        view["focus"] = {"slug": focus["slug"], "title": focus["title"]}
    cfg = game["settings"]
    if cfg.get("theme") == "bf" or game["kind"] == "vault":
        view.update({
            "limited": _limited(prizes, game), "show_left_below": int(cfg.get("show_left_below") or 0),
            "golden": ({"from": cfg.get("golden_from"), "to": cfg.get("golden_to"),
                        "boost": int(cfg.get("golden_boost") or 2), "now": in_golden_hour(game)}
                       if "golden_from" in cfg else None),
            "buy_url": cfg.get("buy_url", ""), "store_links": cfg.get("store_links", []),
            "code_until": cfg.get("code_until"), "slice_repeat": int(cfg.get("slice_repeat") or 1),
        })
    if own_spins(game):
        view["own_spins"] = {"daily": int(cfg.get("own_spins") or 0), "bonus_date": cfg.get("bonus_date"),
                             "bonus": int(cfg.get("bonus_spins") or 0)}
    if game["kind"] == "wordle":
        view["max_guesses"] = WORDLE_MAX_GUESSES
    if game["kind"] == "vault":
        return {**view, **vault_view(conn, game, prizes)}
    if game["kind"] == "quiz":
        view["question_count"] = quiz_count(conn, game)
        view["time_limit"] = int(game["settings"].get("time_limit", 60))
    if game["kind"] in SCORED_KINDS:
        view["ladder"] = [{"label": p["label"], "min_score": p["min_score"], "win": p["kind"] != "none"}
                          for p in sorted(prizes, key=lambda p: p["min_score"])]
    else:
        cap = jackpot_cap(game)
        view["slices"] = [{"label": p["label"], "color": p["color"], "win": p["kind"] != "none",
                           "sold_out": not _in_stock(p) or not _in_day_plan(game, p, cap)} for p in prizes]
    return view


# ---------------------------------------------------------------- limits


def focus_game(conn) -> dict | None:
    """An open game with settings.focus takes over the site (Black Friday wheel): only it and its focus_keep play."""
    for g in db.rows(conn.execute("SELECT * FROM games WHERE enabled=1")):
        if g["settings"].get("focus") and availability(g)[0]:
            return g
    return None


def blocked_by_focus(conn, game: dict) -> dict | None:
    focus = focus_game(conn)
    if focus and game["slug"] != focus["slug"] and game["slug"] not in focus["settings"].get("focus_keep", []):
        return focus
    return None


def own_spins(game: dict) -> bool:
    return int(game["settings"].get("own_spins") or 0) > 0


def spins_today_allowed(game: dict) -> int:
    cfg = game["settings"]
    extra = int(cfg.get("bonus_spins") or 0) if cfg.get("bonus_date") == local_now().date().isoformat() else 0
    return int(cfg.get("own_spins") or 0) + extra


def spins_used_today(conn, game: dict, mobile: str) -> int:
    # plays that did not count (not signed up / API error) give the spin back
    return conn.execute("SELECT COUNT(*) FROM plays WHERE game_id=? AND mobile=? AND created_at >= ?"
                        " AND status IN ('pending','won','lost')",
                        (game["id"], mobile, local_day_start_utc())).fetchone()[0]


def _spend(conn, game: dict, mobile: str) -> None:
    """A game with its own daily spins counts them itself; every other game spends a shared chance."""
    if not own_spins(game):
        wallet.spend(conn, mobile)
        return
    if spins_used_today(conn, game, mobile) >= spins_today_allowed(game):
        last = (parse_local(game["ends_at"]) or local_now()).date() <= local_now().date()
        raise PlayError("no_spins", "چرخش امروزت رو زدی! این آخرین روز بود؛ کدت رو تا آخر مهلتش استفاده کن." if last
                        else "چرخش امروزت رو زدی! فردا دوباره بیا و بچرخون.", 429)


def _check_limits(conn, game: dict, mobile: str, ip: str) -> None:
    ok, message = availability(game)
    if not ok:
        raise PlayError("closed", message)
    focus = blocked_by_focus(conn, game)
    if focus:
        raise PlayError("closed", focus["settings"].get("focus_message") or f"الان فقط «{focus['title']}» فعال است.")

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


def jackpot_cap(game: dict, today: str | None = None) -> int | None:
    """How many limited (stocked) prizes may have been given by the end of today; None = no day plan.
    Unused ones roll over to the next day."""
    days = game["settings"].get("jackpot_days")
    if not days:
        return None
    today = today or local_now().date().isoformat()
    return sum(int(n) for day, n in days.items() if day <= today)


def _in_day_plan(game: dict, p: dict, cap: int | None) -> bool:
    return cap is None or p["stock"] is None or p["given"] < cap


def _usable(conn, game: dict, prizes: list[dict]) -> list[dict]:
    """Prizes that can be handed out right now (stock left, day plan, daily code budget left)."""
    cap = jackpot_cap(game)
    usable = [p for p in prizes if _in_stock(p) and _in_day_plan(game, p, cap)]
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
    until = parse_local(game["settings"].get("code_until"))
    if until:  # campaign codes all end on one date (Black Friday: Sunday 9 Azar)
        end = until.replace(second=59).strftime("%Y-%m-%d %H:%M:%S")
    req = discount.CodeRequest(
        mobile=mobile, type=prize["kind"], amount=prize["amount"],
        max_amount=prize["max_amount"] or (prize["amount"] if prize["kind"] == "amount" else 0),
        usage_count=1,  # owner: every code is good for one subscription purchase, whatever the prize row says
        start_date=start, end_date=end,
    )
    try:
        code = discount.generate(req)
    except discount.DiscountError as exc:
        status = "need_signup" if exc.kind == "user_not_found" else "error"
        with db.transaction(conn):
            conn.execute("UPDATE plays SET status=?, error=?, finished_at=? WHERE id=?",
                         (status, f"{exc.kind}: {exc.detail}"[:300], now_iso(), play_id))
            _release(conn, prize["id"])
            if not own_spins(game):
                wallet.refund(conn, mobile)  # this play does not count (own-spin games just stop counting it)
        if status == "need_signup":
            raise PlayError("need_signup",
                            "این شماره در زبانیاد ثبت‌نام نکرده. اول با همین شماره در زبانیاد ثبت‌نام کنید و "
                            "دوباره بازی کنید؛ این دست حساب نشد.", 404)
        raise PlayError("api_error", "ساخت کد تخفیف الان ممکن نشد. چند دقیقه بعد دوباره امتحان کنید؛ "
                                     "این دست حساب نشد.", 503)

    conn.execute("UPDATE plays SET status='won', code=?, valid_until=?, finished_at=? WHERE id=?",
                 (code, end, now_iso(), play_id))
    return {"result": "won", "code": code, "valid_until": end}


def clean_source(src: str | None) -> str:
    return "".join(ch for ch in (src or "").lower() if ch.isalnum() or ch in "-_")[:30]


def _new_play(conn, game: dict, mobile: str, ip: str, prize: dict | None, status: str = "pending",
              token: str | None = None, data: dict | None = None, total: int | None = None,
              source: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO plays (game_id, mobile, status, prize_id, prize_label, ip, token, data, total, source, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (game["id"], mobile, status, prize["id"] if prize else None, prize["label"] if prize else "",
         ip, token, json.dumps(data or {}, ensure_ascii=False), total, clean_source(source) or None, now_iso()),
    )
    return cur.lastrowid


# ---------------------------------------------------------------- wheel / scratch


def in_golden_hour(game: dict, now=None) -> bool:
    cfg = game["settings"]
    if "golden_from" not in cfg:
        return False
    start, end, _ = golden_hours(game)
    hour = (now or local_now()).hour
    return start < end and start <= hour < end


def _golden_weights(game: dict, prizes: list[dict]) -> list[dict]:
    """In the golden hour, prizes with a golden_weight use it instead of their usual weight."""
    if not in_golden_hour(game) or not any(p.get("golden_weight") is not None for p in prizes):
        return prizes
    return [{**p, "weight": p["golden_weight"] if p.get("golden_weight") is not None else p["weight"]} for p in prizes]


def play_chance(conn, slug: str, mobile: str, ip: str, source: str | None = None) -> dict:
    game = get_game(conn, slug)
    if game["kind"] not in CHANCE_KINDS:
        raise PlayError("bad_game", "این بازی از این راه بازی نمی‌شود.")
    prizes = prizes_of(conn, game["id"])
    with db.LOCK, db.transaction(conn):
        _check_limits(conn, game, mobile, ip)
        prize = draw(_golden_weights(game, _usable(conn, game, prizes)))
        if not prize:
            raise PlayError("no_prizes", "جایزه‌های این بازی تمام شده.", 409)
        _spend(conn, game, mobile)
        _reserve(conn, prize)
        play_id = _new_play(conn, game, mobile, ip, prize, source=source)

    outcome = _issue(conn, game, play_id, prize, mobile)
    index = next(i for i, p in enumerate(prizes) if p["id"] == prize["id"])
    out = {**outcome, "prize_index": index, "prize_label": prize["label"], "chances": wallet.chances(conn, mobile)}
    if own_spins(game):
        out["spins_left"] = max(spins_today_allowed(game) - spins_used_today(conn, game, mobile), 0)
    return out


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

    return _finish_scored(conn, game, play, score, {"late": late})


def _finish_scored(conn, game: dict, play: dict, score: int, extra: dict) -> dict:
    """Gives the best prize the score reaches (quiz, wordle) and issues its code."""
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

    result = {"score": score, "total": play["total"], **extra}
    if not prize:
        return {**result, "result": "lost", "prize_label": "", "chances": wallet.chances(conn, play["mobile"])}
    outcome = _issue(conn, game, play["id"], prize, play["mobile"])
    return {**result, **outcome, "prize_label": prize["label"], "chances": wallet.chances(conn, play["mobile"])}


# ---------------------------------------------------------------- hidden word (Wordle-style, with the Persian meaning as hint)


def _wordle_words(conn, game_id: int) -> list[dict]:
    return [q for q in quiz_questions(conn, game_id) if q["word"].isascii() and q["word"].isalpha()
            and 4 <= len(q["word"]) <= 6]


def wordle_start(conn, slug: str, mobile: str, ip: str) -> dict:
    game = get_game(conn, slug)
    if game["kind"] != "wordle":
        raise PlayError("bad_game", "این بازی کلمه‌ی مخفی نیست.")
    words = _wordle_words(conn, game["id"])
    if not words:
        raise PlayError("no_questions", "هنوز کلمه‌ای برای این بازی ثبت نشده.", 409)
    q = RNG.choice(words)
    token = secrets.token_urlsafe(24)
    with db.LOCK, db.transaction(conn):
        _check_limits(conn, game, mobile, ip)
        wallet.spend(conn, mobile)
        _new_play(conn, game, mobile, ip, None, token=token, total=WORDLE_MAX_GUESSES,
                  data={"qid": q["id"], "guesses": []})
    return {"token": token, "length": len(q["word"]), "hint": q["answer"], "max_guesses": WORDLE_MAX_GUESSES,
            "chances": wallet.chances(conn, mobile)}


def wordle_feedback(word: str, guess: str) -> list[str]:
    """Per letter: 'correct' (right place), 'present' (elsewhere in the word), 'absent'; repeats counted properly."""
    result = ["absent"] * len(guess)
    left: dict[str, int] = {}
    for i, (w, g) in enumerate(zip(word, guess)):
        if w == g:
            result[i] = "correct"
        else:
            left[w] = left.get(w, 0) + 1
    for i, g in enumerate(guess):
        if result[i] != "correct" and left.get(g, 0) > 0:
            result[i] = "present"
            left[g] -= 1
    return result


def wordle_guess(conn, slug: str, token: str, guess: str) -> dict:
    game = get_game(conn, slug)
    play = db.row(conn.execute("SELECT * FROM plays WHERE token=? AND game_id=?", (token, game["id"])).fetchone())
    if not play:
        raise PlayError("bad_token", "این دست بازی پیدا نشد. صفحه را دوباره باز کنید.", 404)
    if play["status"] != "pending":
        raise PlayError("finished", "این دست قبلاً تمام شده.", 409)
    q = db.row(conn.execute("SELECT * FROM questions WHERE id=?", (play["data"]["qid"],)).fetchone())
    word = q["word"].lower()
    guess = (guess or "").strip().lower()
    if len(guess) != len(word) or not guess.isascii() or not guess.isalpha():
        raise PlayError("bad_guess", f"یک کلمه‌ی {len(word)} حرفی انگلیسی بنویسید.")

    late = (utcnow() - datetime.fromisoformat(play["created_at"])).total_seconds() > WORDLE_MINUTES * 60
    with db.LOCK, db.transaction(conn):
        fresh = db.row(conn.execute("SELECT status, data FROM plays WHERE id=?", (play["id"],)).fetchone())
        if fresh["status"] != "pending":
            raise PlayError("finished", "این دست قبلاً تمام شده.", 409)
        guesses = fresh["data"]["guesses"] + ([] if late else [guess])
        conn.execute("UPDATE plays SET data=? WHERE id=?",
                     (json.dumps({**fresh["data"], "guesses": guesses}), play["id"]))
    feedback = wordle_feedback(word, guess)
    solved = not late and guess == word
    if not (solved or late or len(guesses) >= WORDLE_MAX_GUESSES):
        return {"feedback": feedback, "done": False, "guesses": len(guesses)}
    # solved in n guesses → score 7-n (1 guess = 6 … 6 guesses = 1); not solved → 0
    score = WORDLE_MAX_GUESSES + 1 - len(guesses) if solved else 0
    out = _finish_scored(conn, game, play, score,
                         {"late": late, "solved": solved, "guesses": len(guesses), "answer": word, "meaning": q["answer"]})
    return {"feedback": feedback, "done": True, **out}


# ---------------------------------------------------------------- Black Friday vault (crack a 4-digit code, then open a tier)


def _setting_int(game: dict, key: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(game["settings"].get(key, default))))
    except (TypeError, ValueError):
        return default


def golden_hours(game: dict) -> tuple[int, int, int]:
    """(from hour, to hour, weight multiplier); multiplier 1 = no golden hour."""
    return (_setting_int(game, "golden_from", 20, 0, 23), _setting_int(game, "golden_to", 22, 0, 24),
            _setting_int(game, "golden_boost", 1, 1, 10))


def golden_now(game: dict, now=None) -> bool:
    start, end, boost = golden_hours(game)
    hour = (now or local_now()).hour
    return boost > 1 and start < end and start <= hour < end


def vault_tier(game: dict, solved: bool, guesses: int) -> int:
    if solved and guesses <= _setting_int(game, "gold_max", 3, 1, VAULT_MAX_GUESSES):
        return 3
    if solved and guesses <= _setting_int(game, "silver_max", 5, 1, VAULT_MAX_GUESSES):
        return 2
    return 1


def _limited(prizes: list[dict], game: dict | None = None) -> list[dict]:
    cap = jackpot_cap(game) if game else None
    days = (game or {}).get("settings", {}).get("jackpot_days") or {}
    out = []
    for p in prizes:
        if p["stock"] is None or p["kind"] == "none":
            continue
        left = max(p["stock"] - p["given"], 0)
        item = {"label": p["label"], "tier": p["min_score"], "left": left}
        if cap is not None:
            item["left_today"] = max(min(cap, p["stock"]) - p["given"], 0)
            later = sorted(d for d in days if d > local_now().date().isoformat())
            item["next_day"] = later[0] if later else None
        out.append(item)
    return out


def vault_view(conn, game: dict, prizes: list[dict]) -> dict:
    start, end, boost = golden_hours(game)
    tiers = []
    for tier in sorted(VAULT_TIERS, reverse=True):
        labels = []
        for p in prizes:
            if p["min_score"] == tier and p["kind"] != "none" and p["label"] not in labels:
                labels.append(p["label"])
        tiers.append({"tier": tier, "name": VAULT_TIERS[tier], "labels": labels})
    return {
        "digits": VAULT_DIGITS, "max_guesses": VAULT_MAX_GUESSES, "tiers": tiers,
        "gold_max": _setting_int(game, "gold_max", 3, 1, VAULT_MAX_GUESSES),
        "silver_max": _setting_int(game, "silver_max", 5, 1, VAULT_MAX_GUESSES),
        "limited": _limited(prizes, game),
        "golden": {"from": start, "to": end, "boost": boost, "now": golden_now(game)} if boost > 1 else None,
        "starts_at": game["starts_at"], "teaser": bool(game["settings"].get("teaser", True)),
        "server_now": local_now().strftime("%Y-%m-%dT%H:%M:%S"),
    }


def recent_winners(conn, game: dict, limit: int = 12) -> dict:
    rows = conn.execute("SELECT mobile, prize_label, finished_at FROM plays WHERE game_id=? AND status='won'"
                        " ORDER BY id DESC LIMIT ?", (game["id"], limit)).fetchall()
    now = utcnow()
    winners = [{"mobile": mask_mobile(r["mobile"]), "prize": r["prize_label"],
                "ago": int((now - datetime.fromisoformat(r["finished_at"])).total_seconds()) if r["finished_at"] else 0}
               for r in rows]
    return {"winners": winners, "limited": _limited(prizes_of(conn, game["id"]), game),
            "golden_now": golden_now(game) if game["kind"] == "vault" else in_golden_hour(game)}


def jackpot_winners(conn, min_amount: int = 90, limit: int = 40) -> list[dict]:
    """Everyone who won the top prize (90%), newest first, masked mobiles: the «برنده‌های ۹۰٪» board."""
    rows = conn.execute(
        "SELECT p.mobile, p.prize_label, p.finished_at, g.title FROM plays p JOIN prizes z ON z.id=p.prize_id"
        " JOIN games g ON g.id=p.game_id WHERE p.status='won' AND z.kind='percentage' AND z.amount >= ?"
        " ORDER BY p.id DESC LIMIT ?", (min_amount, limit)).fetchall()
    return [{"mobile": mask_mobile(r["mobile"]), "prize": r["prize_label"], "game": r["title"],
             "at": datetime.fromisoformat(r["finished_at"]).astimezone(local_now().tzinfo).strftime("%Y-%m-%d %H:%M")
             if r["finished_at"] else ""} for r in rows]


ACTIVITY_MIN_PLAYERS = 30   # «امروز n نفر بازی کردن» shows only from this many players up (a tiny number looks bad)


def activity(conn, limit: int = 12) -> dict:
    """Real activity for the boards on the home and game pages: last winners of every prize (masked mobiles, 90%+
    marked big), today's players, and the 90% codes still waiting in running Black Friday games. Nothing is invented."""
    now = utcnow()
    rows = conn.execute(
        "SELECT p.mobile, p.prize_label, p.finished_at, g.title, z.amount, z.kind FROM plays p JOIN games g ON g.id=p.game_id"
        " LEFT JOIN prizes z ON z.id=p.prize_id WHERE p.status='won' ORDER BY p.id DESC LIMIT ?", (limit,)).fetchall()
    recent = [{"mobile": mask_mobile(r["mobile"]), "prize": r["prize_label"], "game": r["title"],
               "big": r["kind"] == "percentage" and (r["amount"] or 0) >= 90,
               "ago": int((now - datetime.fromisoformat(r["finished_at"])).total_seconds()) if r["finished_at"] else 0}
              for r in rows]
    players = conn.execute("SELECT COUNT(DISTINCT mobile) FROM plays WHERE status IN ('won','lost') AND created_at >= ?",
                           (local_day_start_utc(),)).fetchone()[0]
    jackpots = []
    for g in db.rows(conn.execute("SELECT * FROM games WHERE enabled=1 ORDER BY id")):
        end = parse_local(g["ends_at"])
        if not g["settings"].get("jackpot_days") or (end and local_now() > end):
            continue
        for item in _limited(prizes_of(conn, g["id"]), g):
            jackpots.append({"game": g["title"], "slug": g["slug"], **item})
    return {"recent": recent, "players_today": players if players >= ACTIVITY_MIN_PLAYERS else None, "jackpots": jackpots}


def vault_start(conn, slug: str, mobile: str, ip: str, source: str | None = None) -> dict:
    game = get_game(conn, slug)
    if game["kind"] != "vault":
        raise PlayError("bad_game", "این بازی گاوصندوق نیست.")
    code = "".join(RNG.sample("0123456789", VAULT_DIGITS))
    token = secrets.token_urlsafe(24)
    with db.LOCK, db.transaction(conn):
        _check_limits(conn, game, mobile, ip)
        wallet.spend(conn, mobile)
        _new_play(conn, game, mobile, ip, None, token=token, total=VAULT_MAX_GUESSES,
                  data={"code": code, "guesses": []}, source=source)
    return {"token": token, "digits": VAULT_DIGITS, "max_guesses": VAULT_MAX_GUESSES,
            "chances": wallet.chances(conn, mobile)}


def vault_guess(conn, slug: str, token: str, guess: str) -> dict:
    game = get_game(conn, slug)
    play = db.row(conn.execute("SELECT * FROM plays WHERE token=? AND game_id=?", (token, game["id"])).fetchone())
    if not play:
        raise PlayError("bad_token", "این دست بازی پیدا نشد. صفحه را دوباره باز کنید.", 404)
    if play["status"] != "pending":
        raise PlayError("finished", "این دست قبلاً تمام شده.", 409)
    guess = latin_digits(guess or "").strip()
    if len(guess) != VAULT_DIGITS or not guess.isdigit() or not guess.isascii():
        raise PlayError("bad_guess", f"یک رمز {VAULT_DIGITS} رقمی بنویسید.")
    code = play["data"]["code"]

    late = (utcnow() - datetime.fromisoformat(play["created_at"])).total_seconds() > VAULT_MINUTES * 60
    with db.LOCK, db.transaction(conn):
        fresh = db.row(conn.execute("SELECT status, data FROM plays WHERE id=?", (play["id"],)).fetchone())
        if fresh["status"] != "pending":
            raise PlayError("finished", "این دست قبلاً تمام شده.", 409)
        guesses = fresh["data"]["guesses"] + ([] if late else [guess])
        conn.execute("UPDATE plays SET data=? WHERE id=?",
                     (json.dumps({**fresh["data"], "guesses": guesses}), play["id"]))
    feedback = wordle_feedback(code, guess)
    solved = not late and guess == code
    if not (solved or late or len(guesses) >= VAULT_MAX_GUESSES):
        return {"feedback": feedback, "done": False, "guesses": len(guesses)}
    tier = vault_tier(game, solved, len(guesses))
    out = _finish_vault(conn, game, play, tier,
                        {"late": late, "solved": solved, "guesses": len(guesses), "answer": code})
    return {"feedback": feedback, "done": True, **out}


def _finish_vault(conn, game: dict, play: dict, tier: int, extra: dict) -> dict:
    """Opens the earned vault: a weighted draw among that tier's prizes (big ones boosted in the golden hour).
    A tier with nothing left in stock falls back to the tier below, then to any prize left."""
    prizes = prizes_of(conn, game["id"])
    golden = golden_now(game)
    boost = golden_hours(game)[2] if golden else 1
    with db.LOCK, db.transaction(conn):
        fresh = conn.execute("SELECT status FROM plays WHERE id=?", (play["id"],)).fetchone()
        if fresh["status"] != "pending":
            raise PlayError("finished", "این دست قبلاً تمام شده.", 409)
        usable = _usable(conn, game, prizes)
        prize, opened = None, tier
        for t in [*range(tier, 0, -1), *range(tier + 1, 4)]:
            pool = [dict(p) for p in usable if p["min_score"] == t and p["weight"] > 0]
            if not pool:
                continue
            smallest = min(p["amount"] for p in pool)
            for p in pool:  # golden hour: everything above the tier's smallest prize is `boost` times likelier
                if p["amount"] > smallest:
                    p["weight"] *= boost
            prize, opened = draw(pool), t
            break
        if prize:
            _reserve(conn, prize)
        conn.execute("UPDATE plays SET score=?, prize_id=?, prize_label=? WHERE id=?",
                     (tier, prize["id"] if prize else None, prize["label"] if prize else "", play["id"]))
        if not prize:
            conn.execute("UPDATE plays SET status='lost', finished_at=? WHERE id=?", (now_iso(), play["id"]))

    result = {"tier": opened, "earned_tier": tier, "tier_name": VAULT_TIERS[opened], "golden": golden,
              "score": tier, "total": 3, **extra}
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
