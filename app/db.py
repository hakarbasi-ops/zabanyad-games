"""SQLite storage. One small file in DATA_DIR; schema is created/upgraded at startup."""
import json
import sqlite3
import threading
from contextlib import contextmanager

from . import config
from .util import now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,                 -- wheel | scratch | quiz
    title TEXT NOT NULL,
    subtitle TEXT NOT NULL DEFAULT '',
    rules TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 0,
    starts_at TEXT,                     -- Tehran local time, empty = no limit
    ends_at TEXT,
    plays_per_mobile INTEGER NOT NULL DEFAULT 1,
    period_days INTEGER NOT NULL DEFAULT 0,      -- 0 = whole campaign
    code_valid_days INTEGER NOT NULL DEFAULT 7,
    daily_code_limit INTEGER NOT NULL DEFAULT 0, -- 0 = no limit
    settings TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prizes (
    id INTEGER PRIMARY KEY,
    game_id INTEGER NOT NULL REFERENCES games(id),
    label TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'percentage',   -- percentage | amount | none
    amount INTEGER NOT NULL DEFAULT 0,          -- percent, or rials for kind=amount
    max_amount INTEGER NOT NULL DEFAULT 0,      -- rials, 0 = no cap
    usage_count INTEGER NOT NULL DEFAULT 1,
    weight INTEGER NOT NULL DEFAULT 1,
    stock INTEGER,                              -- NULL = unlimited
    given INTEGER NOT NULL DEFAULT 0,
    min_score INTEGER NOT NULL DEFAULT 0,       -- quiz: correct answers needed
    color TEXT NOT NULL DEFAULT '',
    sort INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    deleted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY,
    game_id INTEGER NOT NULL REFERENCES games(id),
    word TEXT NOT NULL,
    answer TEXT NOT NULL,
    wrong TEXT NOT NULL DEFAULT '[]',
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS plays (
    id INTEGER PRIMARY KEY,
    game_id INTEGER NOT NULL REFERENCES games(id),
    mobile TEXT NOT NULL,
    status TEXT NOT NULL,          -- pending | won | lost | need_signup | error
    prize_id INTEGER,
    prize_label TEXT NOT NULL DEFAULT '',
    code TEXT,
    valid_until TEXT,
    score INTEGER,
    total INTEGER,
    error TEXT,
    ip TEXT,
    token TEXT,
    data TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS plays_game_mobile ON plays(game_id, mobile, created_at);
CREATE INDEX IF NOT EXISTS plays_game_created ON plays(game_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS plays_token ON plays(token) WHERE token IS NOT NULL;
CREATE TABLE IF NOT EXISTS otps (
    id INTEGER PRIMARY KEY,
    mobile TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    tries INTEGER NOT NULL DEFAULT 0,
    used INTEGER NOT NULL DEFAULT 0,
    ip TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS otps_mobile ON otps(mobile, created_at);
"""

# Serialises the "check limits + reserve prize" step so two requests cannot both take the last prize.
LOCK = threading.Lock()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def init() -> None:
    with session() as conn:
        conn.executescript(SCHEMA)
        if not conn.execute("SELECT 1 FROM games LIMIT 1").fetchone():
            seed(conn)


def row(r: sqlite3.Row | None) -> dict | None:
    if r is None:
        return None
    d = dict(r)
    for key in ("settings", "data", "wrong"):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except ValueError:
                d[key] = {} if key != "wrong" else []
    return d


def rows(rs) -> list[dict]:
    return [row(r) for r in rs]


# ---------------------------------------------------------------- seed data

# Zabanyad design-system palette: brand orange, lighter, info, subtle
DEFAULT_COLORS = ["#F26600", "#FCE0CC", "#33357D", "#F7A366"]

SEED_GAMES = [
    {
        "slug": "wheel",
        "kind": "wheel",
        "title": "گردونه شانس زبانیاد",
        "subtitle": "گردونه رو بچرخون و کد تخفیف ببر!",
        "rules": "هر شماره موبایل یک بار می‌تونه بچرخونه. کد تخفیف روی همون شماره در زبانیاد فعال می‌شه.",
        "prizes": [
            ("۱۰٪ تخفیف", "percentage", 10, 2000000, 30),
            ("پوچ", "none", 0, 0, 20),
            ("۱۵٪ تخفیف", "percentage", 15, 3000000, 20),
            ("۵۰ هزار تومان", "amount", 500000, 500000, 10),
            ("۲۰٪ تخفیف", "percentage", 20, 4000000, 10),
            ("یه بار دیگه!", "none", 0, 0, 10),
            ("۳۰٪ تخفیف", "percentage", 30, 6000000, 4),
            ("۵٪ تخفیف", "percentage", 5, 1000000, 30),
        ],
    },
    {
        "slug": "scratch",
        "kind": "scratch",
        "title": "کارت خراشی زبانیاد",
        "subtitle": "روی کارت بکش و جایزه‌ت رو ببین!",
        "rules": "هر شماره موبایل یک بار می‌تونه کارت رو بخراشه.",
        "prizes": [
            ("۱۰٪ تخفیف", "percentage", 10, 2000000, 40),
            ("۱۵٪ تخفیف", "percentage", 15, 3000000, 25),
            ("۲۵٪ تخفیف", "percentage", 25, 5000000, 5),
            ("این بار نشد!", "none", 0, 0, 30),
        ],
    },
    {
        "slug": "words",
        "kind": "quiz",
        "title": "چالش کلمه‌های زبانیاد",
        "subtitle": "معنی کلمه‌ها رو در ۶۰ ثانیه پیدا کن؛ هرچی بیشتر، تخفیف بیشتر!",
        "rules": "۵ کلمه، ۶۰ ثانیه. با ۳ جواب درست ۱۰٪، با ۴ جواب ۱۵٪ و با ۵ جواب ۲۵٪ تخفیف می‌گیری.",
        "settings": {"question_count": 5, "time_limit": 60},
        "prizes": [
            ("تلاش خوبی بود!", "none", 0, 0, 1, 0),
            ("۱۰٪ تخفیف", "percentage", 10, 2000000, 1, 3),
            ("۱۵٪ تخفیف", "percentage", 15, 3000000, 1, 4),
            ("۲۵٪ تخفیف", "percentage", 25, 5000000, 1, 5),
        ],
        "questions": [
            ("apple", "سیب", ["پرتقال", "موز", "انگور"]),
            ("library", "کتابخانه", ["کتاب‌فروشی", "دانشگاه", "مدرسه"]),
            ("brave", "شجاع", ["ترسو", "خسته", "باهوش"]),
            ("journey", "سفر", ["روزنامه", "شادی", "قضاوت"]),
            ("borrow", "قرض گرفتن", ["قرض دادن", "خریدن", "فروختن"]),
            ("kitchen", "آشپزخانه", ["اتاق خواب", "حمام", "حیاط"]),
            ("weather", "آب و هوا", ["زمستان", "باران", "فصل"]),
            ("quiet", "ساکت", ["شلوغ", "سریع", "آرام‌بخش"]),
            ("neighbor", "همسایه", ["دوست", "همکار", "فامیل"]),
            ("improve", "بهتر کردن", ["ثابت کردن", "شروع کردن", "تمام کردن"]),
            ("honest", "صادق", ["مهربان", "خجالتی", "مغرور"]),
            ("decide", "تصمیم گرفتن", ["فکر کردن", "پرسیدن", "انتخاب شدن"]),
            ("thirsty", "تشنه", ["گرسنه", "خسته", "خوابالو"]),
            ("cheap", "ارزان", ["گران", "مجانی", "کمیاب"]),
            ("forget", "فراموش کردن", ["به یاد آوردن", "بخشیدن", "پیدا کردن"]),
        ],
    },
]


def seed(conn: sqlite3.Connection) -> None:
    for g in SEED_GAMES:
        cur = conn.execute(
            "INSERT INTO games (slug, kind, title, subtitle, rules, enabled, plays_per_mobile, period_days,"
            " code_valid_days, settings, created_at) VALUES (?,?,?,?,?,0,1,0,7,?,?)",
            (g["slug"], g["kind"], g["title"], g["subtitle"], g["rules"],
             json.dumps(g.get("settings", {}), ensure_ascii=False), now_iso()),
        )
        game_id = cur.lastrowid
        for i, p in enumerate(g["prizes"]):
            label, kind, amount, max_amount, weight, *rest = p
            conn.execute(
                "INSERT INTO prizes (game_id, label, kind, amount, max_amount, weight, min_score, color, sort)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (game_id, label, kind, amount, max_amount, weight, rest[0] if rest else 0,
                 DEFAULT_COLORS[i % len(DEFAULT_COLORS)], i),
            )
        for word, answer, wrong in g.get("questions", []):
            conn.execute(
                "INSERT INTO questions (game_id, word, answer, wrong) VALUES (?,?,?,?)",
                (game_id, word, answer, json.dumps(wrong, ensure_ascii=False)),
            )
