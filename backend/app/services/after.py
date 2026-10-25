"""После выдачи: график платежей, «перемотать месяц», уведомления — product-rules-v1.md, разделы 5 и 8.

График (Schedule) — сумма графиков всех продуктов по номеру месяца. Овердрафт и гарантия
в график не входят (проценты овердрафта зависят от использования, у гарантии нет платежей).
Внутри каждого платежа храним «_parts» — доли по продуктам: так можно пересчитать
график при «2 месяца только проценты».

Раннее предупреждение и рост лимита — обычные правила, без ИИ.
"""
from __future__ import annotations

import datetime as dt
import uuid
from fractions import Fraction

from ..clock import add_months, now
from ..config import get_settings
from ..errors import ApiError
from .estimate import round_down
from .offers import annuity_schedule, money
from .statement import avg_income

NO_SCHEDULE = ("OVERDRAFT", "BANK_GUARANTEE")


# ---------------------------------------------------------------- график

def _combine(per_product: dict[int, list[dict]], start: dt.date) -> list[dict]:
    length = max((len(rows) for rows in per_product.values()), default=0)
    payments = []
    for k in range(length):
        parts = [{"p": p, "principal": rows[k]["principal"], "interest": rows[k]["interest"]}
                 for p, rows in per_product.items() if k < len(rows)]
        payments.append(_payment(add_months(start, k), parts))
    return payments


def _payment(date: dt.date, parts: list[dict], status: str = "UPCOMING") -> dict:
    principal = sum(x["principal"] for x in parts)
    interest = sum(x["interest"] for x in parts)
    return {"date": date.isoformat(), "total": principal + interest, "principal": principal,
            "interest": interest, "status": status, "_parts": parts}


def build_schedule(offer: dict, first_date: dt.date) -> dict:
    products, per_product = [], {}
    for p in offer["products"]:
        if p["product"] in NO_SCHEDULE:
            continue
        idx = len(products)
        products.append({"product": p["product"], "ratePercent": p["ratePercent"]})
        per_product[idx] = annuity_schedule(p["amount"], p["ratePercent"], p["termMonths"],
                                            p.get("gracePeriodMonths", 0))
    overdraft = next((p["amount"] for p in offer["products"] if p["product"] == "OVERDRAFT"), 0)
    return {"payments": _combine(per_product, first_date), "_products": products, "_overdraftLimit": overdraft}


def public_schedule(schedule: dict) -> dict:
    payments = [{k: v for k, v in p.items() if not k.startswith("_")} for p in schedule["payments"]]
    upcoming = [p for p in payments if p["status"] == "UPCOMING"]
    out = {"payments": payments, "remainingDebt": sum(p["principal"] for p in upcoming)}
    if upcoming:
        out["nextPayment"] = upcoming[0]
    return out


def _postpone_next(schedule: dict) -> dict:
    """Ближайший платёж — в конец графика."""
    payments = [dict(p) for p in schedule["payments"]]
    nxt = next((p for p in payments if p["status"] == "UPCOMING"), None)
    if nxt is None:
        raise ApiError(409, "INVALID_STATUS", "Предстоящих платежей нет")
    nxt["status"] = "POSTPONED"
    last = dt.date.fromisoformat(payments[-1]["date"])
    payments.append(_payment(add_months(last, 1), nxt["_parts"]))
    return {**schedule, "payments": payments}


def _interest_only(schedule: dict, months: int) -> dict:
    """N месяцев только проценты, срок +N: пересчитываем каждый продукт по остатку долга."""
    payments = schedule["payments"]
    first_up = next((i for i, p in enumerate(payments) if p["status"] == "UPCOMING"), None)
    if first_up is None:
        raise ApiError(409, "INVALID_STATUS", "Предстоящих платежей нет")
    upcoming = [p for p in payments if p["status"] == "UPCOMING"]
    per_product = {}
    for idx, prod in enumerate(schedule["_products"]):
        parts = [x for p in upcoming for x in p["_parts"] if x["p"] == idx]
        rest = sum(x["principal"] for x in parts)
        if rest > 0:
            per_product[idx] = annuity_schedule(rest, prod["ratePercent"], len(parts) + months, months)
    kept = [p for p in payments if p["status"] != "UPCOMING"]
    start = dt.date.fromisoformat(payments[first_up]["date"])
    return {**schedule, "payments": kept + _combine(per_product, start)}


