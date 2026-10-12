import httpx
import pytest

from app import config, discount, games
from app.util import normalize_mobile
from conftest import enable


def test_normalize_mobile():
    assert normalize_mobile("۰۹۱۲ ۳۴۵ ۶۷۸۹") == "09123456789"
    assert normalize_mobile("+989123456789") == "09123456789"
    assert normalize_mobile("9123456789") == "09123456789"
    assert normalize_mobile("0912345678") is None
    assert normalize_mobile("abc") is None


def test_disabled_game_is_closed(client):
    r = client.post("/api/games/wheel/play", json={"mobile": "09120000001"})
    assert r.status_code == 400 and r.json()["code"] == "closed"


def test_wheel_play_once_per_mobile(admin):
    enable(admin, "wheel")
    info = admin.get("/api/games/wheel").json()
    assert info["open"] and len(info["slices"]) == 8
    r = admin.post("/api/games/wheel/play", json={"mobile": "09120000002"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert info["slices"][body["prize_index"]]["label"] == body["prize_label"]
    if body["result"] == "won":
        assert body["code"].startswith("T")
    again = admin.post("/api/games/wheel/play", json={"mobile": "۰۹۱۲۰۰۰۰۰۰۲"})
    assert again.status_code == 429 and again.json()["code"] == "limit"


def test_stock_and_weights(admin):
    game = enable(admin, "scratch")
    for p in game["prizes"]:
        p["weight"] = 1 if p["label"] == "۲۵٪ تخفیف" else 0
        p["stock"] = 1 if p["label"] == "۲۵٪ تخفیف" else None
    game["prizes"][-1]["weight"] = 1  # "no prize" keeps a chance so the game can continue
    admin.put(f"/api/admin/games/{game['id']}", json=game)
    first = admin.post("/api/games/scratch/play", json={"mobile": "09120000003"}).json()
    second = admin.post("/api/games/scratch/play", json={"mobile": "09120000004"}).json()
    labels = [first["prize_label"], second["prize_label"]]
    assert labels.count("۲۵٪ تخفیف") <= 1
    won = [x for x in (first, second) if x["result"] == "won"]
    assert len(won) <= 1


def test_need_signup_does_not_count(admin, monkeypatch):
    game = enable(admin, "scratch")
    for p in game["prizes"]:
        p["weight"] = 1 if p["kind"] != "none" else 0
    admin.put(f"/api/admin/games/{game['id']}", json=game)

    def not_found(req):
        raise discount.DiscountError("user_not_found", "")
    monkeypatch.setattr(discount, "generate", not_found)
    r = admin.post("/api/games/scratch/play", json={"mobile": "09120000005"})
    assert r.status_code == 404 and r.json()["code"] == "need_signup"
    monkeypatch.undo()
    r = admin.post("/api/games/scratch/play", json={"mobile": "09120000005"})
    assert r.status_code == 200 and r.json()["result"] == "won"


def test_quiz_scoring(admin):
    enable(admin, "words")
    start = admin.post("/api/games/words/quiz/start", json={"mobile": "09120000006"}).json()
    assert len(start["questions"]) == 5
    from app import db
    with db.session() as conn:
        answers = {str(q["id"]): conn.execute("SELECT answer FROM questions WHERE id=?", (q["id"],)).fetchone()[0]
                   for q in start["questions"]}
    # 4 right, 1 wrong -> the 15% prize (min_score 4)
    first = start["questions"][0]
    answers[str(first["id"])] = next(o for o in first["options"] if o != answers[str(first["id"])])
    r = admin.post("/api/games/words/quiz/finish", json={"token": start["token"], "answers": answers}).json()
    assert r["score"] == 4 and r["result"] == "won" and r["prize_label"] == "۱۵٪ تخفیف"
    dup = admin.post("/api/games/words/quiz/finish", json={"token": start["token"], "answers": answers})
    assert dup.status_code == 409
    again = admin.post("/api/games/words/quiz/start", json={"mobile": "09120000006"})
    assert again.status_code == 429


def test_quiz_low_score_loses(admin):
    enable(admin, "words")
    start = admin.post("/api/games/words/quiz/start", json={"mobile": "09120000007"}).json()
    r = admin.post("/api/games/words/quiz/finish", json={"token": start["token"], "answers": {}}).json()
    assert r["score"] == 0 and r["result"] == "lost"


def test_admin_requires_login(client):
    assert client.get("/api/admin/games").status_code == 401
    assert client.post("/api/admin/login", json={"password": "wrong"}).status_code == 401


def test_admin_reports(admin):
    enable(admin, "wheel")
    admin.post("/api/games/wheel/play", json={"mobile": "09120000008"})
    stats = admin.get("/api/admin/stats").json()
    assert stats["totals"]["plays"] == 1
    plays = admin.get("/api/admin/plays", params={"q": "09120000008"}).json()
    assert plays["total"] == 1
    csv = admin.get("/api/admin/plays.csv")
    assert "09120000008" in csv.text


def test_admin_validation(admin):
    game = next(g for g in admin.get("/api/admin/games").json() if g["slug"] == "wheel")
    full = admin.get(f"/api/admin/games/{game['id']}").json()
    full["prizes"][0]["amount"] = 150
    r = admin.put(f"/api/admin/games/{game['id']}", json=full)
    assert r.status_code == 400


def test_create_and_delete_game(admin):
    r = admin.post("/api/admin/games", json={"slug": "spring-wheel", "kind": "wheel", "title": "گردونه بهار"})
    assert r.status_code == 200
    gid = r.json()["id"]
    assert admin.post("/api/admin/games", json={"slug": "spring-wheel", "kind": "wheel", "title": "x"}).status_code == 400
    assert admin.delete(f"/api/admin/games/{gid}").json()["ok"]


def test_quiz_questions_edit(admin):
    game = next(g for g in admin.get("/api/admin/games").json() if g["slug"] == "words")
    full = admin.get(f"/api/admin/games/{game['id']}").json()
    full["questions"] = full["questions"][:3] + [{"word": "cat", "answer": "گربه", "wrong": ["سگ", "موش"]}]
    r = admin.put(f"/api/admin/games/{game['id']}", json=full)
    assert r.status_code == 200, r.text
    active = [q for q in r.json()["questions"] if q["active"]]
    assert len(active) == 4 and active[-1]["word"] == "cat"


def test_live_api_call(monkeypatch):
    monkeypatch.setattr(config, "DISCOUNT_MODE", "live")
    monkeypatch.setattr(config, "DISCOUNT_API_SECRET", "s3cret")
    seen = {}

    def fake_post(url, json, headers, timeout):
        seen.update(url=url, body=json, headers=headers)
        return httpx.Response(201, json={"promotion_code": "A1B2C3D4"})
    monkeypatch.setattr(httpx, "post", fake_post)
    req = discount.CodeRequest(mobile="09123456789", type="percentage", amount=20, max_amount=100000,
                               usage_count=1, start_date="2026-10-09 15:29:49", end_date="2026-10-31 23:59:59")
    assert discount.generate(req) == "A1B2C3D4"
    assert seen["headers"]["X-Client-Secret"] == "s3cret"
    assert seen["body"]["email"] == "" and seen["body"]["type"] == "percentage"

    for status, kind in ((401, "unauthorized"), (404, "user_not_found"), (500, "server")):
        monkeypatch.setattr(httpx, "post", lambda *a, s=status, **k: httpx.Response(s, text="x"))
        with pytest.raises(discount.DiscountError) as exc:
            discount.generate(req)
        assert exc.value.kind == kind


def test_api_log_and_validity(admin):
    r = admin.post("/api/admin/test-code", json={"mobile": "09120000099", "amount": 5}).json()
    assert r["ok"] and r["valid_from"].endswith("00:00:00")
    rows = admin.get("/api/admin/api-log").json()
    assert rows and "09120000099" in rows[0]["request"] and '"max_amount": 1000000' in rows[0]["request"]
    assert "Secret" not in rows[0]["request"]


def test_percentage_prize_needs_cap(admin):
    game = next(g for g in admin.get("/api/admin/games").json() if g["slug"] == "wheel")
    full = admin.get(f"/api/admin/games/{game['id']}").json()
    full["prizes"][0]["max_amount"] = 0
    assert admin.put(f"/api/admin/games/{game['id']}", json=full).status_code == 400
