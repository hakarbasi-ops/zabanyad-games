from datetime import datetime

from app import db, games, util, wallet
from app.util import TZ, local_now
from conftest import enable

SLUG = "black-friday-wheel"


def _open(admin, **settings):
    g = next(g for g in admin.get("/api/admin/games").json() if g["slug"] == SLUG)
    full = admin.get(f"/api/admin/games/{g['id']}").json()
    today = local_now().date().isoformat()
    full["settings"].update({"jackpot_days": {today: 3}, **settings})
    return enable(admin, SLUG, starts_at=None, ends_at=None, settings=full["settings"])


def test_seeded_wheel(admin):
    g = next(g for g in admin.get("/api/admin/games").json() if g["slug"] == SLUG)
    assert g["kind"] == "wheel" and g["enabled"] and g["starts_at"].startswith("2026-11-26")
    full = admin.get(f"/api/admin/games/{g['id']}").json()
    assert [(p["amount"], p["weight"], p["golden_weight"], p["stock"]) for p in full["prizes"]] == \
        [(30, 60, 45, None), (40, 28, 32, None), (50, 10, 18, None), (90, 2, 5, 10)]
    vault = next(x for x in admin.get("/api/admin/games").json() if x["slug"] == "black-friday")
    assert vault["ends_at"] == "2026-11-28T23:59" and vault["settings"]["jackpot_days"]["2026-11-27"] == 4


def test_own_spins_and_fixed_code_date(admin):
    _open(admin, bonus_date="")
    r = admin.post(f"/api/games/{SLUG}/play", json={"mobile": "09120000961", "src": "Instagram!"}).json()
    assert r["result"] == "won" and r["valid_until"] == "2026-11-30 23:59:59" and r["spins_left"] == 0
    with db.session() as conn, db.LOCK, db.transaction(conn):  # shared chances untouched
        assert wallet.ensure(conn, "09120000961")["chances"] == 3
    again = admin.post(f"/api/games/{SLUG}/play", json={"mobile": "09120000961"})
    assert again.status_code == 429 and again.json()["code"] == "no_spins"
    with db.session() as conn:
        assert conn.execute("SELECT source FROM plays ORDER BY id DESC LIMIT 1").fetchone()[0] == "instagram"


def test_friday_gets_two_spins(admin):
    _open(admin, bonus_date=local_now().date().isoformat(), bonus_spins=1)
    for left in (1, 0):
        assert admin.post(f"/api/games/{SLUG}/play", json={"mobile": "09120000962"}).json()["spins_left"] == left


def test_focus_mode_hides_other_games(admin):
    enable(admin, "wheel")
    _open(admin)
    listed = admin.get("/api/games").json()
    assert {g["slug"] for g in listed["games"]} <= {SLUG, "black-friday"} and listed["focus"]["slug"] == SLUG
    info = admin.get("/api/games/wheel").json()
    assert info["open"] is False and info["focus"]["slug"] == SLUG and "گردونه‌ی جمعه سیاه" in info["message"]
    assert admin.post("/api/games/wheel/play", json={"mobile": "09120000963"}).status_code == 400


def test_jackpot_day_plan():
    g = {"settings": {"jackpot_days": {"2026-11-26": 3, "2026-11-27": 4, "2026-11-28": 3}}}
    assert games.jackpot_cap(g, "2026-11-25") == 0
    assert games.jackpot_cap(g, "2026-11-26") == 3
    assert games.jackpot_cap(g, "2026-11-27") == 7
    assert games.jackpot_cap(g, "2026-11-30") == 10
    p = {"stock": 10, "given": 3}
    assert not games._in_day_plan(g, p, 3) and games._in_day_plan(g, p, 7)


def test_golden_weights():
    g = {"settings": {"golden_from": 20, "golden_to": 22}}
    prizes = [{"weight": 60, "golden_weight": 45}, {"weight": 2, "golden_weight": None}]
    assert games.in_golden_hour(g, datetime(2026, 11, 27, 21, tzinfo=TZ))
    assert not games.in_golden_hour(g, datetime(2026, 11, 27, 19, tzinfo=TZ))


def test_jackpot_board_and_sold_out_slice(admin):
    full = _open(admin)
    for p in full["prizes"]:
        p["weight"] = 1 if p["amount"] == 90 else 0
        p["golden_weight"] = None
    full["prizes"][0]["weight"] = 0
    assert admin.put(f"/api/admin/games/{full['id']}", json=full).status_code == 200
    for i in range(3):
        assert admin.post(f"/api/games/{SLUG}/play", json={"mobile": f"0912000097{i}"}).json()["prize_label"] == "۹۰٪ تخفیف"
    board = admin.get("/api/jackpot-winners").json()["winners"]
    assert len(board) == 3 and board[0]["mobile"] == "0912***0972"
    info = admin.get(f"/api/games/{SLUG}").json()
    assert info["slices"][3]["sold_out"] is True and info["limited"][0]["left_today"] == 0
    # today's 3 are gone: nothing else has weight, so the play is refused without spending the spin
    assert admin.post(f"/api/games/{SLUG}/play", json={"mobile": "09120000979"}).status_code == 409


