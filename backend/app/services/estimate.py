"""Шаг 7. Смета (Estimate) — contract/product-rules-v1.md, раздел 3.

Смета = строки-«кубики». У каждой строки: категория, сумма, откуда цифра (source) и продукт.
Суммы строк округляются ВВЕРХ до 10 000 ₽ (ROUND). Слова клиента дают суммы строк, но не баллы.

build_estimate() возвращает (estimate, missing):
missing — чего не хватает для автоматического предложения (нет цены оборудования,
нет суммы у стартапа, цель OTHER). Это решается при submit (INFO_REQUESTED / MANUAL_REVIEW).

В строках храним служебные поля с подчёркиванием (_edited, _capped) — наружу они не уходят:
схема EstimateItem в ответе их отбрасывает.
"""
from __future__ import annotations

import math
from fractions import Fraction

from ..config import get_settings
from .goals import answers_map, goal_types
from .statement import avg_category, avg_income

CREDIT_PRODUCTS = {"LEASING", "INVESTMENT_LOAN", "CREDIT_LINE", "OVERDRAFT", "STARTER_LOAN"}
FINANCED = CREDIT_PRODUCTS | {"BANK_GUARANTEE"}   # входят в Estimate.total


def round_up(x) -> int:
    step = get_settings().ROUND
    return int(math.ceil(Fraction(x) / step) * step)


def round_down(x) -> int:
    step = get_settings().ROUND
    return int(math.floor(Fraction(x) / step) * step)


def equipment_product(amount) -> str:
    return "LEASING" if amount >= get_settings().LEASING_MIN else "INVESTMENT_LOAN"


def overdraft_cap(st: dict | None) -> int:
    """Лимит овердрафта ≤ 30% средней выручки; без выписки — 0."""
    return round_down(get_settings().OVERDRAFT_SHARE * avg_income(st)) if st else 0


def buffer_amount(items: list[dict], st: dict | None) -> int:
    """Подушка: 10% от кредитных строк (кроме овердрафта), но ≤ 30% средней выручки."""
    s = get_settings()
    base = sum(i["amount"] for i in items if i["product"] in CREDIT_PRODUCTS - {"OVERDRAFT"} and not i.get("excluded"))
    return min(round_up(Fraction(base) * Fraction(str(s.BUFFER_SHARE))), overdraft_cap(st))


