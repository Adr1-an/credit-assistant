"""Паспортные тесты P01–P16 из tests/passport-tests.json: запрос → заглушка → корзина сервера."""
import pytest

from app.services.checks import _request, eval_passport
from conftest import load

TESTS = load("passport-tests.json")["tests"]


@pytest.mark.parametrize("t", TESTS, ids=[t["id"] for t in TESTS])
def test_passport_case(t, client):
    verdict = eval_passport(_request("POST", "/passport/check", t["request"]))
    expected = t["serverResult"]
    if t["expected"]["status"] == 400:
        # «Ошибка ввода, не STOP»: сервер не пускает такой паспорт уже на шаге 1
        r = client.post("/api/applications", json={"passport": t["request"], "hasBusiness": False})
        assert r.status_code == 400 and r.json()["code"] == "PASSPORT_INVALID"
        assert verdict.basket != "STOP"
    elif expected.startswith("state=ERROR"):
        assert (verdict.state, verdict.basket) == ("ERROR", "NONE")
    else:
        code, basket = [x.strip() for x in expected.split("/")]
        assert (verdict.code, verdict.basket) == (code, basket)
