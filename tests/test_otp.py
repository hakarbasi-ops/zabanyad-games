from app import config, otp
from conftest import enable


def test_play_needs_verified_mobile(admin, monkeypatch):
    monkeypatch.setattr(config, "OTP_REQUIRED", True)
    enable(admin, "wheel")
    assert admin.get("/api/games/wheel").json()["otp"] is True

    r = admin.post("/api/games/wheel/play", json={"mobile": "09120000101"})
    assert r.status_code == 401 and r.json()["code"] == "need_otp"

    sent = admin.post("/api/otp/send", json={"mobile": "09120000101"}).json()
    code = sent["test_code"]
    assert len(code) == 5
    wrong = admin.post("/api/otp/verify", json={"mobile": "09120000101", "code": "00000" if code != "00000" else "11111"})
    assert wrong.status_code == 400 and wrong.json()["code"] == "otp_wrong"
    token = admin.post("/api/otp/verify", json={"mobile": "09120000101", "code": code}).json()["token"]

    # token is bound to its own mobile
    other = admin.post("/api/games/wheel/play", json={"mobile": "09120000102", "otp_token": token})
    assert other.status_code == 401
    ok = admin.post("/api/games/wheel/play", json={"mobile": "09120000101", "otp_token": token})
    assert ok.status_code == 200, ok.text

    # a used code cannot be reused
    again = admin.post("/api/otp/verify", json={"mobile": "09120000101", "code": code})
    assert again.status_code == 400


def test_resend_wait_and_lockout(client):
    assert client.post("/api/otp/send", json={"mobile": "09120000103"}).status_code == 200
    r = client.post("/api/otp/send", json={"mobile": "09120000103"})
    assert r.status_code == 429 and r.json()["code"] == "otp_wait"
    for _ in range(otp.MAX_TRIES):
        client.post("/api/otp/verify", json={"mobile": "09120000103", "code": "99999x"})
    r = client.post("/api/otp/verify", json={"mobile": "09120000103", "code": "12345"})
    assert r.json()["code"] == "otp_locked"


def test_real_sms_mode_without_provider_refuses(client, monkeypatch):
    monkeypatch.setattr(config, "SMS_MODE", "zabanyad")
    r = client.post("/api/otp/send", json={"mobile": "09120000104"})
    assert r.status_code == 503 and "test_code" not in r.text
