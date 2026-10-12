"""Settings, all read from the environment (a `.env` file next to the app works too)."""
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


_load_dotenv(ROOT / ".env")


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


DATA_DIR = Path(env("DATA_DIR", str(ROOT / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "games.db"

# Zabanyad discount API
DISCOUNT_API_URL = env(
    "DISCOUNT_API_URL",
    "https://api.zabanyad.com/api/v1/discount/generateDiscountForUser",
)
DISCOUNT_API_SECRET = env("DISCOUNT_API_SECRET")
# "live" calls the API; "mock" makes fake codes (for trying the games without touching Zabanyad).
DISCOUNT_MODE = env("DISCOUNT_MODE", "live" if DISCOUNT_API_SECRET else "mock").lower()
DISCOUNT_API_TIMEOUT = float(env("DISCOUNT_API_TIMEOUT", "15"))

# Where winners use their code (shown under the code).
SHOP_URL = env("SHOP_URL", "https://zabanyad.com")
SIGNUP_URL = env("SIGNUP_URL", SHOP_URL)

TIMEZONE = env("TIMEZONE", "Asia/Tehran")

ADMIN_PASSWORD = env("ADMIN_PASSWORD")

# Max game attempts (plays + quiz starts) from one IP per hour.
IP_PLAYS_PER_HOUR = int(env("IP_PLAYS_PER_HOUR", "30"))
# Behind nginx / a CDN the real client IP is in X-Forwarded-For.
TRUST_PROXY = env("TRUST_PROXY", "1") == "1"


def _session_secret() -> str:
    value = env("SESSION_SECRET")
    if value:
        return value
    path = DATA_DIR / "session_secret"
    if not path.exists():
        path.write_text(secrets.token_hex(32))
        path.chmod(0o600)
    return path.read_text().strip()


SESSION_SECRET = _session_secret()
