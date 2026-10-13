"""Sends the verification code by SMS through Kavenegar's Verify Lookup (the panel Zabanyad already uses).

GET https://api.kavenegar.com/v1/{API_KEY}/verify/lookup.json?receptor=09…&token=12345&template=<name>
The template is made once in the Kavenegar panel with %token in its text (e.g. «کد تأیید بازی‌های زبانیاد: %token»).
The API key sits in the URL path, so the URL itself is never logged; the panel log shows receptor + template only.
"""
import json
import logging
import time

import httpx

from . import config, db
from .errors import PlayError
from .util import now_iso

log = logging.getLogger("sms")

KAVENEGAR_URL = "https://api.kavenegar.com/v1/{key}/verify/lookup.json"
# Kavenegar return.status → what the admin should check (shown in the panel log)
KAVENEGAR_ERRORS = {
    401: "کلید API کاوه‌نگار درست نیست یا غیرفعال است",
    403: "کلید API کاوه‌نگار معتبر نیست",
    411: "شماره گیرنده درست نیست",
    412: "شماره ارسال‌کننده درست نیست",
    418: "اعتبار حساب کاوه‌نگار کافی نیست",
    422: "متن پیامک کاراکتر نامعتبر دارد",
    424: "الگو (template) در کاوه‌نگار پیدا نشد یا هنوز تأیید نشده",
    426: "این سرویس برای حساب کاوه‌نگار فعال نیست",
    428: "الگو برای ارسال کد تأیید نیست",
    431: "ساختار متن یا توکن الگو درست نیست",
    432: "پارامتر token در متن الگو نیست",
}


def _log(receptor: str, status: int | None, response: str, started: float) -> None:
    try:
        with db.session() as conn:
            conn.execute("INSERT INTO api_log (created_at, mode, request, status, response, ms) VALUES (?,?,?,?,?,?)",
                         (now_iso(), "sms", json.dumps({"receptor": receptor, "template": config.KAVENEGAR_TEMPLATE},
                                                       ensure_ascii=False), status, response[:500],
                          int((time.monotonic() - started) * 1000)))
    except Exception:
        log.exception("api_log write failed")


def send_code(mobile: str, code: str) -> None:
    """Raises PlayError (shown to the player) when the SMS could not be handed to Kavenegar."""
    if not config.KAVENEGAR_API_KEY or not config.KAVENEGAR_TEMPLATE:
        raise PlayError("sms_unavailable", "ارسال پیامک تنظیم نشده. لطفاً بعداً امتحان کنید.", 503)
    started = time.monotonic()
    try:
        resp = httpx.get(KAVENEGAR_URL.format(key=config.KAVENEGAR_API_KEY),
                         params={"receptor": mobile, "token": code, "template": config.KAVENEGAR_TEMPLATE},
                         timeout=15)
    except httpx.HTTPError as exc:
        _log(mobile, None, type(exc).__name__, started)
        raise PlayError("sms_unavailable", "ارسال پیامک الان ممکن نشد. کمی بعد دوباره امتحان کنید.", 503) from None
    try:
        status = int((resp.json().get("return") or {}).get("status", resp.status_code))
    except (ValueError, AttributeError, TypeError):
        status = resp.status_code
    if status == 200:
        _log(mobile, 200, "ارسال شد", started)
        return
    _log(mobile, status, f"{KAVENEGAR_ERRORS.get(status, 'خطای کاوه‌نگار')} — {resp.text[:300]}", started)
    if status == 411:
        raise PlayError("bad_mobile", "این شماره موبایل پیامک دریافت نمی‌کند. شماره را بررسی کنید.", 400)
    raise PlayError("sms_unavailable", "ارسال پیامک الان ممکن نشد. کمی بعد دوباره امتحان کنید.", 503)
