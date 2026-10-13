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
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS players (
    mobile TEXT PRIMARY KEY,
    chances INTEGER NOT NULL DEFAULT 0,
    ref_code TEXT NOT NULL UNIQUE,
    referred_by TEXT,
    invites INTEGER NOT NULL DEFAULT 0,
    last_daily TEXT,                 -- Tehran date of the last daily chance
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY,
    inviter TEXT NOT NULL,
    invitee TEXT NOT NULL UNIQUE,
    reward INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    created_local TEXT NOT NULL      -- Tehran time, for the per-day cap
);
CREATE INDEX IF NOT EXISTS referrals_inviter ON referrals(inviter, created_local);
CREATE TABLE IF NOT EXISTS api_log (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    mode TEXT NOT NULL,
    request TEXT NOT NULL,          -- JSON body sent (never the secret)
    status INTEGER,                 -- HTTP status, NULL when the server was unreachable
    response TEXT NOT NULL DEFAULT '',
    ms INTEGER
);
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
        else:
            add_missing_games(conn)
        apply_prize_plan(conn)


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
        "rules": "هر چرخش یک شانس مصرف می‌کند. همه برنده‌اند: از ۱۰٪ تا ۹۰٪ تخفیف! کد روی همان شماره در زبانیاد فعال می‌شود.",
    },
    {
        "slug": "scratch",
        "kind": "scratch",
        "title": "کارت خراشی زبانیاد",
        "subtitle": "روی کارت بکش و جایزه‌ت رو ببین!",
        "rules": "هر کارت یک شانس مصرف می‌کند. همه برنده‌اند: از ۱۰٪ تا ۹۰٪ تخفیف!",
    },
    {
        "slug": "words",
        "kind": "quiz",
        "title": "چالش کلمه‌های زبانیاد",
        "subtitle": "معنی کلمه‌ها رو در ۶۰ ثانیه پیدا کن؛ هرچی بیشتر، تخفیف بیشتر!",
        "rules": "۵ کلمه، ۶۰ ثانیه، یک شانس. ۰ تا ۱ جواب درست ۱۰٪، ۲ جواب ۲۰٪، ۳ جواب ۳۰٪، ۴ جواب ۴۰٪ و ۵ جواب ۵۰٪ تخفیف.",
        "settings": {"question_count": 5, "time_limit": 60},
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
    {
        "slug": "chest",
        "kind": "chest",
        "title": "صندوق شانس زبانیاد",
        "subtitle": "یکی از سه صندوق رو باز کن و جایزه‌ت رو ببین!",
        "rules": "هر صندوق یک شانس مصرف می‌کند. همه برنده‌اند: از ۱۰٪ تا ۹۰٪ تخفیف!",
    },
    {
        "slug": "slot",
        "kind": "slot",
        "title": "ماشین شانس زبانیاد",
        "subtitle": "اهرم رو بکش؛ سه تا مثل هم بیاد، همون تخفیف مال توئه!",
        "rules": "هر بار کشیدن اهرم یک شانس مصرف می‌کند. همه برنده‌اند: از ۱۰٪ تا ۹۰٪ تخفیف!",
    },
    {
        "slug": "hidden-word",
        "kind": "wordle",
        "title": "کلمه‌ی مخفی زبانیاد",
        "subtitle": "معنی فارسی رو داری؛ کلمه‌ی انگلیسیش رو در ۶ حدس پیدا کن!",
        "rules": "یک شانس، ۶ حدس. هر حرف سبز یعنی جای درست، زرد یعنی در کلمه هست ولی جای دیگر. "
                 "در ۱ تا ۲ حدس ۵۰٪، ۳ حدس ۴۰٪، ۴ حدس ۳۰٪، ۵ حدس ۲۰٪، و در هر صورت حداقل ۱۰٪ تخفیف.",
        "questions": [
            ("apple", "سیب", []), ("house", "خانه", []), ("water", "آب", []), ("happy", "خوشحال", []),
            ("green", "سبز", []), ("money", "پول", []), ("bread", "نان", []), ("chair", "صندلی", []),
            ("music", "موسیقی", []), ("river", "رودخانه", []), ("smile", "لبخند", []), ("train", "قطار", []),
            ("beach", "ساحل", []), ("dream", "رویا", []), ("heart", "قلب", []), ("light", "نور", []),
            ("cloud", "ابر", []), ("plant", "گیاه", []), ("sleep", "خواب", []), ("world", "دنیا", []),
            ("learn", "یاد گرفتن", []), ("story", "داستان", []), ("voice", "صدا", []), ("phone", "تلفن", []),
            ("table", "میز", []), ("horse", "اسب", []), ("sweet", "شیرین", []), ("laugh", "خندیدن", []),
            ("night", "شب", []), ("friend", "دوست", []),
        ],
    },
]


def add_missing_games(conn: sqlite3.Connection) -> None:
    """Games added in later versions appear on existing installs too (switched off until enabled in the panel)."""
    have = {r[0] for r in conn.execute("SELECT slug FROM games")}
    seed(conn, [g for g in SEED_GAMES if g["slug"] not in have])


def seed(conn: sqlite3.Connection, games: list[dict] | None = None) -> None:
    for g in SEED_GAMES if games is None else games:
        cur = conn.execute(
            "INSERT INTO games (slug, kind, title, subtitle, rules, enabled, plays_per_mobile, period_days,"
            " code_valid_days, settings, created_at) VALUES (?,?,?,?,?,0,1,0,7,?,?)",
            (g["slug"], g["kind"], g["title"], g["subtitle"], g["rules"],
             json.dumps(g.get("settings", {}), ensure_ascii=False), now_iso()),
        )
        game_id = cur.lastrowid
        for word, answer, wrong in g.get("questions", []):
            conn.execute(
                "INSERT INTO questions (game_id, word, answer, wrong) VALUES (?,?,?,?)",
                (game_id, word, answer, json.dumps(wrong, ensure_ascii=False)),
            )


