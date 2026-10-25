"""Статусы заявки и переходы — строго по contract/statuses.md.

Главная функция — change_status(): она проверяет, что переход разрешён, меняет статус
и пишет строку в историю. Любой другой переход → 409 INVALID_STATUS.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .errors import ApiError
from .models import Application, HistoryEntry

STATUS_TEXT = {
    "DRAFT": "Черновик заявки",
    "CHECKING": "Проверяем данные",
    "COLLECTING": "Заполните заявку",
    "MANUAL_REVIEW": "Заявка у специалиста. Ответ до {date}",
    "INFO_REQUESTED": "Нужно уточнение: {what}",
    "OFFER_READY": "Предложение готово",
    "SIGNING": "Подпишите договор",
    "ISSUED": "Финансирование выдано",
    "REJECTED": "Сейчас мы не можем одобрить заявку",
}

# Разрешённые переходы (statuses.md → «Переходы»). None → DRAFT — создание заявки.
TRANSITIONS: set[tuple[str | None, str]] = {
    (None, "DRAFT"),
    ("DRAFT", "CHECKING"),
    ("CHECKING", "COLLECTING"),
    ("CHECKING", "REJECTED"),
    ("CHECKING", "DRAFT"),          # hasBusiness=true, ИП не найден
    ("COLLECTING", "OFFER_READY"),
    ("COLLECTING", "MANUAL_REVIEW"),  # жёлтая зона или handoff
    ("COLLECTING", "INFO_REQUESTED"),
    ("COLLECTING", "REJECTED"),
    ("MANUAL_REVIEW", "OFFER_READY"),
    ("MANUAL_REVIEW", "INFO_REQUESTED"),
    ("MANUAL_REVIEW", "REJECTED"),
    ("INFO_REQUESTED", "MANUAL_REVIEW"),
    ("OFFER_READY", "SIGNING"),
    ("SIGNING", "ISSUED"),
}

OPEN_STATUSES = {"DRAFT", "CHECKING", "COLLECTING", "MANUAL_REVIEW", "INFO_REQUESTED", "OFFER_READY", "SIGNING"}


def change_status(db: Session, app: Application, to: str, actor: str, comment: str | None = None) -> None:
    frm = app.status
    if (frm, to) not in TRANSITIONS:
        raise ApiError(409, "INVALID_STATUS", "Это действие сейчас недоступно",
                       {"status": frm, "requestedStatus": to})
    app.status = to
    app.history.append(HistoryEntry(actor=actor, from_status=frm, to_status=to, comment=comment))
    db.flush()


def require_status(app: Application, *allowed: str, action: str = "") -> None:
    """Проверка «действие доступно только в этих статусах», иначе 409."""
    if app.status not in allowed:
        raise ApiError(409, "INVALID_STATUS", "Это действие сейчас недоступно",
                       {"status": app.status, "action": action, "allowedStatuses": list(allowed)})


def status_text(app: Application) -> str:
    tpl = STATUS_TEXT[app.status]
    if app.status == "MANUAL_REVIEW":
        date = app.review_deadline.strftime("%d.%m.%Y") if app.review_deadline else "—"
        return tpl.format(date=date)
    if app.status == "INFO_REQUESTED":
        what = (app.info_request or {}).get("text") or "уточните данные"
        return tpl.format(what=what)
    return tpl


def next_action(app: Application) -> str:
    s = app.status
    if s == "DRAFT":
        return "GIVE_CONSENT"
    if s == "CHECKING":
        has_error = any(c.get("state") == "ERROR" for c in (app.checks or []))
        return "RETRY_CHECKS" if has_error else "WAIT"
    if s == "COLLECTING":
        # «по тому, чего не хватает». Стартапу выписка не нужна.
        if app.has_business and not (app.statement or app.questionnaire):
            return "UPLOAD_STATEMENT"
        if not app.goals:
            return "SET_GOALS"
        if not app.estimate_reviewed:   # ВРЕМЕННО (вопрос 4)
            return "REVIEW_ESTIMATE"
        return "SUBMIT"
    return {
        "MANUAL_REVIEW": "WAIT",
        "INFO_REQUESTED": "ANSWER_INFO_REQUEST",
        "OFFER_READY": "CHOOSE_OFFER",
        "SIGNING": "SIGN",
        "ISSUED": "NONE",
        "REJECTED": "NONE",
    }[s]
