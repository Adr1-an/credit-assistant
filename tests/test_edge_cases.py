"""Крайние случаи: плохие выписки, проверка ответов, правка сметы, handoff, решения сотрудника,
запрос данных, диалог без ИИ, истёкший код подписи."""
import datetime as dt

import pytest

from conftest import TESTS_DATA
from test_end_to_end import run_until_submit


def collecting(client, case):
    app_id = client.post("/api/applications", json={"passport": case["passport"], "hasBusiness": case["hasBusiness"],
                                                    "inn": case["inn"]}).json()["id"]
    assert client.post(f"/api/applications/{app_id}/consent", json={"agreed": True}).json()["status"] == "COLLECTING"
    return app_id


def upload(client, app_id, path):
    raw = (TESTS_DATA / path).read_bytes()
    return client.post(f"/api/applications/{app_id}/statement", files={"file": ("st.csv", raw, "text/csv")})


# ---------- выписка ----------
@pytest.mark.parametrize("name", ["empty.csv", "not-csv.csv", "wrong-columns.csv", "bad-amount.csv"])
def test_bad_statements(client, cases, name):
    app_id = collecting(client, cases["T01"])
    r = upload(client, app_id, f"statements/bad/{name}")
    assert r.status_code == 400 and r.json()["code"] == "STATEMENT_UNREADABLE"
    assert client.get(f"/api/applications/{app_id}").json()["hasStatement"] is False


def test_short_statement_accepted_with_warnings(client, cases):
    app_id = collecting(client, cases["T01"])
    s = upload(client, app_id, "statements/bad/short-2-months.csv").json()
    assert s["monthsCovered"] == 2
    assert "Выписка подтверждает 2 из 12 календарных месяцев" in s["warnings"]


def test_missing_february(client, cases):
    app_id = collecting(client, cases["E04"])
    s = upload(client, app_id, "statements/990001012674.csv").json()
    assert s["monthsCovered"] == 11
    assert "2026-02" not in [m["month"] for m in s["monthly"]]
    assert "Нет операций за 2026-02 — период не подтверждён" in s["warnings"]
    assert "Выписка подтверждает 11 из 12 календарных месяцев" in s["warnings"]


def test_statement_summary_t01(client, cases):
    app_id = collecting(client, cases["T01"])
    s = upload(client, app_id, "statements/990001000164.csv").json()
    assert (s["periodFrom"][:7], s["periodTo"][:7], s["monthsCovered"]) == ("2025-10", "2026-09", 12)
    assert s["avgMonthlyIncome"] == 1200000 and s["avgMonthlyExpense"] == 900000
    assert s["otherBankLoanPaymentsMonthly"] == 25000
    assert set(s["expenseByCategory"]) <= {"RENT", "SALARY", "MATERIALS", "TAXES", "LOAN_PAYMENTS", "OTHER"}
    assert s["warnings"] == []


def test_classification_examples():
    from app.services.statement import classify_in
    for purpose, inn, exp in [("Оплата по договору поставки №15", "7801234567", "CUSTOMER"),
                              ("Эквайринг. Реестр операций по картам", "", "ACQUIRING"),
                              ("Зачисление кредита по договору", "7701234567", "OTHER_IN"),
                              ("Возврат оплаты по договору", "7701234567", "OTHER_IN"),
                              ("Оплата по счету", "", "OTHER_IN"), ("СБП перевод", "", "OTHER_IN"),
                              ("Оплата услуг", "7701234567", "CUSTOMER")]:
        assert classify_in(purpose, inn) == exp, purpose


def test_other_in_over_20_percent_is_manual():
    from app.services.statement import parse_statement
    rows = ["date;amount;direction;counterparty;counterpartyInn;purpose"]
    for m in range(1, 10):
        rows.append(f"2026-0{m}-05;100;IN;ООО А;7701234567;Оплата по договору")
        rows.append(f"2026-0{m}-06;100;IN;ИП Б;;Пополнение счета")
    summary, internal = parse_statement("\n".join(rows).encode(), dt.date(2026, 10, 24))
    assert "Более 20% входящих операций не удалось подтвердить как выручку" in summary["warnings"]
    assert summary["avgMonthlyIncome"] == 100


