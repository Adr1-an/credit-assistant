"""Воронка клиента после проверок: шаги 4–10 и «после выдачи».

Каждая функция: проверить статус → сделать дело → (если надо) сменить статус → сохранить.
"""
from __future__ import annotations

import datetime as dt
import secrets

from sqlalchemy.orm import Session

from .. import ai, refdata, texts
from ..clock import evaluation_date, now
from ..config import get_settings
from ..errors import ApiError
from ..models import Application, HistoryEntry
from ..statuses import change_status, require_status
from . import after, scoring, staff
from .contract import render_contract
from .estimate import apply_client_edits, build_estimate
from .goals import validate_goals, validate_questionnaire
from .offers import build_offers, preview_start_smaller
from .statement import parse_statement


def _eval_date(app: Application) -> dt.date:
    return dt.date.fromisoformat(app.evaluation_date) if app.evaluation_date else evaluation_date()


# ---------------------------------------------------------------- шаг 4: выписка и анкета

def upload_statement(db: Session, app: Application, raw: bytes) -> dict:
    require_status(app, "COLLECTING", action="statement")
    summary, internal = parse_statement(raw, _eval_date(app))
    app.statement, app.statement_internal = summary, internal
    _rebuild_estimate_if_any(app)
    db.commit()
    return summary


def save_questionnaire(db: Session, app: Application, data: dict) -> Application:
    require_status(app, "COLLECTING", action="questionnaire")
    app.questionnaire = validate_questionnaire(data)
    db.commit()
    return app


# ---------------------------------------------------------------- шаги 5–7: цели и смета

def _rebuild_estimate_if_any(app: Application) -> None:
    """Выписка поменялась после целей — строки «как в первой точке» пересчитываем."""
    if app.goals:
        _build_estimate(app)


def _build_estimate(app: Application) -> dict:
    est, missing = build_estimate(app.goals, app.statement_internal, app.has_business)
    est["startSmallerSuggested"] = preview_start_smaller(est, app.goals, app.statement_internal)
    est["_missing"] = missing
    app.estimate = est
    app.estimate_reviewed = False
    return est


def save_goals(db: Session, app: Application, data: dict) -> dict:
    require_status(app, "COLLECTING", action="goals")
    app.goals = validate_goals(data)
    est = _build_estimate(app)
    db.commit()
    return est


def get_estimate(app: Application) -> dict:
    if not app.estimate:
        raise ApiError(404, "NOT_FOUND", "Смета ещё не построена: сначала укажите цели")
    return app.estimate


def update_estimate(db: Session, app: Application, edits: list[dict]) -> dict:
    require_status(app, "COLLECTING", action="estimate")
    est = get_estimate(app)
    new = apply_client_edits(est, edits, app.statement_internal)
    new["startSmallerSuggested"] = preview_start_smaller(new, app.goals, app.statement_internal)
    new["_missing"] = est.get("_missing", [])
    app.estimate = new
    app.estimate_reviewed = True
    db.commit()
    return new


# ---------------------------------------------------------------- ИИ-диалог и handoff

def get_dialog(app: Application) -> dict:
    return app.dialog or {"state": "ASKING", "messages": []}


def _dialog_context(app: Application) -> dict:
    ctx = {"hasBusiness": app.has_business}
    if app.business:
        ctx["okved"] = app.business.get("okved")
        ctx["businessAgeMonths"] = app.business.get("ageMonths")
    if app.statement:
        ctx["avgMonthlyIncome"] = app.statement["avgMonthlyIncome"]
        ctx["avgMonthlyExpense"] = app.statement["avgMonthlyExpense"]
        ctx["expenseByCategory"] = app.statement.get("expenseByCategory", {})
    return ctx


