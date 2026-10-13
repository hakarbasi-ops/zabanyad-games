import httpx

from app import config
from conftest import enable


def test_kavenegar_send(client, monkeypatch):
    monkeypatch.setattr(config, "SMS_MODE", "kavenegar")
    monkeypatch.setattr(config, "KAVENEGAR_API_KEY", "k3y")
    monkeypatch.setattr(config, "KAVENEGAR_TEMPLATE", "zgames")
    seen = {}

    def fake_get(url, params, timeout):
        seen.update(url=url, params=params)
        return httpx.Response(200, json={"return": {"status": 200, "message": "تایید شد"}, "entries": []})
    monkeypatch.setattr(httpx, "get", fake_get)
    r = client.post("/api/otp/send", json={"mobile": "09120000601"})
    assert r.status_code == 200 and "test_code" not in r.json()
    assert seen["url"].endswith("/k3y/verify/lookup.json")
    assert seen["params"]["receptor"] == "09120000601" and seen["params"]["template"] == "zgames"
    assert len(seen["params"]["token"]) == 5


def test_kavenegar_failure_lets_player_retry(client, monkeypatch):
    monkeypatch.setattr(config, "SMS_MODE", "kavenegar")
    monkeypatch.setattr(config, "KAVENEGAR_API_KEY", "k3y")
    monkeypatch.setattr(config, "KAVENEGAR_TEMPLATE", "zgames")
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(418, json={"return": {"status": 418}}))
    r = client.post("/api/otp/send", json={"mobile": "09120000602"})
    assert r.status_code == 503
    # the failed send did not start the 60-second wait
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(200, json={"return": {"status": 200}}))
    assert client.post("/api/otp/send", json={"mobile": "09120000602"}).status_code == 200


def test_my_codes(admin):
    enable(admin, "wheel")
    for _ in range(2):
        admin.post("/api/games/wheel/play", json={"mobile": "09120000701"})
    data = admin.post("/api/my-codes", json={"mobile": "09120000701"}).json()
    assert len(data["codes"]) == 2 and all(not c["expired"] and c["valid_until"] for c in data["codes"])
    assert data["wallet"]["chances"] == 1
    assert admin.get("/my").status_code == 200


def test_out_of_chances_message_mentions_invites(admin):
    enable(admin, "wheel")
    admin.put("/api/admin/chance-settings", json={"referral_enabled": 1, "start_chances": 0})
    r = admin.post("/api/games/wheel/play", json={"mobile": "09120000801"})
    assert r.status_code == 429 and "دعوت" in r.json()["detail"]
