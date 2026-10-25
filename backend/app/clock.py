"""Время и дата оценки.

Дата оценки (evaluationDate) — «сегодня» для всех правил: окно выписки, возраст ИП,
свежесть отчёта БКИ, дата выдачи и первого платежа. Берётся из EVALUATION_DATE,
чтобы демо-данные не «устаревали»; если переменной нет — сегодняшняя дата.

Метки времени (createdAt, история) — настоящее время в UTC.
"""
from __future__ import annotations

import calendar
import datetime as dt

from .config import get_settings


def evaluation_date() -> dt.date:
    raw = get_settings().EVALUATION_DATE
    return dt.date.fromisoformat(raw) if raw else dt.date.today()


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_date(value) -> dt.date | None:
    """Строка YYYY-MM-DD → дата. Всё остальное (None, неверный формат) → None."""
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def add_months(d: dt.date, n: int) -> dt.date:
    """Прибавить n календарных месяцев. 31 января + 1 месяц = 28/29 февраля."""
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def full_months(start: dt.date, end: dt.date) -> int:
    """Число полных календарных месяцев: start + N месяцев ≤ end (модель баллов, 3.2)."""
    if end < start:
        return 0
    n = (end.year - start.year) * 12 + (end.month - start.month)
    while n > 0 and add_months(start, n) > end:
        n -= 1
    return n