# ---------------------------------------------------------------- prize plan (approved by the owner, Oct 2026)

PLAN_VERSION = "2"
NO_CAP = 10_000_000  # rials = one course (~1M toman): in practice no cap, but the API needs a number
# wheel / scratch: everyone wins at least 10%; weight = out of 1000 plays; wheel order and colours
CHANCE_PLAN = [
    ("۱۰٪ تخفیف", 10, 500, "#F26600"),
    ("۳۰٪ تخفیف", 30, 140, "#33357D"),
    ("۲۰٪ تخفیف", 20, 280, "#FCE0CC"),
    ("۹۰٪ تخفیف", 90, 1, "#FFCC00"),
    ("۴۰٪ تخفیف", 40, 60, "#F7A366"),
    ("۵۰٪ تخفیف", 50, 19, "#572401"),
]
# quiz: (label, percent, correct answers needed)
QUIZ_PLAN = [("۱۰٪ تخفیف", 10, 0), ("۲۰٪ تخفیف", 20, 2), ("۳۰٪ تخفیف", 30, 3), ("۴۰٪ تخفیف", 40, 4),
             ("۵۰٪ تخفیف", 50, 5)]
# hidden word: (label, percent, score); score = 7 - guesses used when solved, 0 when not solved
WORDLE_PLAN = [("۱۰٪ تخفیف", 10, 0), ("۲۰٪ تخفیف", 20, 2), ("۳۰٪ تخفیف", 30, 3), ("۴۰٪ تخفیف", 40, 4),
               ("۵۰٪ تخفیف", 50, 5)]
OLD_RULES = {'wheel': 'هر شماره موبایل یک بار می\u200cتونه بچرخونه. کد تخفیف روی همون شماره در زبانیاد فعال می\u200cشه.', 'scratch': 'هر شماره موبایل یک بار می\u200cتونه کارت رو بخراشه.', 'words': '۵ کلمه، ۶۰ ثانیه. با ۳ جواب درست ۱۰٪، با ۴ جواب ۱۵٪ و با ۵ جواب ۲۵٪ تخفیف می\u200cگیری.'}
NEW_RULES = {'wheel': 'هر چرخش یک شانس مصرف می\u200cکند. همه برنده\u200cاند: از ۱۰٪ تا ۹۰٪ تخفیف! کد روی همان شماره در زبانیاد فعال می\u200cشود.', 'scratch': 'هر کارت یک شانس مصرف می\u200cکند. همه برنده\u200cاند: از ۱۰٪ تا ۹۰٪ تخفیف!', 'words': '۵ کلمه، ۶۰ ثانیه، یک شانس. ۰ تا ۱ جواب درست ۱۰٪، ۲ جواب ۲۰٪، ۳ جواب ۳۰٪، ۴ جواب ۴۰٪ و ۵ جواب ۵۰٪ تخفیف.'}


def apply_prize_plan(conn: sqlite3.Connection) -> None:
    """Puts the approved prize plan on each built-in game once (old prize rows stay, marked deleted).
    Done per game (settings key prize_plan:<slug>), so a new game gets its plan without touching edited ones."""
    done = {r[0] for r in conn.execute("SELECT key FROM settings WHERE key LIKE 'prize_plan%'")}
    legacy = conn.execute("SELECT value FROM settings WHERE key='prize_plan'").fetchone()
    legacy_done = bool(legacy and legacy[0] == PLAN_VERSION)  # v5 applied it to the first three games at once
    slugs = [g["slug"] for g in SEED_GAMES]
    todo = [g for g in db_games(conn, slugs)
            if f"prize_plan:{g['slug']}" not in done and not (legacy_done and g["slug"] in ("wheel", "scratch", "words"))]
    if not todo:
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        for g in todo:
            conn.execute("UPDATE prizes SET deleted=1, active=0 WHERE game_id=?", (g["id"],))
            if g["kind"] in ("quiz", "wordle"):
                plan = QUIZ_PLAN if g["kind"] == "quiz" else WORDLE_PLAN
                rows = [(label, pct, 1, score, DEFAULT_COLORS[i % len(DEFAULT_COLORS)])
                        for i, (label, pct, score) in enumerate(plan)]
            else:
                rows = [(label, pct, weight, 0, color) for label, pct, weight, color in CHANCE_PLAN]
            for i, (label, pct, weight, score, color) in enumerate(rows):
                conn.execute("INSERT INTO prizes (game_id, label, kind, amount, max_amount, weight, min_score, color,"
                             " sort) VALUES (?,?,?,?,?,?,?,?,?)",
                             (g["id"], label, "percentage", pct, NO_CAP, weight, score, color, i))
            if g["rules"] == OLD_RULES.get(g["slug"]):
                conn.execute("UPDATE games SET rules=? WHERE id=?", (NEW_RULES[g["slug"]], g["id"]))
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                         (f"prize_plan:{g['slug']}", PLAN_VERSION))
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def db_games(conn: sqlite3.Connection, slugs: list[str]) -> list:
    return conn.execute(f"SELECT id, slug, kind, rules FROM games WHERE slug IN ({','.join('?' * len(slugs))})",
                        slugs).fetchall()
