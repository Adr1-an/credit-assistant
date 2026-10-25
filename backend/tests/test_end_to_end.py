"""Сквозной тест: каждый из 16 случаев проходит воронку через API и сверяется с tests/expected-results.json —
баллы по факторам, зона, статус, причины MANUAL, смета, предложения, рекомендация, договор T01."""
import pytest

from conftest import TESTS_DATA, load

ALL = load("cases.json")["cases"]
SCORED = [c["code"] for c in ALL if c["code"] not in ("T04", "T10")]


def run_until_submit(client, case):
    r = client.post("/api/applications", json={"passport": case["passport"], "hasBusiness": case["hasBusiness"],
                                               "inn": case["inn"]})
    app_id = r.json()["id"]
    r = client.post(f"/api/applications/{app_id}/consent", json={"agreed": True})
    assert r.json()["status"] == "COLLECTING", r.text
    if case["statementFile"]:
        raw = (TESTS_DATA / case["statementFile"]).read_bytes()
        r = client.post(f"/api/applications/{app_id}/statement", files={"file": ("st.csv", raw, "text/csv")})
        assert r.status_code == 200, r.text
    if case["questionnaire"]:
        r = client.post(f"/api/applications/{app_id}/questionnaire", json=case["questionnaire"])
        assert r.status_code == 200, r.text
        assert r.json()["hasQuestionnaire"] is True
    assert client.get(f"/api/applications/{app_id}").json()["nextAction"] == "SET_GOALS"
    r = client.put(f"/api/applications/{app_id}/goals", json=case["goalsData"])
    assert r.status_code == 200, r.text
    assert client.get(f"/api/applications/{app_id}").json()["nextAction"] == "REVIEW_ESTIMATE"
    r = client.post(f"/api/applications/{app_id}/submit")
    assert r.status_code == 200, r.text
    return app_id, r.json()


def strip_items(items):
    return [{k: v for k, v in i.items() if k != "excluded"} for i in items]


@pytest.mark.parametrize("code", SCORED)
def test_case_end_to_end(client, cases, expected, code):
    case, exp = cases[code], expected[code]
    app_id, app = run_until_submit(client, case)
    assert app["status"] == exp["statusAfterSubmit"]
    # клиенту — никаких баллов и зон
    assert all(k not in app for k in ("score", "zone", "factors"))

    card = client.get(f"/api/staff/applications/{app_id}").json()
    score = card["score"]
    assert score["total"] == exp["score"]["total"]
    assert score["zone"] == exp["score"]["zone"]
    assert [(f["code"], f["block"], f["points"], f["maxPoints"]) for f in score["factors"]] == \
           [(f["code"], f["block"], f["points"], f["maxPoints"]) for f in exp["score"]["factors"]]
    assert all(f["reason"] for f in score["factors"])
    manual_flags = sorted({f["code"] for f in score.get("flags", []) if f["basket"] == "MANUAL"})
    assert manual_flags == exp["manualReasons"]

    if "estimate" in exp:
        est = card["estimate"]
        assert strip_items(est["items"]) == exp["estimate"]["items"]
        assert est["total"] == exp["estimate"]["total"]
        assert est["startSmallerSuggested"] == exp["estimate"]["startSmallerSuggested"]
        assert card["recommendation"]["action"] == exp["recommendation"]["action"]
        if exp["statusAfterSubmit"] == "OFFER_READY":
            offers = client.get(f"/api/applications/{app_id}/offers").json()
        else:
            # Сотрудник видит заранее посчитанные предложения; клиенту они пока недоступны
            offers = card["offers"]
            assert client.get(f"/api/applications/{app_id}/offers").status_code == 409
        assert offers == exp["offers"]

    if app["status"] == "MANUAL_REVIEW":
        assert app["reviewDeadline"] and app["nextAction"] == "WAIT"
        assert app["statusText"].startswith("Заявка у специалиста. Ответ до ")
    if app["status"] == "REJECTED":
        assert app["rejection"]["advice"]


