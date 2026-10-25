"""Шаг 9. Предложения (Offer) и график платежей — contract/product-rules-v1.md, разделы 2, 4, 5.

Как строится:
1. MAIN — вся смета. Строки с одним продуктом объединяются в один продукт.
2. Безопасный платёж: fullPayment ≤ (выручка − расходы) ÷ 1,3. Если больше — все продукты
   уменьшаем в одинаковой доле шагом 1% (суммы вниз до 10 000), termsChanged = true.
   Не проходит даже 10% сметы → автоматического предложения нет (MANUAL_REVIEW, CHANGE_TERMS).
3. SMALLER («начать меньше», 60%) — если при падении выручки на 20% платёж не по силам или MAIN уменьшали.
4. ALTERNATIVE («без отсрочки») — если в MAIN есть отсрочка.
Не больше 3 предложений: MAIN, SMALLER, ALTERNATIVE.

Ставка = KEY_RATE + надбавка продукта + поправка (route): AUTO и ≥90 баллов → −1, STAFF → +2.
"""
from __future__ import annotations

import math
from fractions import Fraction

from .. import refdata
from ..config import get_settings
from .estimate import CREDIT_PRODUCTS, FINANCED, round_down
from .goals import goal_types
from .statement import avg_expense, avg_income

PRODUCT_TITLES = {"LEASING": "лизинг", "INVESTMENT_LOAN": "инвестиционный кредит", "CREDIT_LINE": "кредитная линия",
                  "OVERDRAFT": "овердрафт", "BANK_GUARANTEE": "банковская гарантия", "STARTER_LOAN": "стартовый кредит"}
GRACE_PRODUCTS = ("INVESTMENT_LOAN", "CREDIT_LINE", "STARTER_LOAN")
GRACE_GOALS = {"NEW_LOCATION", "START_BUSINESS"}


def money(x: int) -> str:
    return f"{x:,}".replace(",", " ")


def rate(product: str, score_total: int | None, route: str | None) -> float:
    s = get_settings()
    if product == "BANK_GUARANTEE":
        return s.GUARANTEE_FEE
    r = s.KEY_RATE + s.spread(product)
    if route == "AUTO" and score_total is not None and score_total >= s.AUTO_RATE_DISCOUNT_SCORE:
        r -= s.AUTO_RATE_DISCOUNT
    if route == "STAFF":
        r += s.STAFF_RATE_MARKUP
    return float(r)


def annuity_schedule(principal: int, annual_rate: float, n: int, grace: int) -> list[dict]:
    """График одного продукта: месяцы 1…g — только проценты, потом аннуитет на n−g месяцев.
    Каждая строка округляется до рубля, в последний месяц гасится весь остаток."""
    r = annual_rate / 100 / 12
    rows, debt, pay = [], principal, None
    for k in range(1, n + 1):
        interest = round(debt * r)
        if k <= grace:
            principal_part = 0
        else:
            if pay is None:
                pay = round(principal * r / (1 - (1 + r) ** -(n - grace)))
            principal_part = debt if k == n else pay - interest
        rows.append({"month": k, "principal": principal_part, "interest": interest,
                     "total": principal_part + interest})
        debt -= principal_part
    return rows


def _active(items: list[dict]) -> list[dict]:
    return [i for i in items if not i.get("excluded") and i["amount"] > 0]


