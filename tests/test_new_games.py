from app import db, games
from conftest import enable


def test_new_games_seeded_with_plan(admin):
    slugs = {g["slug"]: g for g in admin.get("/api/admin/games").json()}
    assert {"chest", "slot", "hidden-word"} <= set(slugs)
    chest = admin.get(f"/api/admin/games/{slugs['chest']['id']}").json()
    assert sorted(p["weight"] for p in chest["prizes"] if p["active"]) == [1, 19, 60, 140, 280, 500]


def test_chest_and_slot_play(admin):
    for slug in ("chest", "slot"):
        enable(admin, slug)
        r = admin.post(f"/api/games/{slug}/play", json={"mobile": "09120000901"}).json()
        assert r["result"] == "won" and r["prize_label"].endswith("تخفیف")


def test_wordle_feedback_repeats():
    assert games.wordle_feedback("apple", "paper") == ["present", "present", "correct", "present", "absent"]
    assert games.wordle_feedback("apple", "ppppp") == ["absent", "correct", "correct", "absent", "absent"]


def _word(token):
    with db.session() as conn:
        play = db.row(conn.execute("SELECT data FROM plays WHERE token=?", (token,)).fetchone())
        return conn.execute("SELECT word FROM questions WHERE id=?", (play["data"]["qid"],)).fetchone()[0]


def test_wordle_solved_in_two(admin):
    enable(admin, "hidden-word")
    s = admin.post("/api/games/hidden-word/wordle/start", json={"mobile": "09120000902"}).json()
    word = _word(s["token"])
    assert s["length"] == len(word) and s["hint"] and s["chances"] == 2
    wrong = ("z" * len(word))
    r1 = admin.post("/api/games/hidden-word/wordle/guess", json={"token": s["token"], "guess": wrong}).json()
    assert r1["done"] is False and r1["guesses"] == 1
    bad = admin.post("/api/games/hidden-word/wordle/guess", json={"token": s["token"], "guess": "ab"})
    assert bad.status_code == 400
    r2 = admin.post("/api/games/hidden-word/wordle/guess", json={"token": s["token"], "guess": word.upper()}).json()
    assert r2["done"] and r2["solved"] and r2["guesses"] == 2 and r2["prize_label"] == "۵۰٪ تخفیف"
    again = admin.post("/api/games/hidden-word/wordle/guess", json={"token": s["token"], "guess": word})
    assert again.status_code == 409


def test_wordle_failed_still_wins_10(admin):
    enable(admin, "hidden-word")
    s = admin.post("/api/games/hidden-word/wordle/start", json={"mobile": "09120000903"}).json()
    wrong = "z" * s["length"]
    for _ in range(6):
        r = admin.post("/api/games/hidden-word/wordle/guess", json={"token": s["token"], "guess": wrong}).json()
    assert r["done"] and not r["solved"] and r["prize_label"] == "۱۰٪ تخفیف" and r["answer"]


def test_new_game_from_panel_gets_plan(admin):
    g = admin.post("/api/admin/games", json={"slug": "my-slot", "kind": "slot", "title": "اسلات"}).json()
    assert len([p for p in g["prizes"] if p["active"]]) == 6
