"""Chances: every verified mobile has one balance of plays shared by all games.

- New player: `start_chances` (3); invited by a valid link: + `invitee_bonus` (1) → 4.
- Each day the player shows up: + `daily_chance` (1). Missed days do not pile up.
- Inviting: when an invited mobile that never played before verifies, the inviter gets `referral_reward` (3),
  at most `referral_daily_cap` (10) successful invites per inviter per day. Only while `referral_enabled` is on
  (keep it off until real SMS is wired, or fake numbers could farm chances).
- A play costs one chance; it is given back when the play does not count (not signed up / API error).

All functions expect to run inside the caller's transaction.
"""
import secrets

from . import db
from .errors import PlayError
from .util import local_now, now_iso

DEFAULTS = {
    "start_chances": 3,
    "daily_chance": 1,
    "referral_enabled": 0,
    "referral_reward": 3,
    "invitee_bonus": 1,
    "referral_daily_cap": 10,
}
LIMITS = {  # (min, max) accepted from the panel
    "start_chances": (0, 50),
    "daily_chance": (0, 10),
    "referral_enabled": (0, 1),
    "referral_reward": (0, 50),
    "invitee_bonus": (0, 50),
    "referral_daily_cap": (0, 1000),
}
_REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I


def settings(conn) -> dict:
    out = dict(DEFAULTS)
    for r in conn.execute("SELECT key, value FROM settings WHERE key IN (%s)" % ",".join("?" * len(DEFAULTS)),
                          list(DEFAULTS)):
        try:
            out[r["key"]] = int(r["value"])
        except ValueError:
            pass
    return out


def save_settings(conn, values: dict) -> dict:
    for key, (lo, hi) in LIMITS.items():
        if key in values:
            value = max(lo, min(hi, int(values[key])))
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)"
                         " ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    return settings(conn)


def _today() -> str:
    return local_now().date().isoformat()


def _new_ref_code(conn) -> str:
    while True:
        code = "".join(secrets.choice(_REF_ALPHABET) for _ in range(6))
        if not conn.execute("SELECT 1 FROM players WHERE ref_code=?", (code,)).fetchone():
            return code


def _get(conn, mobile: str) -> dict | None:
    return db.row(conn.execute("SELECT * FROM players WHERE mobile=?", (mobile,)).fetchone())


def ensure(conn, mobile: str, ref: str | None = None) -> dict:
    """Returns the player, creating it (with referral credit) or adding today's chance as needed."""
    cfg = settings(conn)
    today = _today()
    player = _get(conn, mobile)
    if player is None:
        chances = cfg["start_chances"]
        inviter = _credit_inviter(conn, cfg, mobile, ref)
        if inviter:
            chances += cfg["invitee_bonus"]
        conn.execute("INSERT INTO players (mobile, chances, ref_code, referred_by, last_daily, created_at)"
                     " VALUES (?,?,?,?,?,?)", (mobile, chances, _new_ref_code(conn), inviter, today, now_iso()))
        return _get(conn, mobile)
    if player["last_daily"] != today:
        conn.execute("UPDATE players SET chances = chances + ?, last_daily=? WHERE mobile=?",
                     (cfg["daily_chance"], today, mobile))
        player = _get(conn, mobile)
    return player


def _credit_inviter(conn, cfg: dict, mobile: str, ref: str | None) -> str | None:
    if not cfg["referral_enabled"] or not ref:
        return None
    inviter = db.row(conn.execute("SELECT * FROM players WHERE ref_code=?", (ref.strip().upper(),)).fetchone())
    if not inviter or inviter["mobile"] == mobile:
        return None
    if conn.execute("SELECT 1 FROM plays WHERE mobile=? LIMIT 1", (mobile,)).fetchone():
        return None  # not a new player
    day_start = local_now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
    today_count = conn.execute("SELECT COUNT(*) FROM referrals WHERE inviter=? AND created_local >= ?",
                               (inviter["mobile"], day_start)).fetchone()[0]
    if today_count >= cfg["referral_daily_cap"]:
        return None
    conn.execute("UPDATE players SET chances = chances + ?, invites = invites + 1 WHERE mobile=?",
                 (cfg["referral_reward"], inviter["mobile"]))
    conn.execute("INSERT INTO referrals (inviter, invitee, reward, created_at, created_local) VALUES (?,?,?,?,?)",
                 (inviter["mobile"], mobile, cfg["referral_reward"], now_iso(),
                  local_now().isoformat(timespec="seconds")))
    return inviter["mobile"]


def spend(conn, mobile: str) -> int:
    player = ensure(conn, mobile)
    if player["chances"] <= 0:
        cfg = settings(conn)
        msg = "شانس‌هایت تمام شد! فردا یک شانس تازه داری."
        if cfg["referral_enabled"]:
            msg = f"شانس‌هایت تمام شد! با دعوت هر دوست {cfg['referral_reward']} شانس تازه بگیر، یا فردا برگرد."
        raise PlayError("no_chances", msg, 429)
    conn.execute("UPDATE players SET chances = chances - 1 WHERE mobile=?", (mobile,))
    return player["chances"] - 1


def refund(conn, mobile: str) -> None:
    conn.execute("UPDATE players SET chances = chances + 1 WHERE mobile=?", (mobile,))


def grant(conn, mobile: str, count: int) -> dict:
    ensure(conn, mobile)
    conn.execute("UPDATE players SET chances = MAX(chances + ?, 0) WHERE mobile=?", (count, mobile))
    return _get(conn, mobile)


def chances(conn, mobile: str) -> int:
    player = _get(conn, mobile)
    return player["chances"] if player else 0


def view(conn, player: dict) -> dict:
    cfg = settings(conn)
    return {
        "chances": player["chances"],
        "ref_code": player["ref_code"],
        "invites": player["invites"],
        "referral_enabled": bool(cfg["referral_enabled"]),
        "referral_reward": cfg["referral_reward"],
        "invitee_chances": cfg["start_chances"] + cfg["invitee_bonus"],
        "daily_chance": cfg["daily_chance"],
    }
