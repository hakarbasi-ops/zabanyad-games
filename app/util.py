import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config

TZ = ZoneInfo(config.TIMEZONE)

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def latin_digits(text: str) -> str:
    return (text or "").translate(_DIGITS)


def normalize_mobile(raw: str) -> str | None:
    """'۰۹۱۲ ۳۴۵ ۶۷۸۹', '+989123456789', '9123456789' -> '09123456789'; None if invalid."""
    s = re.sub(r"[\s\-()]", "", latin_digits(raw))
    if s.startswith("+98"):
        s = "0" + s[3:]
    elif s.startswith("0098"):
        s = "0" + s[4:]
    elif s.startswith("98") and len(s) == 12:
        s = "0" + s[2:]
    elif s.startswith("9") and len(s) == 10:
        s = "0" + s
    return s if re.fullmatch(r"09\d{9}", s) else None


def mask_mobile(mobile: str) -> str:
    return mobile[:4] + "***" + mobile[-4:] if mobile and len(mobile) == 11 else mobile


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return utcnow().isoformat(timespec="seconds")


def local_now() -> datetime:
    return datetime.now(TZ)


def parse_local(value: str | None) -> datetime | None:
    """'2026-10-20T09:00' or '2026-10-20 09:00[:00]' in Tehran time -> aware datetime."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace(" ", "T"))
    except ValueError:
        return None
    return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt


def api_datetime(dt: datetime) -> str:
    return dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S")


def code_validity(days: int) -> tuple[str, str]:
    """(start, end) for the discount API. Start is yesterday 00:00 Tehran, so the code is valid at once even if
    Zabanyad reads the dates as UTC (3.5 h behind); end is 23:59:59 of the `days`-th day from today."""
    now = local_now()
    start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = (now + timedelta(days=max(days, 1) - 1)).replace(hour=23, minute=59, second=59, microsecond=0)
    return api_datetime(start), api_datetime(end)


def local_day_start_utc() -> str:
    """Start of today (Tehran) as a UTC ISO string, to count today's codes."""
    start = local_now().replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc).isoformat(timespec="seconds")