def _check_ai_dialog(result) -> dict:
    """Ответ ИИ проверяем по схеме. Не прошёл — считаем, что ИИ недоступен (llm-contract.md, правило 2)."""
    if not isinstance(result, dict) or result.get("state") not in ("ASKING", "SUMMARY", "ESCALATED"):
        raise ai.AIUnavailable("bad state")
    if not isinstance(result.get("assistantText"), str) or not result["assistantText"].strip():
        raise ai.AIUnavailable("no text")
    qid = result.get("currentQuestionId")
    if qid is not None and qid not in refdata.questions_by_id():
        raise ai.AIUnavailable("unknown questionId")
    replies = result.get("quickReplies") or []
    if not isinstance(replies, list) or not all(isinstance(x, str) for x in replies):
        raise ai.AIUnavailable("bad quickReplies")
    collected = result.get("collected") or {"source": "AI", "goals": [], "commonAnswers": []}
    goals = collected.get("goals") or []
    try:
        if goals:
            collected = validate_goals({**collected, "source": "AI"})
        else:
            collected = {"source": "AI", "goals": [], "commonAnswers": []}
    except ApiError:
        # Неполные ответы допустимы, пока ИИ спрашивает; чужие коды — нет
        known = {g["goalType"] for g in refdata.question_sets()["goals"]}
        if any(g.get("goalType") not in known for g in goals):
            raise ai.AIUnavailable("unknown goalType")
        collected = {"source": "AI", "goals": [{"goalType": g["goalType"], "answers": [
            a for a in g.get("answers") or [] if a.get("questionId") in refdata.questions_by_id()]} for g in goals],
            "commonAnswers": [a for a in collected.get("commonAnswers") or []
                              if a.get("questionId") in refdata.questions_by_id()]}
    return {"state": result["state"], "assistantText": result["assistantText"], "currentQuestionId": qid,
            "quickReplies": replies, "collected": collected, "summaryText": result.get("summaryText")}


def send_dialog_message(db: Session, app: Application, text: str) -> dict:
    require_status(app, "COLLECTING", action="dialog")
    dialog = get_dialog(app)
    messages = list(dialog["messages"]) + [{"role": "CLIENT", "text": text, "at": now().isoformat()}]
    history = [{"role": m["role"], "text": m["text"]} for m in messages]
    try:
        result = _check_ai_dialog(ai.dialog_step(_dialog_context(app), history, refdata.question_sets()))
    except ai.AIUnavailable:
        raise ApiError(503, "AI_UNAVAILABLE", "Помощник сейчас недоступен — заполните, пожалуйста, форму")
    except Exception:
        raise ApiError(503, "AI_UNAVAILABLE", "Помощник сейчас недоступен — заполните, пожалуйста, форму")
    state = result["state"]
    client_count = sum(1 for m in messages if m["role"] == "CLIENT")
    # Подстраховка сервера: после 2 сообщений клиента без цели → ESCALATED, даже если ИИ так не решил
    if not result["collected"]["goals"] and client_count >= get_settings().DIALOG_MAX_ATTEMPTS:
        state = "ESCALATED"
    messages.append({"role": "ASSISTANT", "text": result["assistantText"], "at": now().isoformat()})
    new = {"state": state, "messages": messages, "collected": result["collected"]}
    for k in ("currentQuestionId", "summaryText"):
        if result.get(k):
            new[k] = result[k]
    if result["quickReplies"]:
        new["quickReplies"] = result["quickReplies"]
    app.dialog = new
    db.commit()
    return new


def suggest_okved(text: str) -> list[dict]:
    try:
        result = ai.suggest_okved(text, refdata.okved_catalog())
    except Exception:
        raise ApiError(503, "AI_UNAVAILABLE", "Подсказка сейчас недоступна — найдите код через поиск")
    catalog = refdata.okved_by_code()
    out, seen = [], set()
    for x in result if isinstance(result, list) else []:
        code = x.get("code") if isinstance(x, dict) else None
        if code in catalog and code not in seen:   # только коды из справочника
            seen.add(code)
            out.append(catalog[code])
    return out[:3]


def handoff(db: Session, app: Application, reason: str, text: str | None) -> Application:
    require_status(app, "COLLECTING", action="handoff")
    app.handoff = {"reason": reason, "at": now().isoformat(), **({"text": text} if text else {})}
    app.estimate = None   # «без сметы и баллов»
    app.score = None
    app.recommendation = staff.recommendation(app, auto=False, staff_offers=None, no_offer_reason=None)
    app.review_deadline = staff.review_deadline()
    change_status(db, app, "MANUAL_REVIEW", "CLIENT", reason + (f": {text}" if text else ""))
    db.commit()
    return app


# ---------------------------------------------------------------- шаг 8: отправка и решение

def _score(app: Application) -> dict:
    calc = scoring.calculate(app.has_business, app.check_data, app.statement_internal, app.goals, _eval_date(app))
    app.score = calc["score"]
    app.decision_data = {k: v for k, v in calc.items() if k != "score"}
    return calc


def _set_estimate_flag(app: Application, flag: bool) -> None:
    if app.estimate:
        app.estimate = {**app.estimate, "startSmallerSuggested": flag}


