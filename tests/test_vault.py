from datetime import datetime

from app import db, games, wallet
from app.util import TZ
from conftest import enable


def _code(token):
    with db.session() as conn:
        return db.row(conn.execute("SELECT data FROM plays WHERE token=?", (token,)).fetchone())["data"]["code"]


def _open(admin, **changes):
    # the seeded event starts on 2 Azar; tests open it now
    return enable(admin, "black-friday", starts_at=None, ends_at=None, **changes)


def test_seeded_as_event_with_teaser(admin):
    g = next(g for g in admin.get("/api/admin/games").json() if g["slug"] == "black-friday")
    assert g["kind"] == "vault" and g["enabled"] and g["starts_at"].startswith("2026-11-23")
    full = admin.get(f"/api/admin/games/{g['id']}").json()
    tiers = {t: [p["amount"] for p in full["prizes"] if p["min_score"] == t] for t in (1, 2, 3)}
    assert tiers == {1: [20, 30], 2: [30, 40, 50], 3: [50, 70, 90]}
    assert next(p for p in full["prizes"] if p["amount"] == 90)["stock"] == 10


def test_home_lists_it_as_coming_soon(client):
    info = client.get("/api/games/black-friday").json()
    games_now = client.get("/api/games").json()["games"]
    if datetime.now(TZ) < datetime(2026, 11, 23, tzinfo=TZ):
        assert info["open"] is False and info["teaser"] and info["starts_at"]
        assert games_now[0]["slug"] == "black-friday" and games_now[0]["soon"] is True
        r = client.post("/api/games/black-friday/vault/start", json={"mobile": "09120000950"})
        assert r.status_code == 400


def test_gold_in_three_guesses(admin):
    _open(admin)
    s = admin.post("/api/games/black-friday/vault/start", json={"mobile": "09120000951"}).json()
    code = _code(s["token"])
    assert len(set(code)) == 4 and s["chances"] == 2
    wrong = next(c for c in ("0123", "4567", "8901") if c != code)
    for _ in range(2):
        r = admin.post("/api/games/black-friday/vault/guess", json={"token": s["token"], "guess": wrong}).json()
        assert r["done"] is False
    persian = code.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    r = admin.post("/api/games/black-friday/vault/guess", json={"token": s["token"], "guess": persian}).json()
    assert r["done"] and r["solved"] and r["tier"] == 3 and r["tier_name"] == "طلایی"
    assert r["prize_label"] in ("۵۰٪ تخفیف", "۷۰٪ تخفیف", "۹۰٪ تخفیف") and r["code"].startswith("T")
    assert admin.post("/api/games/black-friday/vault/guess",
                      json={"token": s["token"], "guess": code}).status_code == 409


def test_failed_still_opens_bronze(admin):
    _open(admin)
    s = admin.post("/api/games/black-friday/vault/start", json={"mobile": "09120000952"}).json()
    code = _code(s["token"])
    wrong = next(c for c in ("0123", "4567") if c != code)
    assert admin.post("/api/games/black-friday/vault/guess",
                      json={"token": s["token"], "guess": "12"}).status_code == 400
    for _ in range(6):
        r = admin.post("/api/games/black-friday/vault/guess", json={"token": s["token"], "guess": wrong}).json()
    assert r["done"] and not r["solved"] and r["tier"] == 1 and r["answer"] == code
    assert r["prize_label"] in ("۲۰٪ تخفیف", "۳۰٪ تخفیف")


def test_tiers_and_golden_hour():
    g = {"settings": {"gold_max": 3, "silver_max": 5, "golden_from": 20, "golden_to": 22, "golden_boost": 2}}
    assert [games.vault_tier(g, True, n) for n in range(1, 7)] == [3, 3, 3, 2, 2, 1]
    assert games.vault_tier(g, False, 6) == 1
    assert games.golden_now(g, datetime(2026, 11, 27, 20, 30, tzinfo=TZ))
    assert not games.golden_now(g, datetime(2026, 11, 27, 22, 0, tzinfo=TZ))
    assert not games.golden_now({"settings": {**g["settings"], "golden_boost": 1}},
                                datetime(2026, 11, 27, 21, 0, tzinfo=TZ))


def test_sold_out_gold_falls_back(admin):
    full = _open(admin)
    for p in full["prizes"]:
        if p["min_score"] == 3:
            p["stock"] = 0
    admin.put(f"/api/admin/games/{full['id']}", json=full)
    s = admin.post("/api/games/black-friday/vault/start", json={"mobile": "09120000953"}).json()
    code = _code(s["token"])
    r = admin.post("/api/games/black-friday/vault/guess", json={"token": s["token"], "guess": code}).json()
    assert r["earned_tier"] == 3 and r["tier"] == 2 and r["result"] == "won"


def test_winners_ticker_masks_mobiles(admin):
    _open(admin)
    s = admin.post("/api/games/black-friday/vault/start", json={"mobile": "09120000954"}).json()
    admin.post("/api/games/black-friday/vault/guess", json={"token": s["token"], "guess": _code(s["token"])})
    w = admin.get("/api/games/black-friday/winners").json()
    assert w["winners"][0]["mobile"] == "0912***0954" and w["limited"][0]["left"] <= 10


def test_bonus_chance_on_the_bonus_day(admin):
    today = datetime.now(TZ).date().isoformat()
    full = _open(admin)
    full["settings"].update({"bonus_date": today, "bonus_chances": 1})
    admin.put(f"/api/admin/games/{full['id']}", json=full)
    with db.session() as conn, db.LOCK, db.transaction(conn):
        assert wallet.ensure(conn, "09120000955")["chances"] == 4


def test_panel_checks_tiers(admin):
    full = _open(admin)
    full["prizes"][0]["min_score"] = 7
    assert admin.put(f"/api/admin/games/{full['id']}", json=full).status_code == 400
    g = admin.post("/api/admin/games", json={"slug": "vault-2", "kind": "vault", "title": "گاوصندوق"}).json()
    assert len(g["prizes"]) == 8 and g["settings"]["golden_boost"] == 2