def build_estimate(goals: dict, st: dict | None, has_business: bool) -> tuple[dict, list[str]]:
    s = get_settings()
    a = answers_map(goals)
    items: list[dict] = []
    missing: list[str] = []
    seq = [0]

    def add(category, title, amount, source, product, note=None, **extra):
        if amount and amount > 0:
            seq[0] += 1
            item = {"id": f"i{seq[0]}", "category": category, "title": title, "amount": round_up(amount),
                    "source": source, "product": product, "excluded": False}
            if note:
                item["note"] = note
            item.update(extra)
            items.append(item)

    same_note = "Как в первой точке по выписке"
    for g in goal_types(goals):
        if g == "EQUIPMENT":
            price = a.get("equipment.price")
            if not price:
                missing.append("equipment.price")
            else:
                add("EQUIPMENT", a.get("equipment.what") or "Оборудование", price, "CLIENT", equipment_product(price))
        elif g == "NEW_LOCATION":
            same = a.get("location.sameAsFirst") is True and st is not None
            add("PREMISES", "Ремонт помещения", a.get("location.renovation") or 0, "CLIENT", "INVESTMENT_LOAN")
            if a.get("location.premises") in ("RENT_FOUND", "RENT_NOT_FOUND") and same:
                add("PREMISES", f"Аренда на первые {s.RENT_MONTHS} месяца",
                    s.RENT_MONTHS * avg_category(st, "RENT"), "STATEMENT", "CREDIT_LINE", same_note)
            if a.get("location.equipment"):
                add("EQUIPMENT", "Оборудование для новой точки", a["location.equipment"], "CLIENT",
                    equipment_product(a["location.equipment"]))
            if same:
                add("STAFF", f"Зарплаты на первые {s.STAFF_MONTHS} месяца",
                    s.STAFF_MONTHS * avg_category(st, "SALARY"), "STATEMENT", "CREDIT_LINE", same_note)
                add("INVENTORY", "Материалы на первый месяц", avg_category(st, "MATERIALS"), "STATEMENT",
                    "CREDIT_LINE", same_note)
            elif a.get("location.staff"):
                add("STAFF", f"Зарплаты на первые {s.STAFF_MONTHS} месяца",
                    s.STAFF_MONTHS * a["location.staff"] * s.SALARY_PER_EMPLOYEE, "RULE", "CREDIT_LINE")
        elif g == "INVENTORY":
            add("INVENTORY", a.get("inventory.items") or "Закупка", a.get("inventory.amount") or 0, "CLIENT", "CREDIT_LINE")
        elif g == "CASH_GAP":
            add("BUFFER", "Кассовый разрыв", a.get("cashgap.amount") or 0, "CLIENT", "OVERDRAFT")
        elif g == "TENDER":
            add("TENDER", "Банковская гарантия", a.get("tender.guarantee") or 0, "CLIENT", "BANK_GUARANTEE")
            if a.get("tender.execution"):
                add("TENDER", "Исполнение контракта",
                    Fraction(str(s.TENDER_EXECUTION_SHARE)) * a["tender.contract"], "RULE", "CREDIT_LINE")
        elif g == "MARKETING":
            months = a.get("marketing.months") or s.MARKETING_DEFAULT_MONTHS
            add("MARKETING", a.get("marketing.what") or "Реклама", a["marketing.budget"] * months, "CLIENT",
                "PARTNER_SERVICE", f"Скидка {s.PARTNER_DISCOUNT:g}% у партнёра банка")
        elif g == "START_BUSINESS":
            amount = a.get("common.amount")
            if not amount:
                missing.append("common.amount")
            else:
                capped = amount > s.STARTER_MAX
                add("EQUIPMENT", "Стартовые вложения: " + (a.get("start.needs") or "запуск бизнеса"),
                    min(amount, s.STARTER_MAX), "CLIENT", "STARTER_LOAN",
                    "Сумма уменьшена до максимума стартового кредита" if capped else None,
                    **({"_capped": True} if capped else {}))
        elif g == "OTHER":
            missing.append("OTHER")

    # Подушка — только при выписке от 6 месяцев и если овердрафта в смете ещё нет
    if st and st["monthsCovered"] >= s.MIN_STATEMENT_MONTHS_FOR_OVERDRAFT and items \
            and not any(i["product"] == "OVERDRAFT" for i in items):
        add("BUFFER", "Подушка на непредвиденное", buffer_amount(items, st), "RULE", "OVERDRAFT", _buffer=True)

    # Овердрафт не больше лимита; что сверх — кредитная линия
    for item in list(items):
        if item["product"] == "OVERDRAFT":
            cap = overdraft_cap(st)
            if item["amount"] > cap:
                rest = item["amount"] - cap
                item["amount"] = cap
                add(item["category"], item["title"] + " (сверх лимита овердрафта)", rest, "RULE", "CREDIT_LINE")
                if cap == 0:
                    items.remove(item)

    return finish(items), missing


def finish(items: list[dict]) -> dict:
    total = sum(i["amount"] for i in items if i["product"] in FINANCED and not i.get("excluded"))
    return {"items": items, "total": total, "startSmallerSuggested": False}


def apply_client_edits(estimate: dict, edits: list[dict], st: dict | None) -> dict:
    """PUT /estimate: клиент меняет сумму строки или исключает её. Продукт под строку подбирает сервер."""
    from ..errors import ApiError

    items = [dict(i) for i in estimate["items"]]
    by_id = {i["id"]: i for i in items}
    unknown = [e["id"] for e in edits if e["id"] not in by_id]
    if unknown:
        raise ApiError(400, "VALIDATION_ERROR", "В смете нет таких строк", {"unknownItems": unknown})
    for e in edits:
        item = by_id[e["id"]]
        if e.get("amount") is not None:
            item["amount"] = round_up(e["amount"]) if e["amount"] > 0 else 0
            item["_edited"] = True
        if e.get("excluded") is not None:
            item["excluded"] = e["excluded"]
        # Оборудование: лизинг от 300 000, дешевле — инвестиционный кредит
        if item["category"] == "EQUIPMENT" and item["product"] in ("LEASING", "INVESTMENT_LOAN"):
            item["product"] = equipment_product(item["amount"])
    # Строку «Подушка» пересчитываем по правилу, если клиент её сам не правил (ВРЕМЕННО, вопрос 13)
    for item in items:
        if item.get("_buffer") and not item.get("_edited"):
            item["amount"] = buffer_amount(items, st)
        if item["product"] == "OVERDRAFT":
            item["amount"] = min(item["amount"], overdraft_cap(st))
    return finish(items)
