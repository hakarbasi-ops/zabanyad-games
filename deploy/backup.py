"""Daily copy of the SQLite database: backup.py <db> <dir> <keep_days>."""
import sqlite3
import sys
import time
from pathlib import Path

db, folder, keep = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
folder.mkdir(parents=True, exist_ok=True)
target = folder / f"games-{time.strftime('%Y%m%d')}.db"
with sqlite3.connect(db) as src, sqlite3.connect(target) as dst:
    src.backup(dst)
for old in folder.glob("games-*.db"):
    if old.stat().st_mtime < time.time() - keep * 86400:
        old.unlink()