def _prepare_staff_view(app: Application, missing: list[str]) -> None:
    """Для сотрудника заранее строим предложения (как будто он нажмёт APPROVE: ставка +2) и рекомендацию."""
    calc_okved = (app.decision_data or {}).get("okved")
    offers, flag, why = (None, False, None)
    if app.estimate and not missing:
        offers, flag, why = build_offers(app.estimate, app.goals, app.statement_internal,
                                         app.score["total"], "STAFF", calc_okved)
        _set_estimate_flag(app, flag)
    app.decision_data = {**app.decision_data, "staffOffers": offers, "noOfferReason": why}
    app.recommendation = staff.recommendation(app, auto=False, staff_offers=offers, no_offer_reason=why,
                                              missing=missing)


def submit(db: Session, app: Application) -> Application:
    require_status(app, "COLLECTING", action="submit")
    missing_steps = []
    if app.has_business and not (app.statement or app.questionnaire):
        missing_steps.append("statement")  # ВРЕМЕННО (вопрос 5)
    if not app.goals:
        missing_steps.append("goals")
    if missing_steps:
        raise ApiError(409, "INVALID_STATUS", "Заявку пока нельзя отправить: не все шаги заполнены",
                       {"missing": missing_steps})

    calc = _score(app)
    zone, total = calc["score"]["zone"], calc["score"]["total"]
    missing = (app.estimate or {}).get("_missing", [])
    note = f"Баллы {total}, зона {zone}"
    if calc["manualReasons"]:
        note += "; MANUAL: " + ", ".join(calc["manualReasons"])

    if zone == "RED":
        app.rejection = {"text": texts.REJECTION_TEXT, "advice": texts.REJECTION_ADVICE_SCORE}
        change_status(db, app, "REJECTED", "SYSTEM", note)
    elif "OTHER" in missing:
        _prepare_staff_view(app, missing)
        app.review_deadline = staff.review_deadline()
        change_status(db, app, "MANUAL_REVIEW", "SYSTEM", note + "; цель «Другое»")
    elif missing:
        what = ", ".join(texts.MISSING_TEXT.get(m, m) for m in missing)
        app.info_request = {"text": f"Укажите {what}", "requestedBy": "SYSTEM"}
        _prepare_staff_view(app, missing)
        change_status(db, app, "INFO_REQUESTED", "SYSTEM", note + f"; не хватает: {', '.join(missing)}")
    elif zone == "GREEN":
        offers, flag, why = build_offers(app.estimate, app.goals, app.statement_internal, total, "AUTO",
                                         calc["okved"])
        _set_estimate_flag(app, flag)
        if offers:
            app.offers, app.offers_route = offers, "AUTO"
            app.recommendation = staff.recommendation(app, auto=True, staff_offers=None, no_offer_reason=None)
            change_status(db, app, "OFFER_READY", "SYSTEM", note)
        else:
            _prepare_staff_view(app, missing)
            app.review_deadline = staff.review_deadline()
            change_status(db, app, "MANUAL_REVIEW", "SYSTEM", note + f"; {why}")
    else:
        _prepare_staff_view(app, missing)
        app.review_deadline = staff.review_deadline()
        change_status(db, app, "MANUAL_REVIEW", "SYSTEM", note)
    db.commit()
    return app


def answer_info_request(db: Session, app: Application, text: str, raw_file: bytes | None) -> Application:
    require_status(app, "INFO_REQUESTED", action="info-response")
    if not text or not text.strip():
        raise ApiError(400, "VALIDATION_ERROR", "Напишите ответ", {"missingField": "text"})
    if raw_file:
        app.statement, app.statement_internal = parse_statement(raw_file, _eval_date(app))
    app.info_request = {**(app.info_request or {}), "response": text.strip(),
                        **({"responseHasFile": True} if raw_file else {})}
    # Новая выписка → для сотрудника пересчитываем баллы и предложения (ВРЕМЕННО, вопрос 12)
    if raw_file and app.goals and not app.handoff:
        _score(app)
        _prepare_staff_view(app, (app.estimate or {}).get("_missing", []))
    app.review_deadline = staff.review_deadline()
    change_status(db, app, "MANUAL_REVIEW", "CLIENT", text.strip())
    db.commit()
    return app


# ---------------------------------------------------------------- шаги 9–10: предложение, договор, подпись

def get_offers(app: Application) -> list[dict]:
    require_status(app, "OFFER_READY", "SIGNING", "ISSUED", action="offers")
    return app.offers or []


def select_offer(db: Session, app: Application, offer_id: str) -> Application:
    require_status(app, "OFFER_READY", action="select")
    offer = next((o for o in app.offers or [] if o["id"] == offer_id), None)
    if offer is None:
        raise ApiError(404, "NOT_FOUND", "Такого предложения нет")
    app.selected_offer_id = offer_id
    app.contract = render_contract(app.id, offer, app.estimate, app.goals, evaluation_date())
    change_status(db, app, "SIGNING", "CLIENT", f"Выбрано предложение {offer['kind']}")
    db.commit()
    return app


