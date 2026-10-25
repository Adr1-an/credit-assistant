"""Таблицы базы данных.

applications — одна строка на заявку. Простые поля (статус, ИНН) — обычные колонки,
сложные структуры (результаты проверок, выписка, смета, баллы…) — колонки JSON.
history — каждый переход статуса: кто, когда, откуда, куда, комментарий (statuses.md → История).

Важно про JSON-колонки: SQLAlchemy не замечает изменений ВНУТРИ словаря.
Поэтому всегда присваиваем новое значение целиком: app.checks = new_list.
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .clock import now
from .db import Base

# В PostgreSQL — JSONB, в других базах (например SQLite в быстрых тестах) — обычный JSON
JsonType = JSON().with_variant(JSONB(), "postgresql")


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[str] = mapped_column(String(20), index=True)
    has_business: Mapped[bool] = mapped_column(Boolean)
    inn: Mapped[str | None] = mapped_column(String(12), index=True, nullable=True)
    passport_series: Mapped[str] = mapped_column(String(4))
    passport_number: Mapped[str] = mapped_column(String(6))
    passport: Mapped[dict] = mapped_column(JsonType)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    consent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Дата оценки, на которую посчитаны проверки и баллы (сохраняем вместе с результатом)
    evaluation_date: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Шаг 3: проверки. checks — то, что видит клиент (CheckResult[]);
    # check_data — внутреннее: сырые ответы заглушек и причины MANUAL/STOP для расчёта баллов
    checks: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    check_data: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    business: Mapped[dict | None] = mapped_column(JsonType, nullable=True)

    # Шаг 4: выписка или анкета
    statement: Mapped[dict | None] = mapped_column(JsonType, nullable=True)        # StatementSummary
    statement_internal: Mapped[dict | None] = mapped_column(JsonType, nullable=True)  # доли OTHER_IN и т.п.
    questionnaire: Mapped[dict | None] = mapped_column(JsonType, nullable=True)

    # Шаги 5–7: цели, диалог, смета
    goals: Mapped[dict | None] = mapped_column(JsonType, nullable=True)            # GoalsData
    dialog: Mapped[dict | None] = mapped_column(JsonType, nullable=True)           # DialogState
    estimate: Mapped[dict | None] = mapped_column(JsonType, nullable=True)         # Estimate
    estimate_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    handoff: Mapped[dict | None] = mapped_column(JsonType, nullable=True)

    # Шаг 8: решение
    score: Mapped[dict | None] = mapped_column(JsonType, nullable=True)            # Score (только сотруднику)
    decision_data: Mapped[dict | None] = mapped_column(JsonType, nullable=True)    # причины MANUAL, маршрут
    recommendation: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    review_deadline: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    info_request: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    rejection: Mapped[dict | None] = mapped_column(JsonType, nullable=True)

    # Шаги 9–10: предложения, договор, подпись
    offers: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    offers_route: Mapped[str | None] = mapped_column(String(10), nullable=True)    # AUTO / STAFF
    selected_offer_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    contract: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    sign_code: Mapped[str | None] = mapped_column(String(6), nullable=True)
    sign_code_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    issued_at: Mapped[str | None] = mapped_column(String(10), nullable=True)       # дата выдачи YYYY-MM-DD

    # После выдачи
    schedule: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    notifications: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    after_data: Mapped[dict | None] = mapped_column(JsonType, nullable=True)       # счётчики месяцев роста и т.п.

    history: Mapped[list[HistoryEntry]] = relationship(
        back_populates="application", order_by="HistoryEntry.id", cascade="all, delete-orphan")


class HistoryEntry(Base):
    __tablename__ = "history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), index=True)
    at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    actor: Mapped[str] = mapped_column(String(10))          # CLIENT / SYSTEM / STAFF
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    application: Mapped[Application] = relationship(back_populates="history")