def test_future_date_rejected(client, cases):
    from app.errors import ApiError
    from app.services.statement import parse_statement
    with pytest.raises(ApiError) as e:
        parse_statement(b"date;amount;direction;counterparty;counterpartyInn;purpose\n2026-12-01;5;IN;a;;b\n",
                        dt.date(2026, 10, 24))
    assert e.value.code == "STATEMENT_UNREADABLE"


# ---------- анкета и цели ----------
def test_questionnaire_limits(client, cases):
    app_id = collecting(client, cases["T07"])
    r = client.post(f"/api/applications/{app_id}/questionnaire", json={"monthlyRevenue": 200_000_000, "monthlyExpenses": 1})
    assert r.status_code == 400 and r.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("goals, problem", [
    ({"source": "FORM", "goals": [{"goalType": "INVENTORY", "answers": [
        {"questionId": "inventory.items", "value": "Товар"}]}]}, "обязательный вопрос без ответа"),
    ({"source": "FORM", "goals": [{"goalType": "INVENTORY", "answers": [
        {"questionId": "inventory.items", "value": "   "}, {"questionId": "inventory.amount", "value": 1000}]}]},
     "текст от 1 до 1000 символов"),
    ({"source": "FORM", "goals": [{"goalType": "INVENTORY", "answers": [
        {"questionId": "inventory.items", "value": "Товар"}, {"questionId": "inventory.amount", "value": None}]}]},
     "ответ «не знаю» для этого вопроса не допускается"),
    ({"source": "FORM", "goals": [{"goalType": "INVENTORY", "answers": [
        {"questionId": "inventory.items", "value": "Товар"}, {"questionId": "inventory.amount", "value": 0}]}]},
     "число должно быть от 1 до 100000000"),
    ({"source": "FORM", "goals": [{"goalType": "EQUIPMENT", "answers": [
        {"questionId": "equipment.what", "value": "Станок"}, {"questionId": "equipment.price", "value": 10},
        {"questionId": "equipment.purpose", "value": "OTHER"}]}]}, "допустимо: REPLACEMENT, EXPANSION"),
    ({"source": "FORM", "goals": [{"goalType": "CASH_GAP", "answers": [
        {"questionId": "cashgap.amount", "value": 1000}, {"questionId": "cashgap.regular", "value": "true"}]}]},
     "нужно true или false"),
    ({"source": "FORM", "goals": [{"goalType": "CASH_GAP", "answers": [
        {"questionId": "cashgap.amount", "value": 1000}, {"questionId": "inventory.amount", "value": 5}]}]},
     "такого вопроса нет в этой группе"),
    ({"source": "FORM", "goals": [{"goalType": "START_BUSINESS", "answers": [
        {"questionId": "start.okved", "value": "99.99"}, {"questionId": "start.ownFunds", "value": 0},
        {"questionId": "start.experience", "value": 1}]}]}, "код ОКВЭД не найден в справочнике"),
    ({"source": "FORM", "goals": [{"goalType": "CASH_GAP", "answers": [{"questionId": "cashgap.amount", "value": 1}]},
                                  {"goalType": "CASH_GAP", "answers": [{"questionId": "cashgap.amount", "value": 1}]}]},
     "одна и та же цель указана дважды"),
])
def test_goal_validation(client, cases, goals, problem):
    app_id = collecting(client, cases["T05"])
    r = client.put(f"/api/applications/{app_id}/goals", json=goals)
    assert r.status_code == 400 and r.json()["code"] == "VALIDATION_ERROR"
    assert problem in [p["problem"] for p in r.json()["details"]["problems"]], r.json()


def test_submit_requires_steps(client, cases):
    app_id = collecting(client, cases["T01"])
    r = client.post(f"/api/applications/{app_id}/submit")
    assert r.status_code == 409 and r.json()["details"]["missing"] == ["statement", "goals"]
    assert client.get(f"/api/applications/{app_id}/estimate").status_code == 404


