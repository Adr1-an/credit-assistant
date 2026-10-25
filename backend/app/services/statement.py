"""Шаг 4. Разбор выписки (CSV) — строго по contract/mocks-contract.md → «Формат выписки».

Что делает parse_statement():
1. Читает CSV: UTF-8 (BOM допускается), разделитель «;», ровно 6 колонок в любом порядке.
   Любая ошибка (дата, сумма, направление, колонки) → 400 STATEMENT_UNREADABLE, без частичного расчёта.
2. Берёт окно: 12 последних ЗАВЕРШЁННЫХ календарных месяцев до месяца даты оценки.
   Для 24.10.2026 это 2025-10 … 2026-09. Строки вне окна в расчёт не идут.
3. Поступления (IN) раскладывает по правилам: OTHER_IN / ACQUIRING / CUSTOMER (по приоритету).
   Выручка месяца = только CUSTOMER + ACQUIRING. ИИ здесь не участвует.
4. Списания (OUT) раскладывает по категориям (product-rules-v1.md, 3.1): по началу слова.
5. Месяц без единой строки — «пропущен»: его нет в monthly[], нулём он не считается.

Возвращает (summary, internal):
summary — StatementSummary для API; internal — точные суммы для баллов и сметы
(средние считаем дробями Fraction, чтобы не было ошибок округления на границах порогов).
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import re
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from ..clock import add_months
from ..config import get_settings
from ..errors import ApiError

HEADERS = {"date", "amount", "direction", "counterparty", "counterpartyInn", "purpose"}

# ---- поступления (mocks-contract.md → «Классификация поступлений») ----
EXCLUSIONS = ["возврат", "сторно", "отмена операции", "refund", "reversal", "возврат налога",
              "возмещение налога", "зачисление кредита", "выдача кредита", "кредитные средства", "заем",
              "займ", "договор займа", "перевод собственных средств", "перевод между своими счетами",
              "перевод между счетами", "внутренний перевод", "пополнение счета", "внесение наличных",
              "взнос наличных", "депозит", "вклад", "субсидия", "грант", "страховое возмещение",
              "продажа основных средств", "продажа оборудования", "возврат займа"]
ACQUIRING = ["эквайринг", "acquiring", "реестр операций по картам", "выплаты по операциям с картами",
             "зачисление по операциям с картами", "возмещение по операциям с картами",
             "сбп оплата товаров", "сбп оплата услуг"]
CUSTOMER = ["оплата по договору", "оплата по счету", "оплата за", "оплата товара", "оплата товаров",
            "оплата услуг", "оплата работ", "аванс по договору", "предоплата по договору",
            "выручка от реализации", "поступление от покупателя", "платеж покупателя", "оплата по заказу"]

# ---- списания (product-rules-v1.md, 3.1): первое совпавшее НАЧАЛО слова ----
OUT_RULES = [("LOAN_PAYMENTS", ["кредит", "лизинг", "займ", "заем"]),
             ("TAXES", ["налог", "взнос", "фнс", "уфк"]),
             ("SALARY", ["заработн", "зарплат", "оплата труда"]),
             ("RENT", ["аренд"]),
             ("MATERIALS", ["материал", "сырь", "товар", "закуп", "поставк"])]
OUT_CATEGORIES = ["RENT", "SALARY", "MATERIALS", "TAXES", "LOAN_PAYMENTS", "OTHER"]


def normalize_purpose(text: str) -> str:
    """casefold, ё→е, всё кроме а-я/a-z/0-9 → пробел, лишние пробелы убрать."""
    s = (text or "").casefold().replace("ё", "е")
    s = re.sub(r"[^а-яa-z0-9]+", " ", s)
    return " ".join(s.split())


def _has_phrase(norm: str, phrases: list[str]) -> bool:
    """Ищем ЦЕЛЫЕ слова/фразы: « возврат » не совпадёт с «возврата»."""
    padded = f" {norm} "
    return any(f" {p} " in padded for p in phrases)


def classify_in(purpose: str, counterparty_inn: str) -> str:
    p = normalize_purpose(purpose)
    if _has_phrase(p, EXCLUSIONS):
        return "OTHER_IN"
    if _has_phrase(p, ACQUIRING):
        return "ACQUIRING"
    digits = (counterparty_inn or "").replace(" ", "")
    if _has_phrase(p, CUSTOMER) and digits.isdigit() and len(digits) in (10, 12):
        return "CUSTOMER"
    return "OTHER_IN"


def classify_out(purpose: str) -> str:
    p = normalize_purpose(purpose)
    for category, stems in OUT_RULES:
        if any(re.search(rf"(^| ){re.escape(s)}", p) for s in stems):
            return category
    return "OTHER"


def round_half_up(x: Fraction | float, digits: int = 0) -> int | float:
    q = Decimal(1).scaleb(-digits)
    d = Decimal(x.numerator) / Decimal(x.denominator) if isinstance(x, Fraction) else Decimal(str(x))
    r = d.quantize(q, rounding=ROUND_HALF_UP)
    return int(r) if digits == 0 else float(r)


def window_months(eval_date: dt.date) -> list[str]:
    first = dt.date(eval_date.year, eval_date.month, 1)
    return [add_months(first, -i).strftime("%Y-%m") for i in range(12, 0, -1)]


def _unreadable(reason: str, line: int | None = None) -> ApiError:
    details = {"reason": reason}
    if line:
        details["line"] = line
    return ApiError(400, "STATEMENT_UNREADABLE",
                    "Не удалось прочитать выписку. Нужен CSV с колонками date;amount;direction;"
                    "counterparty;counterpartyInn;purpose", details)


def parse_statement(raw: bytes, eval_date: dt.date) -> tuple[dict, dict]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise _unreadable("файл не в кодировке UTF-8")
    if not text.strip():
        raise _unreadable("файл пустой")

    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    names = reader.fieldnames or []
    if len(names) != len(HEADERS) or set(names) != HEADERS:
        raise _unreadable("колонки не совпадают с форматом выписки")

    window = window_months(eval_date)
    months: dict[str, dict] = {}
    categories = {c: 0 for c in OUT_CATEGORIES}
    customers: dict[str, dict] = {}
    all_in = other_in = 0
    dates: list[dt.date] = []

    for row in reader:
        line = reader.line_num
        if None in row or any(v is None for v in row.values()):
            raise _unreadable("в строке не то количество полей", line)
        if not any(v.strip() for v in row.values()):
            continue  # пустые строки разрешены
        try:
            d = dt.date.fromisoformat(row["date"])
            if len(row["date"]) != 10:
                raise ValueError
        except ValueError:
            raise _unreadable("дата не в формате ГГГГ-ММ-ДД", line)
        if not re.fullmatch(r"[1-9][0-9]*", row["amount"]):
            raise _unreadable("сумма должна быть целым положительным числом без копеек", line)
        if row["direction"] not in ("IN", "OUT"):
            raise _unreadable("direction должен быть IN или OUT", line)
        if d > eval_date:
            raise _unreadable("дата операции позже даты оценки", line)

        ym = d.strftime("%Y-%m")
        if ym not in window:
            continue
        amount = int(row["amount"])
        dates.append(d)
        m = months.setdefault(ym, {"month": ym, "income": 0, "expense": 0})
        if row["direction"] == "IN":
            all_in += amount
            cat = classify_in(row["purpose"], row["counterpartyInn"])
            if cat == "OTHER_IN":
                other_in += amount
            else:
                m["income"] += amount
                key = row["counterpartyInn"].strip() or row["counterparty"].strip()
                c = customers.setdefault(key, {"name": row["counterparty"].strip(),
                                               "inn": row["counterpartyInn"].strip(), "sum": 0})
                c["sum"] += amount
        else:
            m["expense"] += amount
            categories[classify_out(row["purpose"])] += amount

    if not months:
        raise _unreadable("в выписке нет операций за последние 12 завершённых месяцев")

    present = [ym for ym in window if ym in months]
    n = len(present)
    monthly = [months[ym] for ym in present]
    income_sum = sum(m["income"] for m in monthly)
    expense_sum = sum(m["expense"] for m in monthly)

    s = get_settings()
    warnings = [f"Нет операций за {ym} — период не подтверждён" for ym in window if ym not in months]
    if n < 12:
        warnings.append(f"Выписка подтверждает {n} из 12 календарных месяцев")
    if all_in == 0:
        warnings.append("Нет подтверждённых поступлений")
    elif other_in * 100 > all_in * s.OTHER_IN_MAX_SHARE_PERCENT:
        warnings.append(f"Более {s.OTHER_IN_MAX_SHARE_PERCENT}% входящих операций не удалось подтвердить как выручку")

    top = sorted(customers.values(), key=lambda c: -c["sum"])[:3]  # ВРЕМЕННО (вопрос 14)
    summary = {
        "periodFrom": min(dates).isoformat(),
        "periodTo": max(dates).isoformat(),
        "monthsCovered": n,
        "avgMonthlyIncome": round_half_up(Fraction(income_sum, n)),
        "avgMonthlyExpense": round_half_up(Fraction(expense_sum, n)),
        "monthly": monthly,
        "expenseByCategory": {c: round_half_up(Fraction(v, n)) for c, v in categories.items() if v},
        "topCustomers": [
            {k: v for k, v in {"name": c["name"], "inn": c["inn"] or None,
                               "sharePercent": round_half_up(Fraction(c["sum"] * 100, income_sum), 1)}.items()
             if v is not None}
            for c in top] if income_sum else [],
        "otherBankLoanPaymentsMonthly": round_half_up(Fraction(categories["LOAN_PAYMENTS"], n)),
        "warnings": warnings,
    }
    internal = {
        "window": window,
        "monthsCovered": n,
        "incomeSum": income_sum,
        "expenseSum": expense_sum,
        "allIn": all_in,
        "otherIn": other_in,
        "categorySums": categories,
        "monthlyIncome": {m["month"]: m["income"] for m in monthly},
    }
    return summary, internal


# ---- точные средние для баллов и сметы ----

def avg_income(internal: dict) -> Fraction:
    return Fraction(internal["incomeSum"], internal["monthsCovered"])


def avg_expense(internal: dict) -> Fraction:
    return Fraction(internal["expenseSum"], internal["monthsCovered"])


def avg_category(internal: dict, category: str) -> Fraction:
    return Fraction(internal["categorySums"].get(category, 0), internal["monthsCovered"])