def test_t01_contract_sign_and_after(client, cases, expected):
    exp = expected["T01"]
    app_id, _ = run_until_submit(client, cases["T01"])
    r = client.post(f"/api/applications/{app_id}/offers/main/select")
    assert r.status_code == 200 and r.json()["status"] == "SIGNING" and r.json()["nextAction"] == "SIGN"

    contract = client.get(f"/api/applications/{app_id}/contract").json()
    ce = exp["contractExample"]
    assert contract["clauses"] == ce["clauses"]
    assert contract["summary"] == ce["summary"]
    assert contract["faq"] == ce["faq"]
    for qid, answer in ce["faqAnswers"].items():
        a = client.post(f"/api/applications/{app_id}/contract/ask", json={"questionId": qid}).json()
        assert a == {"answer": answer, "source": "FAQ",
                     "disclaimer": "Пояснение справочное и не заменяет юридическую консультацию."}
    r = client.post(f"/api/applications/{app_id}/contract/ask", json={"text": "А если я уеду в отпуск?"})
    assert r.status_code == 503 and r.json()["code"] == "AI_UNAVAILABLE"

    # Подпись: сначала неверный код, потом верный
    code = client.post(f"/api/applications/{app_id}/sign/code").json()["code"]
    wrong = "000000" if code != "000000" else "111111"
    r = client.post(f"/api/applications/{app_id}/sign", json={"code": wrong, "understood": True})
    assert r.status_code == 400 and r.json()["code"] == "CODE_INVALID"
    r = client.post(f"/api/applications/{app_id}/sign", json={"code": code, "understood": False})
    assert r.status_code == 400
    r = client.post(f"/api/applications/{app_id}/sign", json={"code": code, "understood": True})
    assert r.status_code == 200 and r.json()["status"] == "ISSUED" and r.json()["nextAction"] == "NONE"

    # График: без овердрафта, первый платёж 24.11.2026, весь долг гасится
    sch = client.get(f"/api/applications/{app_id}/schedule").json()
    main = exp["offers"][0]
    assert sch["payments"][0]["date"] == "2026-11-24"
    assert sch["payments"][0]["total"] == main["firstMonthsPayment"] - 6000   # минус проценты овердрафта
    assert sch["remainingDebt"] == main["totalAmount"] - 360000                # овердрафт в график не входит
    assert len(sch["payments"]) == 36
    assert sum(p["interest"] for p in sch["payments"]) == main["overpayment"]

    # После выдачи: падение выручки → предложение помощи → перенос платежа
    assert client.post(f"/api/demo/applications/{app_id}/advance-month", json={"scenario": "NORMAL"}).json() == []
    notes = client.post(f"/api/demo/applications/{app_id}/advance-month", json={"scenario": "REVENUE_DROP"}).json()
    assert notes[0]["kind"] == "EARLY_WARNING"
    assert notes[0]["options"] == ["POSTPONE_PAYMENT", "INTEREST_ONLY", "RESTRUCTURE", "DECLINE"]
    sch = client.post(f"/api/applications/{app_id}/notifications/{notes[0]['id']}/choose",
                      json={"option": "POSTPONE_PAYMENT"}).json()
    statuses = [p["status"] for p in sch["payments"]]
    assert statuses[:3] == ["PAID", "PAID", "POSTPONED"] and len(statuses) == 37
    r = client.post(f"/api/applications/{app_id}/notifications/{notes[0]['id']}/choose", json={"option": "DECLINE"})
    assert r.status_code == 409

    # Ещё одно падение → «2 месяца только проценты»: долг тот же, срок +2
    debt = sch["remainingDebt"]
    notes = client.post(f"/api/demo/applications/{app_id}/advance-month", json={"scenario": "REVENUE_DROP"}).json()
    sch2 = client.post(f"/api/applications/{app_id}/notifications/{notes[0]['id']}/choose",
                       json={"option": "INTEREST_ONLY"}).json()
    up = [p for p in sch2["payments"] if p["status"] == "UPCOMING"]
    assert up[0]["principal"] == 0 and up[1]["principal"] == 0
    assert sch2["remainingDebt"] == sum(p["principal"] for p in sch["payments"]
                                        if p["status"] == "UPCOMING") - sch["nextPayment"]["principal"]
    assert debt > sch2["remainingDebt"] > 0

    # Рост 3 месяца подряд → банк предлагает больший лимит овердрафта
    for _ in range(2):
        assert client.post(f"/api/demo/applications/{app_id}/advance-month", json={"scenario": "GROWTH"}).json() == []
    notes = client.post(f"/api/demo/applications/{app_id}/advance-month", json={"scenario": "GROWTH"}).json()
    assert notes[0]["kind"] == "LIMIT_INCREASE" and "450 000" in notes[0]["text"]
    client.post(f"/api/applications/{app_id}/notifications/{notes[0]['id']}/choose", json={"option": "ACCEPT_LIMIT"})
    all_notes = client.get(f"/api/applications/{app_id}/notifications").json()
    assert all_notes[-1]["kind"] == "INFO"

    history = client.get(f"/api/staff/applications/{app_id}").json()["history"]
    assert [h["toStatus"] for h in history][:6] == ["DRAFT", "CHECKING", "COLLECTING", "OFFER_READY", "SIGNING", "ISSUED"]
