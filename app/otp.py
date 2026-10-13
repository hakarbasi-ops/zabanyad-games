"""Mobile verification by SMS code before a game can be played.

Flow: POST /api/otp/send {mobile} -> code by SMS; POST /api/otp/verify {mobile, code} -> signed token (valid
VERIFY_MINUTES) that the play endpoints require for that same mobile.

Who sends the SMS is behind `_deliver()`: "kavenegar" (real SMS, app/sms.py) or "mock" (the code is shown on the
page; testing only).
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from . import config, db, sms, wallet
from .games import PlayError
from .util import now_iso, utcnow

CODE_DIGITS = 5
CODE_MINUTES = 2          # an SMS code is valid this long
VERIFY_MINUTES = 30 * 24 * 60  # after verifying, the mobile stays signed in on that device for 30 days
RESEND_SECONDS = 60
MAX_PER_MOBILE_HOUR = 5
MAX_PER_IP_HOUR = 20
MAX_TRIES = 5             # wrong guesses per code

_serializer = URLSafeTimedSerializer(config.SESSION_SECRET, salt="zg-otp")


def required() -> bool:
    return config.OTP_REQUIRED


def mode() -> str:
    return config.SMS_MODE


def _hash(mobile: str, code: str) -> str:
    return hmac.new(config.SESSION_SECRET.encode(), f"{mobile}:{code}".encode(), hashlib.sha256).hexdigest()


def _deliver(mobile: str, code: str) -> None:
    if mode() == "mock":
        return
    if mode() == "kavenegar":
        sms.send_code(mobile, code)
        return
    raise PlayError("sms_unavailable", "ارسال پیامک تنظیم نشده. لطفاً بعداً امتحان کنید.", 503)


def send(mobile: str, ip: str) -> dict:
    now = utcnow()
    hour_ago = (now - timedelta(hours=1)).isoformat(timespec="seconds")
    with db.session() as conn:
        with db.transaction(conn):
            last = conn.execute("SELECT created_at FROM otps WHERE mobile=? ORDER BY id DESC LIMIT 1",
                                (mobile,)).fetchone()
            if last:
                wait = RESEND_SECONDS - (now - datetime.fromisoformat(last["created_at"])).total_seconds()
                if wait > 0:
                    raise PlayError("otp_wait", f"کد قبلی همین الان فرستاده شد. {int(wait) + 1} ثانیه دیگر دوباره امتحان کنید.", 429)
            per_mobile = conn.execute("SELECT COUNT(*) FROM otps WHERE mobile=? AND created_at >= ?",
                                      (mobile, hour_ago)).fetchone()[0]
            per_ip = conn.execute("SELECT COUNT(*) FROM otps WHERE ip=? AND created_at >= ?",
                                  (ip, hour_ago)).fetchone()[0]
            if per_mobile >= MAX_PER_MOBILE_HOUR or (ip and per_ip >= MAX_PER_IP_HOUR):
                raise PlayError("otp_rate", "درخواست کد زیاد شد. یک ساعت بعد دوباره امتحان کنید.", 429)
            code = "".join(secrets.choice("0123456789") for _ in range(CODE_DIGITS))
            cur = conn.execute("INSERT INTO otps (mobile, code_hash, ip, created_at, expires_at) VALUES (?,?,?,?,?)",
                         (mobile, _hash(mobile, code), ip, now_iso(),
                          (now + timedelta(minutes=CODE_MINUTES)).isoformat(timespec="seconds")))
    try:
        _deliver(mobile, code)
    except PlayError:
        with db.session() as conn:  # not sent: do not make the player wait for a resend
            conn.execute("DELETE FROM otps WHERE id=?", (cur.lastrowid,))
        raise
    out = {"sent": True, "resend_after": RESEND_SECONDS, "digits": CODE_DIGITS}
    if mode() == "mock":
        out["test_code"] = code  # test mode only: there is no SMS, so the page shows the code
    return out


def verify(mobile: str, code: str, ref: str | None = None) -> dict:
    code = (code or "").strip()
    with db.session() as conn:
        with db.transaction(conn):
            row = conn.execute("SELECT * FROM otps WHERE mobile=? AND used=0 ORDER BY id DESC LIMIT 1",
                               (mobile,)).fetchone()
            if not row or row["expires_at"] < now_iso():
                raise PlayError("otp_expired", "کد منقضی شده. دوباره «دریافت کد» را بزنید.", 400)
            if row["tries"] >= MAX_TRIES:
                raise PlayError("otp_locked", "چند بار کد اشتباه وارد شد. یک کد تازه بگیرید.", 429)
            good = hmac.compare_digest(row["code_hash"], _hash(mobile, code))
            # count the wrong guess before raising, or the error would roll the count back
            conn.execute("UPDATE otps SET tries = tries + 1, used = ? WHERE id=?", (int(good), row["id"]))
    if not good:
        raise PlayError("otp_wrong", "کد تأیید درست نیست.", 400)
    with db.session() as conn, db.LOCK, db.transaction(conn):
        player = wallet.ensure(conn, mobile, ref)  # new players get their chances (and the inviter's reward) here
        view = wallet.view(conn, player)
    return {"token": _serializer.dumps(mobile), "valid_minutes": VERIFY_MINUTES, "wallet": view}


def check(mobile: str, token: str | None) -> None:
    """Raises unless `token` proves `mobile` was verified recently. No-op when OTP is off."""
    if not required():
        return
    try:
        verified = _serializer.loads(token or "", max_age=VERIFY_MINUTES * 60)
    except (BadSignature, SignatureExpired):
        verified = None
    if verified != mobile:
        raise PlayError("need_otp", "اول شماره موبایل را با کد پیامکی تأیید کنید.", 401)
