"""Кабинет сотрудника: рекомендация системы, карточка, список, решения.

Рекомендация — product-rules-v1.md, раздел 6 (по порядку строк таблицы).
Решение принимает сотрудник: APPROVE / CHANGE_TERMS / REQUEST_INFO / REJECT.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import ai, texts
from ..clock import now
from ..config import get_settings
from ..errors import ApiError
from ..models import Application
from ..statuses import change_status, require_status
from .applications import applicant_name, to_client
from .goals import answers_map
from .offers import money, staff_terms_offer
from .scoring import okved_for
from .. import refdata


# ---------------------------------------------------------------- рекомендация

def recommendation(app: Application, *, auto: bool, staff_offers: list | None, no_offer_reason: str | None,
                   missing: list[str] | None = None) -> dict:
    s = get_settings()
    if auto:
        return {"action": "APPROVE", "text": "Одобрено автоматически"}
    if app.handoff:
        return {"action": "REQUEST_INFO", "text": "Цель не определена — уточните у клиента, на что нужны деньги"}
    dd = app.decision_data or {}
    reasons = set(dd.get("manualReasons") or [])
    total = (app.score or {}).get("total", 0)

    if reasons & {"PASSPORT_HOLDER_MISMATCH", "PASSPORT_HOLDER_UNKNOWN"}:
        body = ((app.check_data or {}).get("raw", {}).get("PASSPORT") or {}).get("body") or {}
        fields = [texts.PASSPORT_FIELD_TEXT[f] for f in body.get("mismatchFields") or [] if f in texts.PASSPORT_FIELD_TEXT]
        if fields:
            return {"action": "REQUEST_INFO", "text": f"Уточните паспортные данные: не совпадает {', '.join(fields)}"}
        return {"action": "REQUEST_INFO", "text": "Уточните паспортные данные: запись о паспорте не подтверждена"}
    if reasons & {"NO_VERIFIED_STATEMENT", "STATEMENT_INCOMPLETE"}:
        return {"action": "REQUEST_INFO", "text": "Попросите выписку за 12 месяцев"}
    if missing and "OTHER" in missing:
        return {"action": "CHANGE_TERMS", "text": "Цель «Другое»: задайте сумму и срок сами"}
    if no_offer_reason:
        return {"action": "CHANGE_TERMS", "text": f"{no_offer_reason} — предложите меньшую сумму или другой срок"}
    if not app.has_business:
        amount = dd.get("requestedAmount") or 0
        if amount > s.STARTUP_AUTO_APPROVE_LIMIT or not dd.get("goodBki"):
            return {"action": "CHANGE_TERMS",
                    "text": f"Предложите до {money(s.STARTUP_AUTO_APPROVE_LIMIT)} ₽ или запросите поручителя/залог"}
    else:
        young = (dd.get("businessAgeMonths") or 0) < s.GREEN_MIN_BUSINESS_AGE_MONTHS
        smaller = any(o["kind"] == "SMALLER" for o in staff_offers or [])
        if young or (smaller and total < s.ZONE_GREEN_MIN):
            return {"action": "CHANGE_TERMS", "text": "Предложите вариант «Начать меньше»"}
    if total >= 60:
        why = "; ".join(texts.flag_text(r).lower() for r in sorted(reasons)) or "причину ручной проверки"
        return {"action": "APPROVE", "text": f"Риск приемлемый: проверьте — {why}"}
    return {"action": "CHANGE_TERMS", "text": "Предложите вариант «Начать меньше»"}


# ---------------------------------------------------------------- сравнение окупаемости

def _months_word(n: int) -> str:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return "месяц"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "месяца"
    return "месяцев"


def break_even_comparisons(app: Application) -> list[dict]:
    """Только информация для сотрудника (scoring-clarifications.md, раздел 6). Баллы НЕ меняет."""
    out = []
    if not app.goals:
        return out
    okved = okved_for(app.has_business, app.check_data or {}, app.goals)
    for idx, g in enumerate(app.goals["goals"]):
        qid = {"START_BUSINESS": "start.breakEven", "NEW_LOCATION": "location.breakEven"}.get(g["goalType"])
        if not qid:
            continue
        client = next((a["value"] for a in g["answers"] if a["questionId"] == qid), None)
        code = answers_map(app.goals).get("start.okved") if g["goalType"] == "START_BUSINESS" else okved
        ind = refdata.find_industry(code)
        industry = ind.get("typicalBreakEvenMonths") if ind else None
        if not (isinstance(client, int) and client > 0 and isinstance(industry, int) and industry > 0):
            continue
        diff = client - industry
        synthetic = ind["sourceType"] == "SYNTHETIC"
        src = "синтетического" if synthetic else "официального"
        if diff < 0:
            text = f"По прогнозу клиента окупаемость быстрее {src} отраслевого ориентира на {-diff} {_months_word(diff)}"
        elif diff == 0:
            text = f"Прогноз клиента совпадает с {'синтетическим' if synthetic else 'официальным'} отраслевым ориентиром"
        else:
            text = f"По прогнозу клиента окупаемость медленнее {src} отраслевого ориентира на {diff} {_months_word(diff)}"
        text += ". Прогноз клиента не подтверждён, на баллы не влияет"
        item = {"goalIndex": idx, "goalType": g["goalType"], "questionId": qid, "okvedCode": ind["okvedCode"],
                "clientMonths": client, "industryMonths": industry, "differenceMonths": diff,
                "sourceType": ind["sourceType"], "text": text}
        if ind.get("dataAsOf"):
            item["dataAsOf"] = ind["dataAsOf"]
        out.append(item)
    return out


# ---------------------------------------------------------------- карточка и список

def staff_offers(app: Application) -> list | None:
    return app.offers or (app.decision_data or {}).get("staffOffers")


def card(app: Application) -> dict:
    out = {
        "application": to_client(app),
        "passport": app.passport,
        "statement": app.statement,
        "questionnaire": app.questionnaire,
        "goals": app.goals,
        "estimate": app.estimate,
        "score": app.score,
        "breakEvenComparisons": break_even_comparisons(app),
        "handoff": app.handoff,
        "dialog": app.dialog,
        "recommendation": app.recommendation,
        "offers": staff_offers(app),
        "history": [{"at": h.at, "actor": h.actor, "fromStatus": h.from_status, "toStatus": h.to_status,
                     "comment": h.comment} for h in app.history],
    }
    try:
        # ИИ получает карточку без aiSummary; любой сбой → null (llm-contract.md, задача 5)
        summary = ai.staff_summary({k: v for k, v in out.items() if k != "history"} | {"history": [
            {**h, "at": h["at"].isoformat()} for h in out["history"]]})
        out["aiSummary"] = summary if isinstance(summary, str) and summary.strip() else None
    except Exception:
        out["aiSummary"] = None
    # Пустые поля не отдаём; handoff и aiSummary по контракту nullable — их оставляем как null
    return {k: v for k, v in out.items() if v is not None or k in ("handoff", "aiSummary")}


def list_items(db: Session, status: str | None, zone: str | None) -> list[dict]:
    q = select(Application)
    if status:
        q = q.where(Application.status == status)
    items = []
    for app in db.scalars(q).all():
        sc = app.score or {}
        if zone and sc.get("zone") != zone:
            continue
        dd = app.decision_data or {}
        okved = (app.business or {}).get("okved") or refdata.okved_by_code().get(answers_map(app.goals).get("start.okved"))
        requested = dd.get("requestedAmount") or (app.estimate or {}).get("total")  # ВРЕМЕННО (вопрос 16)
        item = {"id": app.id, "status": app.status, "applicantName": applicant_name(app),
                "okvedName": (okved or {}).get("name"), "requestedAmount": requested,
                "scoreTotal": sc.get("total"), "zone": sc.get("zone"),
                "needsAttention": app.status in ("MANUAL_REVIEW", "INFO_REQUESTED"), "createdAt": app.created_at}
        items.append({k: v for k, v in item.items() if v is not None})
    # спорные сверху, внутри — сначала новые
    items.sort(key=lambda x: x["createdAt"], reverse=True)
    items.sort(key=lambda x: not x["needsAttention"])
    return items


# ---------------------------------------------------------------- решение

def decide(db: Session, app: Application, body: dict) -> Application:
    require_status(app, "MANUAL_REVIEW", action="decision")
    action, comment = body["action"], body["comment"]
    okved = okved_for(app.has_business, app.check_data or {}, app.goals)
    offers_ready = (app.decision_data or {}).get("staffOffers")

    if action == "APPROVE":
        if app.handoff:
            raise ApiError(400, "VALIDATION_ERROR",
                           "Заявка передана клиентом без цели: задайте условия через CHANGE_TERMS (newTerms обязательны)")
        if not offers_ready:
            raise ApiError(400, "VALIDATION_ERROR",
                           "Автоматическое предложение не построено: задайте условия через CHANGE_TERMS")
        app.offers, app.offers_route = offers_ready, "STAFF"
        change_status(db, app, "OFFER_READY", "STAFF", comment)
    elif action == "CHANGE_TERMS":
        terms = body.get("newTerms") or {}
        if not isinstance(terms.get("amount"), int) or terms["amount"] < 1:
            raise ApiError(400, "VALIDATION_ERROR", "Для CHANGE_TERMS укажите newTerms.amount",
                           {"missingField": "newTerms.amount"})
        term = terms.get("termMonths")
        if term is not None and not 1 <= term <= 120:
            raise ApiError(400, "VALIDATION_ERROR", "Срок — от 1 до 120 месяцев", {"field": "newTerms.termMonths"})
        estimate = None if app.handoff else app.estimate
        app.offers = staff_terms_offer(estimate, app.goals, app.statement_internal, okved,
                                       terms["amount"], term, startup=not app.has_business)
        app.offers_route = "STAFF"
        change_status(db, app, "OFFER_READY", "STAFF", comment)
    elif action == "REQUEST_INFO":
        app.info_request = {"text": body.get("infoRequestText") or comment, "requestedBy": "STAFF"}
        change_status(db, app, "INFO_REQUESTED", "STAFF", comment)
    elif action == "REJECT":
        app.rejection = {"text": texts.REJECTION_TEXT,
                         "advice": (body.get("advice") or texts.REJECTION_ADVICE_SCORE)[:3]}
        change_status(db, app, "REJECTED", "STAFF", comment)
    db.commit()
    return app


def review_deadline() -> dt.datetime:
    return now() + dt.timedelta(days=get_settings().REVIEW_SLA_DAYS)
