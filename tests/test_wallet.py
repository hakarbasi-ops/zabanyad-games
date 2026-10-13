from datetime import date, timedelta

from app import db, wallet
from conftest import enable


def _me(client, mobile):
    return client.post("/api/me", json={"mobile": mobile}).json()


def test_prize_plan(admin):
    game = enable(admin, "wheel")
    weights = {p["label"]: p["weight"] for p in game["prizes"] if p["active"] and not p["deleted"]}
    assert weights == {"۱۰٪ تخفیف": 500, "۲۰٪ تخفیف": 280, "۳۰٪ تخفیف": 140, "۴۰٪ تخفیف": 60,
                       "۵۰٪ تخفیف": 19, "۹۰٪ تخفیف": 1}
    assert all(p["max_amount"] == db.NO_CAP for p in game["prizes"] if p["active"])


def test_daily_chance_does_not_pile_up(client):
    assert _me(client, "09120000201")["chances"] == 3
    with db.session() as conn:
        conn.execute("UPDATE players SET last_daily=? WHERE mobile=?",
                     ((date.today() - timedelta(days=5)).isoformat(), "09120000201"))
    assert _me(client, "09120000201")["chances"] == 4   # +1 once, not +5
    assert _me(client, "09120000201")["chances"] == 4   # same day again: nothing


def _referral(admin, **cfg):
    r = admin.put("/api/admin/chance-settings", json={"referral_enabled": 1, **cfg})
    assert r.status_code == 200, r.text


def test_referral_rewards(admin):
    _referral(admin)
    code = _me(admin, "09120000301")["ref_code"]
    with db.session() as conn, db.transaction(conn):
        wallet.ensure(conn, "09120000302", code)      # new player through the link
        wallet.ensure(conn, "09120000301", code)      # self-invite: ignored
        wallet.ensure(conn, "09120000302", code)      # second time: ignored
    assert _me(admin, "09120000301")["chances"] == 3 + 3
    assert _me(admin, "09120000302")["chances"] == 4
    top = admin.get("/api/admin/referrals").json()
    assert top["top"][0]["mobile"] == "09120000301" and top["top"][0]["invites"] == 1


def test_referral_off_and_daily_cap(admin):
    code = _me(admin, "09120000401")["ref_code"]
    with db.session() as conn, db.transaction(conn):
        wallet.ensure(conn, "09120000402", code)      # referrals are off by default
    assert _me(admin, "09120000401")["chances"] == 3 and _me(admin, "09120000402")["chances"] == 3
    _referral(admin, referral_daily_cap=1)
    with db.session() as conn, db.transaction(conn):
        wallet.ensure(conn, "09120000403", code)
        wallet.ensure(conn, "09120000404", code)      # over today's cap
    assert _me(admin, "09120000401")["chances"] == 6


def test_admin_grant(admin):
    r = admin.post("/api/admin/grant-chances", json={"mobile": "09120000501", "count": 5}).json()
    assert r["chances"] == 8