def build_offer(kind: str, items: list[dict], goals: dict | None, score_total, route, *,
                grace_on: bool = True, share: float = 1.0, term_override: int | None = None,
                force_grace: bool = False) -> dict:
    s = get_settings()
    goals_set = set(goal_types(goals))
    by_product: dict[str, list[dict]] = {}
    for i in _active(items):
        if i["product"] in FINANCED:
            by_product.setdefault(i["product"], []).append(i)
    products, monthly, overpay = [], {}, 0
    for prod, its in by_product.items():
        base = sum(x["amount"] for x in its)
        k = share if isinstance(share, Fraction) else Fraction(str(share))
        amount = round_down(base * k) if k != 1 else base
        if amount <= 0:
            continue
        rt = rate(prod, score_total, route)
        if prod == "BANK_GUARANTEE":
            term = s.TERM_BANK_GUARANTEE
            fee = round(amount * rt / 100 * term / 12)
            overpay += fee
            products.append({"product": prod, "amount": amount, "termMonths": term, "ratePercent": rt,
                             "monthlyPayment": 0, "coversItems": [x["id"] for x in its], "fee": fee})
            continue
        term = s.term(prod)
        if term_override and prod not in ("OVERDRAFT",):
            term = term_override
        grace = 0
        if grace_on and prod in GRACE_PRODUCTS and (goals_set & GRACE_GOALS or force_grace):
            grace = s.GRACE_MONTHS
        if prod == "OVERDRAFT":
            # Осторожная оценка: проценты, как будто лимит выбран полностью
            pay = round(amount * rt / 1200)
            rows = [{"month": k, "total": pay, "interest": pay} for k in range(1, term + 1)]
        else:
            rows = annuity_schedule(amount, rt, term, min(grace, term - 1))
        for row in rows:
            monthly[row["month"]] = monthly.get(row["month"], 0) + row["total"]
        if prod != "OVERDRAFT":
            overpay += sum(row["interest"] for row in rows)
        p = {"product": prod, "amount": amount, "termMonths": term, "ratePercent": rt,
             "monthlyPayment": max(row["total"] for row in rows), "coversItems": [x["id"] for x in its]}
        if grace:
            p["gracePeriodMonths"] = grace
        if prod == "OVERDRAFT":
            p["note"] = "проценты, если лимит выбран полностью"
        products.append(p)
    partner = [i for i in _active(items) if i["product"] == "PARTNER_SERVICE"]
    return {
        "kind": kind, "products": products,
        "totalAmount": sum(p["amount"] for p in products),
        "firstMonthsPayment": monthly.get(1, 0),
        "fullPayment": max(monthly.values()) if monthly else 0,
        "overpayment": overpay,
        "partnerServices": [{"title": i["title"], "amount": i["amount"],
                             "withDiscount": round(i["amount"] * (100 - s.PARTNER_DISCOUNT) / 100),
                             "discountPercent": s.PARTNER_DISCOUNT} for i in partner],
    }


def payback(okved: str | None) -> dict | None:
    """Ориентир отрасли typicalBreakEvenMonths: normal = ориентир, good = 75%, bad = 150% (null, если > 60)."""
    s = get_settings()
    ind = refdata.find_industry(okved)
    n = ind.get("typicalBreakEvenMonths") if ind else None
    if not n:
        return None
    bad = math.ceil(n * s.PAYBACK_BAD_SHARE)
    return {"good": math.ceil(n * s.PAYBACK_GOOD_SHARE), "normal": n,
            "bad": bad if bad <= s.PAYBACK_BAD_MAX_MONTHS else None}


def why_it_fits(o: dict) -> list[str]:
    s = get_settings()
    out = []
    g = max((p.get("gracePeriodMonths", 0) for p in o["products"]), default=0)
    if g:
        out.append(f"Отсрочка {g} мес.: пока бизнес запускается, платите только проценты — "
                   f"{money(o['firstMonthsPayment'])} ₽")
    if any(p["product"] == "LEASING" for p in o["products"]):
        out.append("Оборудование в лизинге — не нужен залог")
    if o["partnerServices"]:
        out.append(f"Реклама у партнёра банка со скидкой {s.PARTNER_DISCOUNT:g}%")
    if o["kind"] == "SMALLER":
        out.insert(0, "Если выручка упадёт на 20%, платёж всё равно по силам")
    if o["kind"] == "ALTERNATIVE":
        out.insert(0, "Без отсрочки — переплата меньше")
    return out[:3]


