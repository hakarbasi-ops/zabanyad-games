import os
import sys
import tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="zg-test-")
os.environ["DISCOUNT_MODE"] = "mock"
os.environ["DISCOUNT_API_SECRET"] = ""
os.environ["ADMIN_PASSWORD"] = "test-pass"
os.environ["TRUST_PROXY"] = "0"
os.environ["OTP_REQUIRED"] = "0"
os.environ["SMS_MODE"] = "mock"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from app import config, db


@pytest.fixture()
def client():
    for suffix in ("", "-wal", "-shm"):
        Path(str(config.DB_PATH) + suffix).unlink(missing_ok=True)
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def admin(client):
    r = client.post("/api/admin/login", json={"password": "test-pass"})
    assert r.status_code == 200
    return client


def enable(admin, slug, **changes):
    game = next(g for g in admin.get("/api/admin/games").json() if g["slug"] == slug)
    full = admin.get(f"/api/admin/games/{game['id']}").json()
    full.update({"enabled": True, **changes})
    r = admin.put(f"/api/admin/games/{game['id']}", json=full)
    assert r.status_code == 200, r.text
    return r.json()