def get_contract(app: Application) -> dict:
    require_status(app, "SIGNING", "ISSUED", action="contract")
    return app.contract


def ask_contract(app: Application, question_id: str | None, text: str | None) -> dict:
    require_status(app, "SIGNING", "ISSUED", action="contract/ask")
    disclaimer = "Пояснение справочное и не заменяет юридическую консультацию."
    if question_id:
        answer = app.contract["faqAnswers"].get(question_id)
        if answer is None:
            raise ApiError(400, "VALIDATION_ERROR", "Такого готового вопроса нет", {"questionId": question_id})
        return {"answer": answer, "source": "FAQ", "disclaimer": disclaimer}
    if not text or not text.strip():
        raise ApiError(400, "VALIDATION_ERROR", "Укажите questionId или текст вопроса")
    public = {k: v for k, v in app.contract.items() if k not in ("faqAnswers", "firstPaymentDate")}
    try:
        answer = ai.explain_contract(public, text.strip())
        if not isinstance(answer, str) or not answer.strip():
            raise ai.AIUnavailable("empty")
    except Exception:
        raise ApiError(503, "AI_UNAVAILABLE", "Сейчас могу ответить только на готовые вопросы")
    return {"answer": answer.strip(), "source": "AI", "disclaimer": disclaimer}


def request_sign_code(db: Session, app: Application) -> dict:
    require_status(app, "SIGNING", action="sign/code")
    app.sign_code = f"{secrets.randbelow(10 ** 6):06d}"
    app.sign_code_expires_at = now() + dt.timedelta(minutes=get_settings().SIGN_CODE_TTL_MINUTES)
    db.commit()
    return {"code": app.sign_code, "expiresAt": app.sign_code_expires_at}


def sign(db: Session, app: Application, code: str) -> Application:
    require_status(app, "SIGNING", action="sign")
    if not app.sign_code or not secrets.compare_digest(code, app.sign_code):
        raise ApiError(400, "CODE_INVALID", "Неверный код. Проверьте цифры или запросите новый код")
    expires = app.sign_code_expires_at
    if expires.tzinfo is None:  # SQLite хранит без часового пояса
        expires = expires.replace(tzinfo=dt.timezone.utc)
    if now() > expires:
        raise ApiError(400, "CODE_EXPIRED", "Код устарел. Запросите новый код")
    offer = next(o for o in app.offers if o["id"] == app.selected_offer_id)
    app.sign_code = None
    app.issued_at = evaluation_date().isoformat()   # ВРЕМЕННО (вопрос 17)
    app.schedule = after.build_schedule(offer, dt.date.fromisoformat(app.contract["firstPaymentDate"]))
    app.notifications = []
    change_status(db, app, "ISSUED", "CLIENT", "Договор подписан кодом")
    db.commit()
    return app


# ---------------------------------------------------------------- после выдачи

def get_schedule(app: Application) -> dict:
    require_status(app, "ISSUED", action="schedule")
    return after.public_schedule(app.schedule)


def get_notifications(app: Application) -> list[dict]:
    return [after.public_notification(n) for n in app.notifications or []]


def advance_month(db: Session, app: Application, scenario: str) -> list[dict]:
    require_status(app, "ISSUED", action="advance-month")
    schedule, data, new = after.advance_month(app.schedule, app.after_data, scenario, app.statement_internal)
    app.schedule, app.after_data = schedule, data
    app.notifications = (app.notifications or []) + new
    db.commit()
    return [after.public_notification(n) for n in new]


def choose_notification_option(db: Session, app: Application, notification_id: str, option: str) -> dict:
    require_status(app, "ISSUED", action="notifications/choose")
    notes = list(app.notifications or [])
    idx = next((i for i, n in enumerate(notes) if n["id"] == notification_id), None)
    if idx is None:
        raise ApiError(404, "NOT_FOUND", "Уведомление не найдено")
    schedule, changed, extra = after.choose_option(app.schedule, notes[idx], option)
    notes[idx] = changed
    app.schedule, app.notifications = schedule, notes + extra
    app.history.append(HistoryEntry(actor="CLIENT", from_status="ISSUED", to_status="ISSUED",
                                    comment=f"Уведомление {changed['kind']}: выбран {option}"))
    db.commit()
    return after.public_schedule(schedule)