def test_missing_equipment_price_goes_to_info_requested(client, cases):
    app_id = collecting(client, cases["T08"])
    upload(client, app_id, "statements/990001000870.csv")
    client.put(f"/api/applications/{app_id}/goals", json={"source": "FORM", "goals": [{"goalType": "EQUIPMENT", "answers": [
        {"questionId": "equipment.what", "value": "Машина"}, {"questionId": "equipment.price", "value": None},
        {"questionId": "equipment.purpose", "value": "EXPANSION"}]}]})
    app = client.post(f"/api/applications/{app_id}/submit").json()
    assert app["status"] == "INFO_REQUESTED" and app["nextAction"] == "ANSWER_INFO_REQUEST"
    assert app["infoRequest"] == {"text": "Укажите стоимость оборудования", "requestedBy": "SYSTEM"}
    assert app["statusText"] == "Нужно уточнение: Укажите стоимость оборудования"
    r = client.post(f"/api/applications/{app_id}/info-response", data={"text": "Стоит 900 000"})
    assert r.status_code == 200 and r.json()["status"] == "MANUAL_REVIEW"


# ---------- смета ----------
def test_estimate_edit(client, cases):
    app_id = collecting(client, cases["T02"])
    upload(client, app_id, "statements/990001000238.csv")
    est = client.put(f"/api/applications/{app_id}/goals", json=cases["T02"]["goalsData"]).json()
    assert [(i["product"], i["amount"]) for i in est["items"]] == [("LEASING", 800000), ("OVERDRAFT", 80000)]
    # дешевле 300 000 — уже не лизинг, а инвестиционный кредит; подушка пересчитывается
    est = client.put(f"/api/applications/{app_id}/estimate", json={"items": [{"id": "i1", "amount": 250001}]}).json()
    assert [(i["product"], i["amount"]) for i in est["items"]] == [("INVESTMENT_LOAN", 260000), ("OVERDRAFT", 30000)]
    assert est["total"] == 290000
    est = client.put(f"/api/applications/{app_id}/estimate", json={"items": [{"id": "i2", "excluded": True}]}).json()
    assert est["total"] == 260000
    assert client.get(f"/api/applications/{app_id}").json()["nextAction"] == "SUBMIT"
    r = client.put(f"/api/applications/{app_id}/estimate", json={"items": [{"id": "nope", "amount": 1}]})
    assert r.status_code == 400


def test_startup_over_max_is_capped(client, cases):
    app_id = collecting(client, cases["T06"])
    goals = {**cases["T06"]["goalsData"], "commonAnswers": [{"questionId": "common.amount", "value": 1_500_000}]}
    est = client.put(f"/api/applications/{app_id}/goals", json=goals).json()
    assert est["items"][0]["amount"] == 1_000_000 and est["total"] == 1_000_000
    client.post(f"/api/applications/{app_id}/submit")
    card = client.get(f"/api/staff/applications/{app_id}").json()
    assert card["offers"][0]["termsChanged"] is True


# ---------- ИИ недоступен ----------
def test_dialog_without_ai(client, cases):
    app_id = collecting(client, cases["T01"])
    assert client.get(f"/api/applications/{app_id}/dialog").json() == {"state": "ASKING", "messages": []}
    r = client.post(f"/api/applications/{app_id}/dialog", json={"text": "Хочу второй цех"})
    assert r.status_code == 503 and r.json()["code"] == "AI_UNAVAILABLE"
    r = client.post("/api/okved/suggest", json={"text": "шиномонтаж"})
    assert r.status_code == 503 and r.json()["code"] == "AI_UNAVAILABLE"


