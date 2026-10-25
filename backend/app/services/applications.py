"""Шаги 1–3: создание заявки, согласие, проверки. Плюс «вид заявки для клиента».

Порядок решения после проверок (scoring-model-v1.md, раздел 5 и 11; statuses.md):
1. hasBusiness=true и ИП не найден в ЕГРИП → 422 INN_NOT_FOUND / NOT_IP, назад в DRAFT;
2. какой-то сервис не ответил → остаёмся в CHECKING, 503 SERVICE_UNAVAILABLE, nextAction=RETRY_CHECKS;
3. есть STOP → REJECTED;
4. иначе → COLLECTING (MANUAL/MINUS учтутся позже, при submit).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import texts
from ..clock import evaluation_date, full_months, parse_date
from ..errors import ApiError
from ..models import Application, HistoryEntry
from ..statuses import OPEN_STATUSES, change_status, next_action, require_status, status_text
from .checks import evaluate_checks

# ---------------------------------------------------------------- ИНН

INN12_W1 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
INN12_W2 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)


def inn_is_valid(inn: str) -> bool:
    """ИНН физлица: 12 цифр, две последние — контрольные (сумма с весами по модулю 11, затем 10)."""
    if len(inn) != 12 or not inn.isdigit():
        return False
    d = [int(c) for c in inn]
    c11 = sum(w * x for w, x in zip(INN12_W1, d)) % 11 % 10
    c12 = sum(w * x for w, x in zip(INN12_W2, d)) % 11 % 10
    return d[10] == c11 and d[11] == c12


# ---------------------------------------------------------------- шаг 1

def find_open_application(db: Session, inn: str | None, series: str, number: str) -> Application | None:
    q = select(Application).where(Application.status.in_(OPEN_STATUSES))
    if inn:
        q = q.where(Application.inn == inn)
    else:
        q = q.where(Application.passport_series == series, Application.passport_number == number)
    return db.scalars(q.order_by(Application.created_at.desc())).first()


def create_application(db: Session, passport: dict, has_business: bool, inn: str | None) -> tuple[Application, bool]:
    """Возвращает (заявка, создана_ли_новая). Если есть открытая заявка — возвращаем её."""
    if inn is not None and not inn_is_valid(inn):
        raise ApiError(400, "INN_INVALID", "ИНН введён с ошибкой: не сходится контрольная сумма",
                       {"field": "inn"})
    if has_business and not inn:
        raise ApiError(400, "VALIDATION_ERROR", "Укажите ИНН — он нужен, если у вас уже есть ИП",
                       {"missingField": "inn"})
    existing = find_open_application(db, inn, passport["series"], passport["number"])
    if existing:
        return existing, False
    # Статус пока пустой: переход «ничего → DRAFT» пишем в историю общей функцией
    app = Application(has_business=has_business, inn=inn,
                      passport_series=passport["series"], passport_number=passport["number"],
                      passport=passport)
    db.add(app)
    change_status(db, app, "DRAFT", "CLIENT", "Заявка создана")
    db.commit()
    return app, True


def get_application(db: Session, app_id: str) -> Application:
    app = db.get(Application, app_id)
    if app is None:
        raise ApiError(404, "NOT_FOUND", "Заявка не найдена")
    return app


# ---------------------------------------------------------------- шаги 2–3

def give_consent(db: Session, app: Application) -> Application:
    require_status(app, "DRAFT", action="consent")
    if not app.inn:
        # statuses.md: без личного ИНН проверки не запускаем, статус DRAFT не меняется
        raise ApiError(422, "VALIDATION_ERROR",
                       "Для проверки нужен ваш ИНН. Создайте заявку заново и укажите ИНН",
                       {"missingField": "inn"})
    app.consent_at = dt.datetime.now(dt.timezone.utc)
    change_status(db, app, "CHECKING", "CLIENT", "Клиент дал согласие на проверку")
    return run_checks(db, app)


def retry_checks(db: Session, app: Application) -> Application:
    require_status(app, "CHECKING", action="checks")
    if not app.consent_at:
        raise ApiError(409, "CONSENT_REQUIRED", "Сначала нужно согласие на проверку")
    return run_checks(db, app)


def _business_info(egrip_body: dict, eval_date: dt.date) -> dict:
    reg = parse_date(egrip_body.get("registrationDate"))
    info = {"okved": egrip_body.get("okvedMain"), "registrationDate": egrip_body.get("registrationDate"),
            "region": egrip_body.get("region")}
    if reg:
        info["ageMonths"] = full_months(reg, eval_date)
    return {k: v for k, v in info.items() if v is not None}


def run_checks(db: Session, app: Application) -> Application:
    eval_date = evaluation_date()
    result = evaluate_checks(app.passport, app.inn, app.has_business, eval_date)
    app.checks = result["checks"]
    app.check_data = result
    app.evaluation_date = eval_date.isoformat()

    egrip = result["raw"]["FNS_EGRIP"]
    if app.has_business and egrip["status"] == 200 and isinstance(egrip["body"], dict):
        app.business = _business_info(egrip["body"], eval_date)
    else:
        app.business = None

    # 1. ИП не найден при hasBusiness=true → назад в DRAFT, 422
    if result["innProblem"]:
        code = result["innProblem"]
        change_status(db, app, "DRAFT", "SYSTEM", f"ЕГРИП: {code}")
        db.commit()
        msg = ("ИП с таким ИНН не найден в реестре. Проверьте ИНН и создайте заявку заново"
               if code == "INN_NOT_FOUND" else
               "Этот ИНН не принадлежит действующему ИП. Проверьте ИНН и создайте заявку заново")
        raise ApiError(422, code, msg, {"applicationId": app.id})

    # 2. Сервис не ответил → остаёмся в CHECKING, сохраняем, 503
    if result["errors"]:
        app.history.append(HistoryEntry(actor="SYSTEM", from_status="CHECKING", to_status="CHECKING",
                                        comment="Не ответили: " + ", ".join(result["errors"])))
        db.commit()
        raise ApiError(503, "SERVICE_UNAVAILABLE",
                       "Один из сервисов проверки временно недоступен. Заявка сохранена — повторите проверку чуть позже",
                       {"applicationId": app.id, "sources": result["errors"]})

    # 3. STOP → отказ сразу
    if result["stops"]:
        app.rejection = {"text": texts.REJECTION_TEXT, "advice": texts.REJECTION_ADVICE_STOP}
        change_status(db, app, "REJECTED", "SYSTEM", "Стоп-фактор: " + ", ".join(result["stops"]))
        db.commit()
        return app

    # 4. Всё получено, стоп-факторов нет
    comment = "Проверки пройдены"
    if result["manuals"]:
        comment += "; на ручную проверку: " + ", ".join(result["manuals"])
    change_status(db, app, "COLLECTING", "SYSTEM", comment)
    db.commit()
    return app


# ---------------------------------------------------------------- вид для клиента

def applicant_name(app: Application) -> str:
    p = app.passport or {}
    return " ".join(x for x in (p.get("lastName"), p.get("firstName")) if x)


def to_client(app: Application) -> dict:
    """Application из openapi.yaml. Никаких баллов, зон и формул."""
    out = {
        "id": app.id,
        "status": app.status,
        "statusText": status_text(app),
        "nextAction": next_action(app),
        "hasBusiness": app.has_business,
        "applicantName": applicant_name(app),
        "inn": app.inn,
        "business": app.business,
        "checks": app.checks,
        "hasStatement": app.statement is not None,
        "hasQuestionnaire": app.questionnaire is not None,
        "goals": [g["goalType"] for g in (app.goals or {}).get("goals", [])] if app.goals else None,
        "reviewDeadline": app.review_deadline if app.status == "MANUAL_REVIEW" else None,
        "infoRequest": app.info_request if app.status == "INFO_REQUESTED" else None,
        "rejection": app.rejection if app.status == "REJECTED" else None,
        "createdAt": app.created_at,
        "updatedAt": app.updated_at,
    }
    return {k: v for k, v in out.items() if v is not None}