def test_report_and_visits(admin):
    full = _open(admin)
    admin.post("/api/visit", json={"slug": SLUG, "src": "telegram"})
    admin.post("/api/visit", json={"slug": "nope", "src": "x"})
    admin.post(f"/api/games/{SLUG}/play", json={"mobile": "09120000981", "src": "telegram"})
    day = admin.get(f"/api/admin/games/{full['id']}/report").json()["days"][0]
    assert day["visits"] == 1 and day["plays"] == 1 and day["codes"] == 1 and day["sources"] == {"telegram": 1}
    assert day["visit_sources"] == {"telegram": 1}


def test_only_store_percentages(admin):
    full = _open(admin)
    full["prizes"][1]["amount"] = 60
    r = admin.put(f"/api/admin/games/{full['id']}", json=full)
    assert r.status_code == 400 and "۹۰" not in r.json()["detail"] or "90" in r.json()["detail"]
    assert admin.post("/api/admin/test-code", json={"mobile": "09120000990", "amount": 5}).status_code == 400
    assert admin.post("/api/admin/test-code", json={"mobile": "09120000990", "amount": 10}).json()["ok"]


def test_upgrade_drops_60_70(tmp_path, monkeypatch):
    """A v11 database (vault gold 50/70/90, wheel 50/60/70/90) gets only store percentages."""
    import json, sqlite3
    from app import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "old.db")
    db.init()
    with db.session() as conn:  # put the v11 plans back, as on the server
        v = conn.execute("SELECT id FROM games WHERE slug='black-friday'").fetchone()[0]
        conn.execute("UPDATE prizes SET weight=70 WHERE game_id=? AND min_score=3 AND amount=50", (v,))
        conn.execute("INSERT INTO prizes (game_id,label,kind,amount,max_amount,weight,min_score,sort) VALUES (?,?,?,?,?,?,?,?)",
                     (v, "۷۰٪ تخفیف", "percentage", 70, db.NO_CAP, 28, 3, 6))
        w = conn.execute("SELECT id FROM games WHERE slug='black-friday-wheel'").fetchone()[0]
        conn.execute("DELETE FROM prizes WHERE game_id=?", (w,))
        for i, a in enumerate(db.OLD_BF_WHEEL_AMOUNTS):
            conn.execute("INSERT INTO prizes (game_id,label,kind,amount,max_amount,weight,sort) VALUES (?,?,?,?,?,?,?)",
                         (w, f"{a}", "percentage", a, db.NO_CAP, 10, i))
        conn.execute("DELETE FROM settings WHERE key='allowed_percents_v12'")
    db.init()
    db.init()  # twice: runs once
    with db.session() as conn:
        gold = conn.execute("SELECT amount, weight FROM prizes WHERE game_id=? AND deleted=0 AND min_score=3 ORDER BY amount", (v,)).fetchall()
        wheel = [r[0] for r in conn.execute("SELECT amount FROM prizes WHERE game_id=? AND deleted=0 ORDER BY sort", (w,))]
    assert [tuple(r) for r in gold] == [(50, 98), (90, 2)] and wheel == [30, 40, 50, 90]


def test_codes_are_single_use(admin, monkeypatch):
    """Every code is asked for usage_count 1, even if a prize row says otherwise."""
    from app import discount
    sent = []
    real = discount.generate
    monkeypatch.setattr(discount, "generate", lambda req: (sent.append(req.usage_count), real(req))[1])
    with db.session() as conn:
        conn.execute("UPDATE prizes SET usage_count=5")
    _open(admin)
    admin.post(f"/api/games/{SLUG}/play", json={"mobile": "09120000995"})
    assert sent == [1]


def test_activity_board_is_real(admin):
    """Only real plays: last winners (90% marked big), players today only from ACTIVITY_MIN_PLAYERS up, codes waiting."""
    a = admin.get("/api/activity").json()
    assert a["recent"] == [] and a["players_today"] is None
    assert any(j["slug"] == "black-friday-wheel" and j["left"] == 10 for j in a["jackpots"])
    full = _open(admin)
    for p in full["prizes"]:
        p["weight"] = 1 if p["amount"] == 90 else 0
        p["golden_weight"] = None
    admin.put(f"/api/admin/games/{full['id']}", json=full)
    admin.post(f"/api/games/{SLUG}/play", json={"mobile": "09120000997"})
    a = admin.get("/api/activity").json()
    assert a["recent"][0]["mobile"] == "0912***0997" and a["recent"][0]["big"] is True
    w = next(j for j in a["jackpots"] if j["slug"] == SLUG)
    assert w["left"] == 9 and w["left_today"] == 2
    with db.session() as conn:  # enough players today → the count shows
        g = conn.execute("SELECT id FROM games WHERE slug='wheel'").fetchone()[0]
        for i in range(games.ACTIVITY_MIN_PLAYERS):
            conn.execute("INSERT INTO plays (game_id, mobile, status, created_at) VALUES (?,?,?,?)",
                         (g, f"0913{i:07d}", "lost", util.now_iso()))
    assert admin.get("/api/activity").json()["players_today"] == games.ACTIVITY_MIN_PLAYERS + 1