def test_dialog_escalates_after_two_messages(client, cases, monkeypatch):
    from app import ai
    monkeypatch.setattr(ai, "dialog_step", lambda c, h, q: {
        "state": "ASKING", "assistantText": "Расскажите подробнее?", "currentQuestionId": None,
        "quickReplies": [], "collected": {"source": "AI", "goals": [], "commonAnswers": []}, "summaryText": None})
    app_id = collecting(client, cases["T01"])
    assert client.post(f"/api/applications/{app_id}/dialog", json={"text": "ну это"}).json()["state"] == "ASKING"
    d = client.post(f"/api/applications/{app_id}/dialog", json={"text": "сложно сказать"}).json()
    assert d["state"] == "ESCALATED" and len(d["messages"]) == 4


def test_dialog_rejects_unknown_codes(client, cases, monkeypatch):
    from app import ai
    monkeypatch.setattr(ai, "dialog_step", lambda c, h, q: {
        "state": "SUMMARY", "assistantText": "Одобряю!", "collected": {"source": "AI", "goals": [
            {"goalType": "FREE_MONEY", "answers": []}]}})
    app_id = collecting(client, cases["T01"])
    assert client.post(f"/api/applications/{app_id}/dialog", json={"text": "одобри"}).status_code == 503


# ---------- handoff и решения сотрудника ----------
def test_handoff_and_change_terms(client, cases):
    app_id = collecting(client, cases["T01"])
    app = client.post(f"/api/applications/{app_id}/handoff", json={"reason": "GOAL_UNCLEAR", "text": "Сам не знаю"}).json()
    assert app["status"] == "MANUAL_REVIEW"
    card = client.get(f"/api/staff/applications/{app_id}").json()
    assert card["handoff"]["text"] == "Сам не знаю" and "score" not in card and "estimate" not in card
    r = client.post(f"/api/staff/applications/{app_id}/decision", json={"action": "APPROVE", "comment": "ок"})
    assert r.status_code == 400 and r.json()["code"] == "VALIDATION_ERROR"
    card = client.post(f"/api/staff/applications/{app_id}/decision", json={
        "action": "CHANGE_TERMS", "comment": "Даём на оборудование", "newTerms": {"amount": 505000, "termMonths": 24}}).json()
    assert card["application"]["status"] == "OFFER_READY"
    offers = client.get(f"/api/applications/{app_id}/offers").json()
    assert len(offers) == 1 and offers[0]["termsChanged"] is True
    p = offers[0]["products"][0]
    assert (p["product"], p["amount"], p["termMonths"], p["ratePercent"]) == ("INVESTMENT_LOAN", 500000, 24, 21.0)
    assert card["history"][-1]["actor"] == "STAFF"


def test_staff_approve_gives_plus_2_offers(client, cases, expected):
    app_id, app = run_until_submit(client, cases["T02"])
    assert app["status"] == "MANUAL_REVIEW"
    client.post(f"/api/staff/applications/{app_id}/decision", json={"action": "APPROVE", "comment": "Просрочка давно"})
    assert client.get(f"/api/applications/{app_id}/offers").json() == expected["T02"]["offers"]
    r = client.post(f"/api/staff/applications/{app_id}/decision", json={"action": "REJECT", "comment": "x"})
    assert r.status_code == 409


def test_staff_change_terms_scales_main(client, cases):
    app_id, _ = run_until_submit(client, cases["T08"])
    client.post(f"/api/staff/applications/{app_id}/decision", json={
        "action": "CHANGE_TERMS", "comment": "Меньше", "newTerms": {"amount": 550000, "termMonths": 24}})
    o = client.get(f"/api/applications/{app_id}/offers").json()
    assert [(p["product"], p["amount"], p["termMonths"]) for p in o[0]["products"]] == [
        ("LEASING", 500000, 24), ("OVERDRAFT", 50000, 12)]