# ---------------------------------------------------------------- уведомления

def _notification(kind: str, text: str, options: list[str] | None = None, data: dict | None = None) -> dict:
    n = {"id": str(uuid.uuid4()), "kind": kind, "text": text, "createdAt": now().isoformat()}
    if options:
        n["options"] = options
    if data:
        n["_data"] = data
    return n


def public_notification(n: dict) -> dict:
    return {k: v for k, v in n.items() if not k.startswith("_")}


def advance_month(schedule: dict, after: dict, scenario: str, statement: dict | None) -> tuple[dict, dict, list[dict]]:
    """Перемотать месяц: платёж месяца отмечается PAID, по сценарию — уведомления.
    Возвращает (новый график, новые служебные данные, новые уведомления)."""
    s = get_settings()
    payments = [dict(p) for p in schedule["payments"]]
    nxt = next((p for p in payments if p["status"] == "UPCOMING"), None)
    if nxt:
        nxt["status"] = "PAID"   # ВРЕМЕННО (вопрос 11): и в месяц падения выручки платёж считаем внесённым
    schedule = {**schedule, "payments": payments}
    after = dict(after or {})
    new: list[dict] = []

    if scenario == "REVENUE_DROP":
        after["growthStreak"] = 0
        new.append(_notification("EARLY_WARNING", "Выручка ниже обычной. Можем помочь с платежом",
                                 ["POSTPONE_PAYMENT", "INTEREST_ONLY", "RESTRUCTURE", "DECLINE"]))
    elif scenario == "GROWTH":
        after["growthStreak"] = after.get("growthStreak", 0) + 1
        limit = schedule.get("_overdraftLimit", 0)
        if after["growthStreak"] >= s.GROWTH_MONTHS_IN_ROW and limit > 0 and statement:
            new_avg = avg_income(statement) * Fraction(str(s.GROWTH_REVENUE_SHARE))
            proposed = min(round_down(limit * Fraction(str(1 + s.LIMIT_INCREASE_SHARE))),
                           round_down(new_avg * Fraction(str(s.OVERDRAFT_SHARE))))
            after["growthStreak"] = 0
            if proposed > limit:
                new.append(_notification(
                    "LIMIT_INCREASE",
                    f"Ваш бизнес растёт — банк увеличил доступный лимит овердрафта до {money(proposed)} ₽",
                    ["ACCEPT_LIMIT", "DECLINE"], {"newLimit": proposed}))
    else:
        after["growthStreak"] = 0
    return schedule, after, new


def choose_option(schedule: dict, notification: dict, option: str) -> tuple[dict, dict, list[dict]]:
    """Клиент выбрал вариант в уведомлении. Возвращает (график, изменённое уведомление, новые уведомления)."""
    s = get_settings()
    if option not in (notification.get("options") or []):
        raise ApiError(409, "INVALID_STATUS", "Этот вариант недоступен для уведомления",
                       {"options": notification.get("options") or []})
    if notification.get("chosen"):
        raise ApiError(409, "INVALID_STATUS", "Вариант уже выбран", {"chosen": notification["chosen"]})
    extra: list[dict] = []
    if option == "POSTPONE_PAYMENT":
        schedule = _postpone_next(schedule)
    elif option == "INTEREST_ONLY":
        schedule = _interest_only(schedule, s.INTEREST_ONLY_MONTHS)
    elif option == "RESTRUCTURE":
        # Крупные изменения подтверждает сотрудник; API для этого в контракте нет (ВРЕМЕННО, вопрос 11)
        extra.append(_notification("INFO", f"Запрос на увеличение срока на {s.RESTRUCTURE_EXTRA_MONTHS} мес. "
                                           "передан специалисту банка. Пока график не меняется"))
    elif option == "ACCEPT_LIMIT":
        schedule = {**schedule, "_overdraftLimit": notification["_data"]["newLimit"]}
        extra.append(_notification("INFO", f"Лимит овердрафта увеличен до {money(notification['_data']['newLimit'])} ₽"))
    return schedule, {**notification, "chosen": option}, extra
