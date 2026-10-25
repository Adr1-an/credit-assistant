"""Шаги 1–3: создание заявки, согласие, проверки — сверка с tests/expected-results.json."""
import pytest

from conftest import load

ALL_CODES = [c["code"] for c in load("cases.json")["cases"]]


def create(client, case, **override):
    body = {"passport": case["passport"], "hasBusiness": case["hasBusiness"], "inn": case["inn"], **override}
    return client.post("/api/applications", json=body)


@pytest.mark.parametrize("code", ALL_CODES)
def test_checks_match_expected(client, cases, expected, code):
    case, exp = cases[code], expected[code]
    r = create(client, case)
    assert r.status_code == 201, r.text
    app_id = r.json()["id"]

    r = client.post(f"/api/applications/{app_id}/consent", json={"agreed": True})
    app = client.get(f"/api/applications/{app_id}").json()

    # Корзины по каждой проверке
    got = [(c["source"], c["state"], c["basket"]) for c in app["checks"]]
    want = [(c["source"], c["state"], c["basket"]) for c in exp["checks"]]
    assert got == want
    for g, w in zip(app["checks"], exp["checks"]):
        if w["code"]:
            assert g.get("code") == w["code"], g
    # Статус после согласия
    assert app["status"] == exp["statusAfterConsent"]
    if exp["statusAfterConsent"] == "CHECKING":
        assert r.status_code == 503 and r.json()["code"] == "SERVICE_UNAVAILABLE"
        assert app["nextAction"] == exp["nextActionAfterConsent"] == "RETRY_CHECKS"
    else:
        assert r.status_code == 200, r.text
    if app["status"] == "REJECTED":
        assert app["rejection"]["text"] and len(app["rejection"]["advice"]) <= 3
    # Клиенту никогда не показываем баллы
    assert "score" not in r.text.lower() or r.status_code == 503


def test_retry_checks_still_unavailable(client, cases):
    app_id = create(client, cases["T10"]).json()["id"]
    client.post(f"/api/applications/{app_id}/consent", json={"agreed": True})
    r = client.post(f"/api/applications/{app_id}/checks")
    assert r.status_code == 503
    assert client.get(f"/api/applications/{app_id}").json()["status"] == "CHECKING"


def test_repeat_application_returns_open_one(client, cases):
    first = create(client, cases["T01"])
    second = create(client, cases["T01"])
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_repeat_without_inn_matches_by_passport(client, cases):
    case = cases["T05"]
    first = create(client, case, inn=None)
    second = create(client, case, inn=None)
    assert second.status_code == 200 and first.json()["id"] == second.json()["id"]


def test_rejected_application_is_not_reused(client, cases):
    first = create(client, cases["T04"]).json()["id"]
    client.post(f"/api/applications/{first}/consent", json={"agreed": True})
    second = create(client, cases["T04"])
    assert second.status_code == 201 and second.json()["id"] != first


def test_inn_checksum(client, cases):
    r = create(client, cases["T01"], inn="990001000165")
    assert r.status_code == 400 and r.json()["code"] == "INN_INVALID"
    r = create(client, cases["T01"], inn="12345")
    assert r.status_code == 400 and r.json()["code"] == "INN_INVALID"


def test_passport_format(client, cases):
    bad = {**cases["T01"]["passport"], "series": "99A0"}
    r = create(client, cases["T01"], passport=bad)
    assert r.status_code == 400 and r.json()["code"] == "PASSPORT_INVALID"
    bad = {**cases["T01"]["passport"], "birthDate": "1988-02-30"}
    assert create(client, cases["T01"], passport=bad).json()["code"] == "PASSPORT_INVALID"


def test_business_requires_inn(client, cases):
    r = create(client, cases["T01"], inn=None)
    assert r.status_code == 400 and r.json()["details"]["missingField"] == "inn"


def test_startup_consent_without_inn(client, cases):
    app_id = create(client, cases["T05"], inn=None).json()["id"]
    r = client.post(f"/api/applications/{app_id}/consent", json={"agreed": True})
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"
    assert r.json()["details"]["missingField"] == "inn"
    assert client.get(f"/api/applications/{app_id}").json()["status"] == "DRAFT"


def test_business_inn_not_ip_goes_back_to_draft(client, cases):
    # Личный ИНН стартапа (ЕГРИП отвечает NOT_IP), но человек говорит, что ИП есть
    app_id = create(client, cases["T05"], hasBusiness=True).json()["id"]
    r = client.post(f"/api/applications/{app_id}/consent", json={"agreed": True})
    assert r.status_code == 422 and r.json()["code"] == "NOT_IP"
    assert client.get(f"/api/applications/{app_id}").json()["status"] == "DRAFT"


def test_consent_rules(client, cases):
    app_id = create(client, cases["T01"]).json()["id"]
    assert client.post(f"/api/applications/{app_id}/consent", json={"agreed": False}).status_code == 400
    assert client.post(f"/api/applications/{app_id}/checks").status_code == 409
    assert client.post(f"/api/applications/{app_id}/consent", json={"agreed": True}).status_code == 200
    r = client.post(f"/api/applications/{app_id}/consent", json={"agreed": True})
    assert r.status_code == 409 and r.json()["code"] == "INVALID_STATUS"


def test_unknown_application(client):
    r = client.get("/api/applications/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404 and r.json()["code"] == "NOT_FOUND"


def test_reference_endpoints(client):
    assert client.get("/api/health").json() == {"status": "ok", "aiAvailable": False}
    qs = client.get("/api/question-sets").json()
    assert qs["version"] == "0.2" and len(qs["goals"]) == 8
    assert client.get("/api/okved", params={"query": "хлеб"}).json()[0]["code"] == "10.71"
    assert client.get("/api/okved", params={"query": "45"}).json()[0]["code"] == "45.20"
    assert client.get("/api/okved", params={"query": "х"}).status_code == 400
    demo = client.get("/api/demo/clients").json()
    assert len(demo) == 10 and demo[0]["inn"] == "990001000164"
    r = client.get("/api/demo/statements/990001000164")
    assert r.status_code == 200 and r.text.startswith("date;amount;direction")
    assert client.get("/api/demo/statements/990001000485").status_code == 404