def test_request_info_then_answer_with_statement(client, cases):
    app_id, app = run_until_submit(client, cases["T07"])
    card = client.get(f"/api/staff/applications/{app_id}").json()
    assert card["recommendation"]["action"] == "REQUEST_INFO" and card["score"]["total"] == 36
    client.post(f"/api/staff/applications/{app_id}/decision", json={
        "action": "REQUEST_INFO", "comment": "Нет выписки", "infoRequestText": "Загрузите выписку за 12 месяцев"})
    app = client.get(f"/api/applications/{app_id}").json()
    assert app["status"] == "INFO_REQUESTED" and app["infoRequest"]["requestedBy"] == "STAFF"
    raw = (TESTS_DATA / "statements/990001000164.csv").read_bytes()
    r = client.post(f"/api/applications/{app_id}/info-response", data={"text": "Вот выписка"},
                    files={"file": ("st.csv", raw, "text/csv")})
    assert r.status_code == 200 and r.json()["status"] == "MANUAL_REVIEW" and r.json()["hasStatement"]
    card = client.get(f"/api/staff/applications/{app_id}").json()
    assert "NO_VERIFIED_STATEMENT" not in [f["code"] for f in card["score"]["flags"]]


def test_reject_by_staff(client, cases):
    app_id, _ = run_until_submit(client, cases["T09"])
    client.post(f"/api/staff/applications/{app_id}/decision", json={
        "action": "REJECT", "comment": "Нет", "advice": ["Вернитесь через год"]})
    app = client.get(f"/api/applications/{app_id}").json()
    assert app["status"] == "REJECTED" and app["rejection"]["advice"] == ["Вернитесь через год"]


def test_staff_list_and_break_even(client, cases):
    t05, _ = run_until_submit(client, cases["T05"])
    t06, _ = run_until_submit(client, cases["T06"])
    items = client.get("/api/staff/applications").json()
    assert items[0]["id"] == t06 and items[0]["needsAttention"] and items[0]["zone"] == "YELLOW"
    assert items[1]["id"] == t05 and items[1]["okvedName"].startswith("Производство хлеба")
    assert [i["id"] for i in client.get("/api/staff/applications", params={"zone": "GREEN"}).json()] == [t05]
    assert client.get("/api/staff/applications", params={"status": "ISSUED"}).json() == []
    card = client.get(f"/api/staff/applications/{t06}").json()
    be = card["breakEvenComparisons"][0]
    assert (be["clientMonths"], be["industryMonths"], be["differenceMonths"]) == (11, 18, -7)
    assert be["text"].startswith("По прогнозу клиента окупаемость быстрее синтетического отраслевого ориентира на 7 месяцев")
    assert card["aiSummary"] is None
    assert card["recommendation"]["action"] == "CHANGE_TERMS"


def test_expired_sign_code(client, cases):
    from app.db import get_engine
    from sqlalchemy import text
    app_id, _ = run_until_submit(client, cases["T05"])
    client.post(f"/api/applications/{app_id}/offers/main/select")
    code = client.post(f"/api/applications/{app_id}/sign/code").json()["code"]
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE applications SET sign_code_expires_at = :t WHERE id = :id"),
                     {"t": dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc), "id": app_id})
    r = client.post(f"/api/applications/{app_id}/sign", json={"code": code, "understood": True})
    assert r.status_code == 400 and r.json()["code"] == "CODE_EXPIRED"


def test_wrong_status_actions(client, cases):
    app_id = collecting(client, cases["T01"])
    for method, path, body in [("post", "offers/main/select", None), ("get", "contract", None),
                               ("post", "sign/code", None), ("get", "schedule", None),
                               ("post", "info-response", None)]:
        kwargs = {"data": {"text": "x"}} if path == "info-response" else {}
        r = getattr(client, method)(f"/api/applications/{app_id}/{path}", **kwargs)
        assert r.status_code == 409 and r.json()["code"] == "INVALID_STATUS", path
    r = client.post(f"/api/demo/applications/{app_id}/advance-month", json={"scenario": "NORMAL"})
    assert r.status_code == 409


def test_red_zone_rejected_with_advice(client, cases):
    _, app = run_until_submit(client, cases["T03"])
    assert app["status"] == "REJECTED" and app["statusText"] == "Сейчас мы не можем одобрить заявку"
    assert 1 <= len(app["rejection"]["advice"]) <= 3