def to_api(o: dict, okved: str | None) -> dict:
    """Приводим к схеме Offer из openapi.yaml."""
    products = []
    for p in o["products"]:
        q = {k: p[k] for k in ("product", "amount", "termMonths", "ratePercent", "monthlyPayment", "coversItems")}
        q["title"] = PRODUCT_TITLES[p["product"]].capitalize()
        for k in ("gracePeriodMonths", "fee", "note"):
            if k in p:
                q[k] = p[k]
        products.append(q)
    out = {"id": o["kind"].lower(), "kind": o["kind"], "termsChanged": o["termsChanged"], "products": products,
           "totalAmount": o["totalAmount"], "firstMonthsPayment": o["firstMonthsPayment"],
           "fullPayment": o["fullPayment"], "overpayment": o["overpayment"],
           "partnerServices": o["partnerServices"], "whyItFits": why_it_fits(o)}
    pb = payback(okved)
    if pb:
        out["paybackMonths"] = pb
    return out


def build_offers(estimate: dict, goals: dict | None, st: dict | None, score_total, route: str,
                 okved: str | None) -> tuple[list[dict] | None, bool, str | None]:
    """Возвращает (предложения для API, startSmallerSuggested, причина_если_нет_предложения)."""
    s = get_settings()
    items = estimate["items"]
    est_total = sum(i["amount"] for i in _active(items) if i["product"] in FINANCED)
    if est_total <= 0:
        return None, False, "В смете нет строк для финансирования"
    capped = any(i.get("_capped") for i in _active(items))

    main = build_offer("MAIN", items, goals, score_total, route)
    reduced, start_smaller = False, False
    if st:
        R, E = avg_income(st), avg_expense(st)
        safe = (R - E) / Fraction(str(s.DSCR))
        share = 1.0
        while main["fullPayment"] > safe and share > s.MIN_SHARE:
            share = round(share - 0.01, 2)
            main = build_offer("MAIN", items, goals, score_total, route, share=share)
            reduced = True
        if main["fullPayment"] > safe:
            return None, False, "Даже 10% сметы не проходит по безопасному платежу"
        start_smaller = main["fullPayment"] > Fraction(str(s.STRESS_REVENUE_SHARE)) * R - E
    main["termsChanged"] = reduced or capped
    offers = [main]
    if start_smaller or reduced:
        ratio = s.SMALLER_SHARE * (main["totalAmount"] / est_total if reduced else 1)
        smaller = build_offer("SMALLER", items, goals, score_total, route, share=ratio)
        smaller["termsChanged"] = True
        offers.append(smaller)
    if any(p.get("gracePeriodMonths") for p in main["products"]) and len(offers) < 3:
        alt = build_offer("ALTERNATIVE", items, goals, score_total, route, grace_on=False,
                          share=main["totalAmount"] / est_total if reduced else 1.0)
        alt["termsChanged"] = reduced or capped
        offers.append(alt)
    return [to_api(o, okved) for o in offers], start_smaller, None


def staff_terms_offer(estimate: dict | None, goals: dict | None, st: dict | None, okved: str | None,
                      amount: int, term: int | None, startup: bool) -> list[dict]:
    """CHANGE_TERMS сотрудника (product-rules, раздел 6): MAIN масштабируется до newTerms.amount,
    срок newTerms.termMonths ставится всем кредитным продуктам, кроме овердрафта и гарантии.
    Без сметы (handoff, цель «Другое») — один INVESTMENT_LOAN (у стартапа STARTER_LOAN)."""
    amount = max(round_down(amount), get_settings().ROUND)
    items = [i for i in (estimate or {}).get("items", []) if i["product"] in FINANCED]
    total = sum(i["amount"] for i in _active(items))
    if total > 0:
        o = build_offer("MAIN", items, goals, None, "STAFF", share=Fraction(amount, total), term_override=term)
    else:
        product = "STARTER_LOAN" if startup else "INVESTMENT_LOAN"
        item = {"id": "staff", "category": "EQUIPMENT", "title": "Условия сотрудника", "amount": amount,
                "source": "RULE", "product": product}
        o = build_offer("MAIN", [item], goals, None, "STAFF", term_override=term, force_grace=startup)
    o["termsChanged"] = True
    return [to_api(o, okved)]


def preview_start_smaller(estimate: dict, goals: dict | None, st: dict | None) -> bool:
    """Подсказка «начать меньше» ещё до отправки (по базовым ставкам, без поправок)."""
    if not st or estimate["total"] <= 0:
        return False
    _, flag, _ = build_offers(estimate, goals, st, None, "PREVIEW", None)
    return flag
