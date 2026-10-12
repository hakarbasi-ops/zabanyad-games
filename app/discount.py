"""Zabanyad discount-code API (POST generateDiscountForUser, header X-Client-Secret).

The secret only ever comes from the environment and is never logged or returned.
"""
import logging
import secrets
from dataclasses import dataclass

import httpx

from . import config

log = logging.getLogger("discount")


class DiscountError(Exception):
    """kind: 'unauthorized' (bad secret), 'user_not_found', 'server', 'network', 'bad_response'."""

    def __init__(self, kind: str, detail: str = ""):
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail


@dataclass
class CodeRequest:
    mobile: str
    type: str          # percentage | amount
    amount: int
    max_amount: int
    usage_count: int
    start_date: str    # YYYY-MM-DD HH:mm:ss
    end_date: str
    email: str = ""

    def body(self) -> dict:
        return {
            "mobile": self.mobile,
            "email": self.email,
            "type": self.type,
            "amount": self.amount,
            "max_amount": self.max_amount,
            "usage_count": self.usage_count,
            "start_date": self.start_date,
            "end_date": self.end_date,
        }


def mode() -> str:
    return "live" if config.DISCOUNT_MODE == "live" else "mock"


def generate(req: CodeRequest) -> str:
    """Returns the promotion code or raises DiscountError."""
    if mode() == "mock":
        # Same shape as a real code; "T" prefix so a test code is never mistaken for a real one.
        return "T" + secrets.token_hex(4).upper()[:7]

    if not config.DISCOUNT_API_SECRET:
        raise DiscountError("unauthorized", "DISCOUNT_API_SECRET is empty")
    headers = {"Content-Type": "application/json", "X-Client-Secret": config.DISCOUNT_API_SECRET}
    try:
        resp = httpx.post(config.DISCOUNT_API_URL, json=req.body(), headers=headers,
                          timeout=config.DISCOUNT_API_TIMEOUT)
    except httpx.HTTPError as exc:
        log.warning("discount API unreachable: %s", type(exc).__name__)
        raise DiscountError("network", type(exc).__name__) from None

    if resp.status_code in (200, 201):
        try:
            code = (resp.json() or {}).get("promotion_code")
        except ValueError:
            code = None
        if code:
            return str(code)
        raise DiscountError("bad_response", resp.text[:200])
    if resp.status_code in (401, 403):
        raise DiscountError("unauthorized", f"HTTP {resp.status_code}")
    if resp.status_code == 404:
        raise DiscountError("user_not_found", resp.text[:200])
    raise DiscountError("server", f"HTTP {resp.status_code}: {resp.text[:200]}")
