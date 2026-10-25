"""Эталонный расчёт сметы, предложений и графика по «Правилам продуктов» v1 — для сверки.

ЭТО НЕ КОД БЭКЕНДА. Нужен, чтобы примеры в contract/product-rules-v1.md
и ожидаемые результаты были посчитаны, а не вписаны руками.
Запуск из корня репозитория: python tests/reference_offers.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
from decimal import Decimal, ROUND_HALF_UP, getcontext
from fractions import Fraction as Fr
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
CONTRACT = ROOT / "contract"
MOCK_DATA = ROOT / "mocks" / "data"
sys.path.insert(0, str(TESTS))
import reference_scoring as rs  # noqa: E402

# ---------------- настройки (раздел 2 правил) ----------------
CFG = {
    "KEY_RATE": 14.0,
    "SPREAD": {"LEASING": 4.0, "INVESTMENT_LOAN": 5.0, "CREDIT_LINE": 6.0, "OVERDRAFT": 7.0, "STARTER_LOAN": 8.0},
    "GUARANTEE_FEE": 3.0,
    "TERM": {"LEASING": 36, "INVESTMENT_LOAN": 36, "CREDIT_LINE": 18, "OVERDRAFT": 12, "STARTER_LOAN": 24},
    "GRACE": 3,
    "LEASING_MIN": 300000,
    "ROUND": 10000,
    "DSCR": Fr(13, 10),
    "OVERDRAFT_SHARE": Fr(3, 10),
    "BUFFER_SHARE": Fr(1, 10),
    "SMALLER_SHARE": 60,
    "STAFF_MONTHS": 3,
    "RENT_MONTHS": 3,
    "SALARY_PER_EMPLOYEE": 60000,
    "MARKETING_DEFAULT_MONTHS": 3,
    "PARTNER_DISCOUNT": 20,
    "TENDER_EXECUTION_SHARE": Fr(3, 10),
    "STARTER_MAX": 1000000,
}
CREDIT = {"LEASING", "INVESTMENT_LOAN", "CREDIT_LINE", "OVERDRAFT", "STARTER_LOAN"}


getcontext().prec = 40


def up(x):
    """Вверх до 10 000 ₽ (точная дробь, без float)."""
    return math.ceil(Fr(x) / CFG["ROUND"]) * CFG["ROUND"]


def down(x):
    """Вниз до 10 000 ₽."""
    return math.floor(Fr(x) / CFG["ROUND"]) * CFG["ROUND"]


def rub(x):
    """До рубля, половина вверх (product-rules-v1.md, раздел 5)."""
    return int(Decimal(x).quantize(Decimal(1), rounding=ROUND_HALF_UP))


# ---------------- категории списаний (раздел 3.1) ----------------
OUT_RULES = [("LOAN_PAYMENTS", ["кредит", "лизинг", "займ", "заем"]),
             ("TAXES", ["налог", "взнос", "фнс", "уфк"]),
             ("SALARY", ["заработн", "зарплат", "оплата труда"]),
             ("RENT", ["аренд"]),
             ("MATERIALS", ["материал", "сырь", "товар", "закуп", "поставк"])]


def out_category(purpose):
    p = rs.norm_purpose(purpose)
    for cat, stems in OUT_RULES:
        if any(re.search(rf"(^| ){s}", p) for s in stems):
            return cat
    return "OTHER"


def expense_by_category(case):
    import csv, io
    text = (TESTS / case["statementFile"]).read_text(encoding="utf-8")
    summary, _ = rs.parse_statement(text, rs.EVAL)
    sums = {}
    for row in csv.DictReader(io.StringIO(text), delimiter=";"):
        if row["direction"] == "OUT" and row["date"][:7] in summary["monthly"]:
            c = out_category(row["purpose"])
            sums[c] = sums.get(c, 0) + int(row["amount"])
    n = summary["monthsCovered"]
    R = Fr(sum(m["income"] for m in summary["monthly"].values()), n)
    E = Fr(sum(m["expense"] for m in summary["monthly"].values()), n)
    return {k: Fr(v, n) for k, v in sums.items()}, R, E, n


# ---------------- смета (раздел 3) ----------------

def answers(case):
    a = {}
    for g in case["goalsData"]["goals"]:
        for x in g["answers"]:
            a[x["questionId"]] = x["value"]
    for x in case["goalsData"].get("commonAnswers", []):
        a[x["questionId"]] = x["value"]
    return a


def estimate(case):
    a = answers(case)
    goals = [g["goalType"] for g in case["goalsData"]["goals"]]
    st = expense_by_category(case) if case["statementFile"] else None
    items, missing = [], []

    def add(cat, title, amount, source, product, note=None):
        if amount and amount > 0:
            items.append({"id": f"i{len(items) + 1}", "category": cat, "title": title, "amount": up(amount),
                          "source": source, "product": product, **({"note": note} if note else {})})

    def eq_product(x):
        return "LEASING" if x >= CFG["LEASING_MIN"] else "INVESTMENT_LOAN"

    for g in goals:
        if g == "EQUIPMENT":
            price = a.get("equipment.price")
            if not price:
                missing.append("equipment.price")
            else:
                add("EQUIPMENT", a.get("equipment.what") or "Оборудование", price, "CLIENT", eq_product(price))
        elif g == "NEW_LOCATION":
            same = a.get("location.sameAsFirst") is True and st is not None
            add("PREMISES", "Ремонт помещения", a.get("location.renovation") or 0, "CLIENT", "INVESTMENT_LOAN")
            if a.get("location.premises") in ("RENT_FOUND", "RENT_NOT_FOUND") and same:
                add("PREMISES", f"Аренда на первые {CFG['RENT_MONTHS']} месяца", CFG["RENT_MONTHS"] * st[0].get("RENT", 0),
                    "STATEMENT", "CREDIT_LINE", "Как в первой точке по выписке")
            if a.get("location.equipment"):
                add("EQUIPMENT", "Оборудование для новой точки", a["location.equipment"], "CLIENT", eq_product(a["location.equipment"]))
            if same:
                add("STAFF", f"Зарплаты на первые {CFG['STAFF_MONTHS']} месяца", CFG["STAFF_MONTHS"] * st[0].get("SALARY", 0),
                    "STATEMENT", "CREDIT_LINE", "Как в первой точке по выписке")
                add("INVENTORY", "Материалы на первый месяц", st[0].get("MATERIALS", 0), "STATEMENT", "CREDIT_LINE",
                    "Как в первой точке по выписке")
            elif a.get("location.staff"):
                add("STAFF", f"Зарплаты на первые {CFG['STAFF_MONTHS']} месяца",
                    CFG["STAFF_MONTHS"] * a["location.staff"] * CFG["SALARY_PER_EMPLOYEE"], "RULE", "CREDIT_LINE")
        elif g == "INVENTORY":
            add("INVENTORY", a.get("inventory.items") or "Закупка", a.get("inventory.amount") or 0, "CLIENT", "CREDIT_LINE")
        elif g == "CASH_GAP":
            add("BUFFER", "Кассовый разрыв", a.get("cashgap.amount") or 0, "CLIENT", "OVERDRAFT")
        elif g == "TENDER":
            add("TENDER", "Банковская гарантия", a.get("tender.guarantee") or 0, "CLIENT", "BANK_GUARANTEE")
            if a.get("tender.execution"):
                add("TENDER", "Исполнение контракта", CFG["TENDER_EXECUTION_SHARE"] * a["tender.contract"], "RULE", "CREDIT_LINE")
        elif g == "MARKETING":
            months = a.get("marketing.months") or CFG["MARKETING_DEFAULT_MONTHS"]
            add("MARKETING", a.get("marketing.what") or "Реклама", a["marketing.budget"] * months, "CLIENT", "PARTNER_SERVICE",
                f"Скидка {CFG['PARTNER_DISCOUNT']}% у партнёра банка")
        elif g == "START_BUSINESS":
            amt = a.get("common.amount")
            if not amt:
                missing.append("common.amount")
            else:
                add("EQUIPMENT", "Стартовые вложения: " + (a.get("start.needs") or "запуск бизнеса"),
                    min(amt, CFG["STARTER_MAX"]), "CLIENT", "STARTER_LOAN")
        elif g == "OTHER":
            missing.append("OTHER")
    # Подушка — только у действующего бизнеса с выпиской от 6 месяцев
    if st and st[3] >= 6 and items:
        base = sum(i["amount"] for i in items if i["product"] in CREDIT - {"OVERDRAFT"})
        buf = min(up(base * CFG["BUFFER_SHARE"]), down(CFG["OVERDRAFT_SHARE"] * st[1]))
        if not any(i["product"] == "OVERDRAFT" for i in items):
            add("BUFFER", "Подушка на непредвиденное", buf, "RULE", "OVERDRAFT")
    # Овердрафт не больше 30% средней выручки; остаток — кредитная линия
    for i in list(items):
        if i["product"] == "OVERDRAFT":
            cap = down(CFG["OVERDRAFT_SHARE"] * st[1]) if st else 0
            if i["amount"] > cap:
                rest = i["amount"] - cap
                i["amount"] = cap
                add(i["category"], i["title"] + " (сверх лимита овердрафта)", rest, "RULE", "CREDIT_LINE")
                if cap == 0:
                    items.remove(i)
    total = sum(i["amount"] for i in items if i["product"] in CREDIT | {"BANK_GUARANTEE"})
    return {"items": items, "total": total, "missing": missing}, st


# ---------------- ставка и график (разделы 2, 5) ----------------

def rate(product, score_total, route):
    if product == "BANK_GUARANTEE":
        return CFG["GUARANTEE_FEE"]
    r = CFG["KEY_RATE"] + CFG["SPREAD"][product]
    if route == "AUTO" and score_total is not None and score_total >= 90:
        r -= 1
    if route == "STAFF":
        r += 2
    return r


def schedule(P, annual, n, g):
    """Раздел 5: Decimal, каждая строка до рубля половиной вверх, последний месяц закрывает долг."""
    r = Decimal(str(annual)) / Decimal(1200)
    rows, debt, pay = [], P, None
    for k in range(1, n + 1):
        interest = rub(Decimal(debt) * r)
        if k <= g:
            principal = 0
        else:
            if pay is None:
                pay = rub(Decimal(P) * r / (1 - (1 + r) ** -(n - g)))
            principal = debt if k == n else pay - interest
        rows.append({"month": k, "principal": principal, "interest": interest, "total": principal + interest})
        debt -= principal
    assert debt == 0
    return rows


def base_amounts(items):
    """Сумма строк сметы по продуктам (кредитные продукты и гарантия)."""
    out = {}
    for i in items:
        if i["product"] in CREDIT | {"BANK_GUARANTEE"}:
            out[i["product"]] = out.get(i["product"], 0) + i["amount"]
    return out


def build_offer(kind, items, case, score_total, route, amounts, grace_on=True):
    """amounts — сумма по каждому продукту для этого предложения."""
    goals = {g["goalType"] for g in case["goalsData"]["goals"]}
    covers = {}
    for i in items:
        covers.setdefault(i["product"], []).append(i["id"])
    products, monthly, overpay = [], {}, 0
    for prod, amount in amounts.items():
        if amount <= 0:
            continue
        rt = rate(prod, score_total, route)
        if prod == "BANK_GUARANTEE":
            term = 12
            fee = rub(Decimal(amount) * Decimal(str(rt)) / 100 * term / 12)
            overpay += fee
            products.append({"product": prod, "amount": amount, "termMonths": term, "ratePercent": rt,
                             "monthlyPayment": 0, "coversItems": covers[prod], "fee": fee})
            continue
        term = CFG["TERM"][prod]
        grace = 0
        if grace_on and prod in ("INVESTMENT_LOAN", "CREDIT_LINE", "STARTER_LOAN") and (
                goals & {"NEW_LOCATION", "START_BUSINESS"}):
            grace = CFG["GRACE"]
        if prod == "OVERDRAFT":
            x = rub(Decimal(amount) * Decimal(str(rt)) / 1200)
            rows = [{"month": k, "total": x, "interest": x} for k in range(1, term + 1)]
            note = "проценты, если лимит выбран полностью"
        else:
            rows = schedule(amount, rt, term, grace)
            note = None
        for r_ in rows:
            monthly[r_["month"]] = monthly.get(r_["month"], 0) + r_["total"]
        overpay += sum(r_["interest"] for r_ in rows) if prod != "OVERDRAFT" else 0
        p = {"product": prod, "amount": amount, "termMonths": term, "ratePercent": rt,
             "monthlyPayment": max(r_["total"] for r_ in rows), "coversItems": covers[prod]}
        if grace:
            p["gracePeriodMonths"] = grace
        if note:
            p["note"] = note
        products.append(p)
    partner = [i for i in items if i["product"] == "PARTNER_SERVICE"]
    return {"kind": kind, "products": products, "totalAmount": sum(p["amount"] for p in products),
            "firstMonthsPayment": monthly.get(1, 0), "fullPayment": max(monthly.values()) if monthly else 0,
            "overpayment": overpay,
            "partner": [{"title": i["title"], "amount": i["amount"],
                         "withDiscount": rub(Decimal(i["amount"]) * (100 - CFG["PARTNER_DISCOUNT"]) / 100)} for i in partner]}


def scaled(amounts, pct):
    """Каждый продукт × pct%, вниз до 10 000 ₽; продукты, ставшие 0, выпадают."""
    out = {k: down(Fr(v * pct, 100)) for k, v in amounts.items()}
    return {k: v for k, v in out.items() if v > 0}


def payback(case, offer):
    okved = case["plannedOkved"] or None
    if not okved and case["hasBusiness"]:
        okved = json.loads((MOCK_DATA / "egrip.json").read_text(encoding="utf-8"))[case["inn"]]["okvedMain"]["code"]
    ind = rs.industry(okved) if okved else None
    if not ind or not ind.get("typicalBreakEvenMonths"):
        return None
    n = ind["typicalBreakEvenMonths"]
    bad = math.ceil(Fr(n * 3, 2))
    return {"good": math.ceil(Fr(n * 3, 4)), "normal": n, "bad": bad if bad <= 60 else None}


def offers_for(case, score_total, route):
    """Раздел 4 правил продуктов."""
    est, st = estimate(case)
    if est["missing"]:
        return est, None, f"INFO_REQUESTED: не хватает {est['missing']}"
    base = base_amounts(est["items"])
    main_amounts = dict(base)
    main = build_offer("MAIN", est["items"], case, score_total, route, main_amounts)
    reduced = False
    if st:
        R, E = st[1], st[2]
        safe = (R - E) / CFG["DSCR"]
        pct = 100
        while main["fullPayment"] > safe and pct > 10:
            pct -= 1
            main_amounts = scaled(base, pct)
            main = build_offer("MAIN", est["items"], case, score_total, route, main_amounts)
            reduced = True
        if main["fullPayment"] > safe:
            return est, None, "MANUAL_REVIEW: даже 10% сметы не проходит по безопасному платежу"
        start_smaller = main["fullPayment"] > Fr(4, 5) * R - E
    else:
        start_smaller = False
    main["termsChanged"] = reduced
    est["startSmallerSuggested"] = start_smaller
    out = [main]
    if start_smaller or reduced:
        sm = build_offer("SMALLER", est["items"], case, score_total, route, scaled(main_amounts, CFG["SMALLER_SHARE"]))
        sm["termsChanged"] = True
        out.append(sm)
    if any(p.get("gracePeriodMonths") for p in main["products"]) and len(out) < 3:
        alt = build_offer("ALTERNATIVE", est["items"], case, score_total, route, main_amounts, grace_on=False)
        alt["termsChanged"] = reduced
        out.append(alt)
    for o in out:
        o["paybackMonths"] = payback(case, o)
    return est, out, None


GOAL_TITLES = {"EQUIPMENT": "покупку оборудования", "NEW_LOCATION": "открытие новой точки", "INVENTORY": "закупку запасов",
               "CASH_GAP": "кассовый разрыв", "TENDER": "участие в тендере", "MARKETING": "рекламу",
               "START_BUSINESS": "запуск бизнеса", "OTHER": "другие цели"}
PRODUCT_TITLES = {"LEASING": "лизинг", "INVESTMENT_LOAN": "инвестиционный кредит", "CREDIT_LINE": "кредитная линия",
                  "OVERDRAFT": "овердрафт", "BANK_GUARANTEE": "банковская гарантия", "STARTER_LOAN": "стартовый кредит"}


def money(x):
    return f"{x:,}".replace(",", " ")


FIELD_RU = {"LAST_NAME": "фамилия", "FIRST_NAME": "имя", "MIDDLE_NAME": "отчество", "BIRTH_DATE": "дата рождения",
            "ISSUE_DATE": "дата выдачи"}

# Коды флагов (contract/scoring-clarifications.md, раздел 8): код → (корзина, текст для сотрудника)
FLAGS = {
    "PASSPORT_HOLDER_MISMATCH": ("MANUAL", "Паспортные данные не совпадают с записью о паспорте"),
    "PASSPORT_HOLDER_UNKNOWN": ("MANUAL", "Нет подтверждённой записи о владельце паспорта"),
    "EGRIP_NAME_MISMATCH": ("MANUAL", "ФИО в реестре ИП не совпадает с паспортом"),
    "EGRIP_ACTIVE_FOR_STARTUP": ("MANUAL", "Клиент указал, что бизнеса нет, но в реестре есть действующее ИП"),
    "INN_NOT_FOUND": ("MANUAL", "Личный ИНН не найден"),
    "TAX": ("MANUAL", "Налоговый долг больше 50 000 ₽ или данные устарели"),
    "TAX_DEBT_SMALL": ("MINUS", "Налоговый долг до 50 000 ₽"),
    "BKI_REPORT_STALE": ("MANUAL", "Кредитный отчёт старше 30 дней"),
    "BKI_CURRENT_OVERDUE": ("MANUAL", "Текущая просрочка по кредиту 1–89 дней"),
    "BKI_HISTORIC_OVERDUE_90": ("MANUAL", "Просрочка 90+ дней за последние 3 года"),
    "BKI_HISTORIC_OVERDUE": ("MINUS", "Просрочка до 90 дней за последние 3 года"),
    "FSSP_ACTIVE": ("MANUAL", "Есть действующее производство у приставов"),
    "BANKRUPTCY_PAST_LT_5Y": ("MANUAL", "Банкротство завершено менее 5 лет назад"),
    "BANKRUPTCY_CONFLICT": ("MANUAL", "Противоречивые данные о банкротстве"),
    "NO_VERIFIED_STATEMENT": ("MANUAL", "Нет выписки, только анкета"),
    "STATEMENT_INCOMPLETE": ("MANUAL", "Выписка подтверждает меньше 12 месяцев"),
    "OTHER_IN_OVER_20": ("MANUAL", "Больше 20% поступлений не подтверждены как выручка"),
    "NO_CONFIRMED_INCOME": ("MANUAL", "Нет подтверждённых поступлений"),
    "REVENUE_ZERO": ("MANUAL", "Нет подтверждённой выручки"),
    "TREND_PREV_ZERO": ("MANUAL", "Нельзя посчитать тренд: выручка за 3 месяца была нулевой"),
    "BUSINESS_YOUNGER_3_MONTHS": ("MANUAL", "ИП младше 3 месяцев"),
    "INDUSTRY_NOT_FOUND": ("MANUAL", "Отрасли нет в справочнике"),
    "INDUSTRY_DATA_MISSING": ("MANUAL", "Нет данных о росте или закрытиях в отрасли"),
}


def passport_mismatch(case):
    sys.path.insert(0, str(ROOT / "mocks"))
    import logic
    st, js = logic.route("POST", "/passport/check", case["passport"])
    return [FIELD_RU[f] for f in js.get("mismatchFields", [])] if st == 200 else []


def flags_for(res):
    out = []
    for code in res["manualReasons"]:
        basket, text = FLAGS[code]
        out.append({"code": code, "basket": basket, "text": text})
    bki = next(c for c in res["checks"] if c["source"] == "BKI")
    if bki["basket"] == "MINUS":
        out.append({"code": "BKI_HISTORIC_OVERDUE", "basket": "MINUS", "text": FLAGS["BKI_HISTORIC_OVERDUE"][1]})
    tax = next(c for c in res["checks"] if c["source"] == "FNS_TAX_DEBT")
    if tax["basket"] == "MINUS":
        out.append({"code": "TAX_DEBT_SMALL", "basket": "MINUS", "text": FLAGS["TAX_DEBT_SMALL"][1]})
    return out


def recommendation(case, res, offers):
    """Раздел 6 правил продуктов. Порядок строк таблицы = порядок проверки."""
    if res["statusAfterSubmit"] == "OFFER_READY":
        return {"action": "APPROVE", "text": "Одобрено автоматически"}
    reasons = set(res["manualReasons"])
    total = res["score"]["total"]
    if "PASSPORT_HOLDER_MISMATCH" in reasons:
        return {"action": "REQUEST_INFO", "text": "Уточните паспортные данные: не совпадает " + ", ".join(passport_mismatch(case))}
    if "PASSPORT_HOLDER_UNKNOWN" in reasons:
        return {"action": "REQUEST_INFO", "text": "Уточните паспортные данные: нет подтверждённой записи о паспорте"}
    if reasons & {"NO_VERIFIED_STATEMENT", "STATEMENT_INCOMPLETE"}:
        return {"action": "REQUEST_INFO", "text": "Попросите выписку за 12 месяцев"}
    if not case["hasBusiness"]:
        amount = answers(case).get("common.amount") or 0
        bki = json.loads((MOCK_DATA / "bki.json").read_text(encoding="utf-8"))[case["inn"]]
        if amount > rs.STARTUP_AUTO_APPROVE_LIMIT or not rs.good_bki(bki):
            return {"action": "CHANGE_TERMS", "text": "Предложите до 200 000 ₽ или запросите поручителя/залог"}
    else:
        reg = json.loads((MOCK_DATA / "egrip.json").read_text(encoding="utf-8"))[case["inn"]]["registrationDate"]
        young = rs.full_months(dt.date.fromisoformat(reg), rs.EVAL) < 12
        smaller = any(o["kind"] == "SMALLER" for o in offers or [])
        if young or (smaller and total < 80):
            return {"action": "CHANGE_TERMS", "text": "Предложите вариант «Начать меньше»"}
    if total >= 60:
        if reasons:
            why = "; ".join(FLAGS[c][1].lower() for c in sorted(reasons))
            return {"action": "APPROVE", "text": f"Риск приемлемый, проверьте: {why}"}
        return {"action": "APPROVE", "text": f"Риск приемлемый: {total} баллов из 100"}
    return {"action": "CHANGE_TERMS", "text": "Предложите вариант «Начать меньше»"}


# Отказ (product-rules-v1.md, раздел 6.2)
STOP_REJECTION = {
    "BANKRUPTCY_CURRENT": ("идёт процедура банкротства", ["Подайте заявку после завершения процедуры банкротства"], None),
    "PASSPORT_INVALID": ("паспорт недействителен", ["Подайте заявку по действующему паспорту"], None),
    "EGRIP_TERMINATED": ("ИП прекратил деятельность", ["Зарегистрируйте ИП заново или подайте заявку как новый бизнес"], None),
    "BKI_CURRENT_OVERDUE_90": ("есть текущая просрочка по кредиту больше 90 дней",
                               ["Погасите просроченный платёж", "Подайте заявку через 3 месяца без новых просрочек"], 3),
}
FACTOR_ADVICE = {
    "BUSINESS_STABILITY": "Выровняйте выручку: в нескольких месяцах она была заметно ниже обычной",
    "BUSINESS_REVENUE_TREND": "Вернитесь, когда выручка за 3 месяца перестанет снижаться",
    "BUSINESS_CASH_BUFFER": "Сократите расходы: сейчас после них почти ничего не остаётся",
    "BUSINESS_START_CREDIT_SEARCH": "Не подавайте много заявок на кредит одновременно",
    "BUSINESS_START_DEBT_LOAD": "Снизьте текущие платежи по кредитам",
    "BUSINESS_START_OPERATING_HISTORY": "Поработайте 6 месяцев и приходите с выпиской",
    "OWNER_OVERDUE_HISTORY": "Платите по кредитам без просрочек",
    "OWNER_BUSINESS_AGE": "Вернитесь позже: чем дольше работает ИП, тем выше шанс одобрения",
    "OWNER_TAX_DISCIPLINE": "Погасите налоговый долг",
    "IDEA_VERIFIED_DEBT_COVERAGE": "Снизьте нагрузку: свободных денег не хватает на текущие платежи по кредитам",
    "IDEA_VERIFIED_STRESS_BUFFER": "Создайте запас: падение выручки на 20% сейчас оставит бизнес без денег",
    "INDUSTRY_BASE_RISK": "Отрасль с высоким риском: попробуйте меньшую сумму или залог",
    "INDUSTRY_REVENUE_TREND": "Отрасль с высоким риском: попробуйте меньшую сумму или залог",
    "INDUSTRY_CLOSURE_RATE": "Отрасль с высоким риском: попробуйте меньшую сумму или залог",
}


def rejection(res):
    stop = next((c for c in res["checks"] if c["basket"] == "STOP"), None)
    if stop:
        why, advice, retry = STOP_REJECTION[stop["code"]]
        return {"text": f"Сейчас мы не можем одобрить заявку: {why}", "advice": advice, "retryAfterMonths": retry}
    factors = res["score"]["factors"]
    order = {f["code"]: i for i, f in enumerate(factors)}
    ranked = sorted((f for f in factors if f["points"] < f["maxPoints"]),
                    key=lambda f: (-(f["maxPoints"] - f["points"]), order[f["code"]]))
    advice = []
    for f in ranked:
        t = FACTOR_ADVICE[f["code"]]
        if t not in advice:
            advice.append(t)
        if len(advice) == 3:
            break
    return {"text": "Сейчас мы не можем одобрить заявку", "advice": advice, "retryAfterMonths": 3}


def months_word(n):
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return "месяц"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "месяца"
    return "месяцев"


def break_even(case):
    """contract/scoring-clarifications.md, раздел 6."""
    out = []
    for gi, g in enumerate(case["goalsData"]["goals"]):
        qid = {"START_BUSINESS": "start.breakEven", "NEW_LOCATION": "location.breakEven"}.get(g["goalType"])
        if not qid:
            continue
        v = next((a["value"] for a in g["answers"] if a["questionId"] == qid), None)
        okved = case["plannedOkved"] or (json.loads((MOCK_DATA / "egrip.json").read_text(encoding="utf-8"))
                                         [case["inn"]].get("okvedMain") or {}).get("code")
        ind = rs.industry(okved) if okved else None
        if not (isinstance(v, int) and v > 0 and ind and ind.get("typicalBreakEvenMonths")):
            continue
        d = v - ind["typicalBreakEvenMonths"]
        src = "синтетического отраслевого ориентира" if ind["sourceType"] == "SYNTHETIC" else "отраслевого ориентира"
        if d < 0:
            text = f"По прогнозу клиента окупаемость быстрее {src} на {-d} {months_word(d)}"
        elif d > 0:
            text = f"По прогнозу клиента окупаемость медленнее {src} на {d} {months_word(d)}"
        else:
            text = f"Прогноз клиента совпадает с {src.replace('синтетического отраслевого ориентира', 'синтетическим отраслевым ориентиром').replace('отраслевого ориентира', 'отраслевым ориентиром')}"
        out.append({"goalIndex": gi, "goalType": g["goalType"], "questionId": qid, "okvedCode": ind["okvedCode"],
                    "clientMonths": v, "industryMonths": ind["typicalBreakEvenMonths"], "differenceMonths": d,
                    "sourceType": ind["sourceType"], "dataAsOf": ind["dataAsOf"], "text": text})
    return out


def statement_summary(case):
    """StatementSummary по mocks-contract.md (окно, выручка, расходы) и product-rules-v1.md 3.1 (категории, покупатели)."""
    import csv, io
    text = (TESTS / case["statementFile"]).read_text(encoding="utf-8")
    sm, _ = rs.parse_statement(text, rs.EVAL)
    n = sm["monthsCovered"]
    rows = [r for r in csv.DictReader(io.StringIO(text), delimiter=";") if r["date"][:7] in sm["monthly"]]
    dates = sorted(r["date"] for r in rows)
    cats, cust, op_income = {}, {}, 0
    for r in rows:
        amt = int(r["amount"])
        if r["direction"] == "OUT":
            c = out_category(r["purpose"])
            cats[c] = cats.get(c, 0) + amt
        else:
            k = rs.classify_in(r["purpose"], r["counterpartyInn"])
            if k in ("CUSTOMER", "ACQUIRING"):
                op_income += amt
            if k == "CUSTOMER":
                key = r["counterpartyInn"].replace(" ", "")
                e = cust.setdefault(key, {"name": r["counterparty"], "inn": key, "sum": 0})
                e["sum"] += amt
    avg = lambda x: rub(Decimal(x) / Decimal(n))
    top = sorted(cust.values(), key=lambda e: (-e["sum"], e["inn"]))[:3]
    warnings = []
    for m in sm["window"]:
        if m not in sm["monthly"]:
            warnings.append(f"Нет операций за {m} — период не подтверждён")
    if n < 12:
        warnings.append(f"Выписка подтверждает {n} из 12 календарных месяцев")
    if sm["allIn"] == 0:
        warnings.append("Нет подтверждённых поступлений")
    elif sm["otherIn"] * 100 > sm["allIn"] * 20:
        warnings.append("Более 20% входящих операций не удалось подтвердить как выручку")
    return {"periodFrom": dates[0], "periodTo": dates[-1], "monthsCovered": n,
            "avgMonthlyIncome": avg(sum(m["income"] for m in sm["monthly"].values())),
            "avgMonthlyExpense": avg(sum(m["expense"] for m in sm["monthly"].values())),
            "monthly": [{"month": m, "income": v["income"], "expense": v["expense"]} for m, v in sm["monthly"].items()],
            "expenseByCategory": {k: avg(v) for k, v in sorted(cats.items())},
            "topCustomers": [{"name": e["name"], "inn": e["inn"],
                              "sharePercent": float((Decimal(e["sum"] * 100) / Decimal(op_income))
                                                    .quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))}
                             for e in top] if op_income else [],
            "otherBankLoanPaymentsMonthly": avg(cats.get("LOAN_PAYMENTS", 0)),
            "warnings": warnings}


def render_contract(case, est, offer, issue_date):
    tpl = json.loads((CONTRACT / "contract-clauses.json").read_text(encoding="utf-8"))
    prods = offer["products"]
    grace = max((p.get("gracePeriodMonths", 0) for p in prods), default=0)
    first = rs.add_months(issue_date, 1)
    if first.day > 28:
        first = first.replace(day=28)
    leasing = [i["title"] for i in est["items"] if i["product"] == "LEASING"]
    flags = {"always": True, "hasGrace": grace > 0, "noGrace": grace == 0, "hasLeasing": bool(leasing),
             "noLeasing": not leasing, "hasOverdraft": any(p["product"] == "OVERDRAFT" for p in prods),
             "hasGuarantee": any(p["product"] == "BANK_GUARANTEE" for p in prods)}
    od = next((p["amount"] for p in prods if p["product"] == "OVERDRAFT"), 0)
    gu = next((p for p in prods if p["product"] == "BANK_GUARANTEE"), None)
    v = {"totalAmount": money(offer["totalAmount"]),
         "goalsText": ", ".join(GOAL_TITLES[g["goalType"]] for g in case["goalsData"]["goals"]),
         "productsText": "; ".join(f"{PRODUCT_TITLES[p['product']]} {money(p['amount'])} ₽ под {p['ratePercent']:g}% на {p['termMonths']} мес."
                                   for p in prods),
         "maxTermMonths": max(p["termMonths"] for p in prods), "graceMonths": grace,
         "firstMonthsPayment": money(offer["firstMonthsPayment"]), "fullPayment": money(offer["fullPayment"]),
         "overpayment": money(offer["overpayment"]), "firstPaymentDate": first.strftime("%d.%m.%Y"),
         "paymentDay": first.day, "leasingItems": ", ".join(t[:1].lower() + t[1:] for t in leasing), "overdraftLimit": money(od),
         "guaranteeAmount": money(gu["amount"]) if gu else "", "guaranteeFee": money(gu["fee"]) if gu else "",
         "penaltyPercent": "0,1"}
    fill = lambda t: t.format(**v)
    clauses = [{"id": c["id"], "title": c["title"], "legalText": fill(c["legalText"]), "plainText": fill(c["plainText"]),
                "important": c["important"]} for c in tpl["clauses"] if flags[c["when"]]]
    summary = [fill(x["text"]) for x in tpl["summary"] if flags[x["when"]]]
    faq = [{"id": f["id"], "question": f["question"], "answer": fill(f["answer"])}
           for f in tpl["faq"] if flags[f.get("when", "always")]]
    assert len(summary) == 3
    return {"clauses": clauses, "summary": summary, "faq": [{"id": f["id"], "question": f["question"]} for f in faq],
            "faqAnswers": {f["id"]: f["answer"] for f in faq}}


def to_api_offer(o, idx):
    """Приводит к схеме Offer из openapi.yaml."""
    prods = []
    for p in o["products"]:
        q = {k: p[k] for k in ("product", "amount", "termMonths", "ratePercent", "monthlyPayment", "coversItems")}
        q["title"] = PRODUCT_TITLES[p["product"]].capitalize()
        for k in ("gracePeriodMonths", "fee", "note"):
            if k in p:
                q[k] = p[k]
        prods.append(q)
    return {"id": f"{o['kind'].lower()}", "kind": o["kind"], "termsChanged": o["termsChanged"], "products": prods,
            "totalAmount": o["totalAmount"], "firstMonthsPayment": o["firstMonthsPayment"], "fullPayment": o["fullPayment"],
            "overpayment": o["overpayment"], "paybackMonths": o["paybackMonths"],
            "partnerServices": [{"title": x["title"], "amount": x["amount"], "withDiscount": x["withDiscount"],
                                 "discountPercent": CFG["PARTNER_DISCOUNT"]} for x in o["partner"]],
            "whyItFits": o["whyItFits"]}


def why_it_fits(o, main, free):
    """product-rules-v1.md, раздел 4: по порядку, не больше 3."""
    out = []
    if o["kind"] == "SMALLER":
        out.append(f"Платёж на {money(main['fullPayment'] - o['fullPayment'])} ₽ меньше главного предложения")
    if o["kind"] == "ALTERNATIVE":
        out.append(f"Без отсрочки — переплата меньше на {money(main['overpayment'] - o['overpayment'])} ₽")
    if free:
        pct = rub(Decimal(o["fullPayment"] * 100) / Decimal(free.numerator) * Decimal(free.denominator))
        out.append(f"Платёж — {pct}% свободных денег вашего бизнеса")
    g = max((p.get("gracePeriodMonths", 0) for p in o["products"]), default=0)
    if g:
        out.append(f"Отсрочка {g} мес.: пока бизнес запускается, платите только проценты — {money(o['firstMonthsPayment'])} ₽")
    if any(p["product"] == "LEASING" for p in o["products"]):
        out.append("Оборудование в лизинге — не нужен залог")
    if o["partner"]:
        out.append(f"Реклама у партнёра банка со скидкой {CFG['PARTNER_DISCOUNT']}%")
    return out[:3]


KEYS = ("estimate", "offers", "offersRoute", "recommendation", "contractExample", "submitNote", "rejection",
        "breakEvenComparisons", "statementSummary")


def main():
    path = TESTS / "expected-results.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = {c["code"]: c for c in json.loads((TESTS / "cases.json").read_text(encoding="utf-8"))["cases"]}
    for res in data["results"]:
        for k in KEYS:
            res.pop(k, None)
        case = cases[res["code"]]
        if res["statusAfterConsent"] == "REJECTED":
            res["rejection"] = rejection(res)
        if not res["score"]:
            continue
        res["score"]["flags"] = flags_for(res)
        if case["statementFile"]:
            res["statementSummary"] = statement_summary(case)
        res["breakEvenComparisons"] = break_even(case)
        if res["statusAfterSubmit"] == "REJECTED":
            # Смету клиент видит до отправки; предложений при отказе нет
            est, _ = estimate(case)
            res["estimate"] = {"items": est["items"], "total": est["total"], "startSmallerSuggested": False}
            res["rejection"] = rejection(res)
            continue
        route = "AUTO" if res["statusAfterSubmit"] == "OFFER_READY" else "STAFF"
        est, offers, stop = offers_for(case, res["score"]["total"], route)
        res["estimate"] = {"items": est["items"], "total": est["total"],
                           "startSmallerSuggested": bool(est.get("startSmallerSuggested"))}
        free = None
        if case["statementFile"]:
            _, R, E, _ = expense_by_category(case)
            free = R - E if R - E > 0 else None
        for o in offers or []:
            o["whyItFits"] = why_it_fits(o, offers[0], free)
        res["offers"] = [to_api_offer(o, i) for i, o in enumerate(offers or [])]
        res["offersRoute"] = route
        if stop:
            res["submitNote"] = stop
        res["recommendation"] = recommendation(case, res, offers)
        if res["code"] == "T01":
            res["contractExample"] = render_contract(case, est, offers[0], rs.EVAL)
    data["productRules"] = "contract/product-rules-v1.md (утверждено 25.10.2026)"
    data["note"] = ("Посчитано эталонными скриптами tests/reference_scoring.py и tests/reference_offers.py. "
                    "Для MANUAL_REVIEW предложения посчитаны так, как если сотрудник нажмёт APPROVE (ставка +2 п.п.).")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for r in data["results"]:
        if r.get("offers") is not None:
            o = r["offers"][0] if r["offers"] else None
            print(f"{r['code']}: {r['recommendation']['action']:12} " + (
                f"MAIN {money(o['totalAmount'])} платёж {money(o['firstMonthsPayment'])}→{money(o['fullPayment'])}, предложений {len(r['offers'])}" if o else r.get("submitNote", "")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
