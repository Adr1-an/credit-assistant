"""Эталонный расчёт сметы, предложений и графика по «Правилам продуктов» v1 — для сверки.

ЭТО НЕ КОД БЭКЕНДА. Нужен, чтобы примеры в contract/docs/product-rules-v1.md
и ожидаемые результаты были посчитаны, а не вписаны руками.
Запуск из корня репозитория: python tests/reference_offers.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
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
    "DSCR": 1.3,
    "OVERDRAFT_SHARE": 0.30,
    "BUFFER_SHARE": 0.10,
    "SMALLER_SHARE": 0.60,
    "STAFF_MONTHS": 3,
    "RENT_MONTHS": 3,
    "SALARY_PER_EMPLOYEE": 60000,
    "MARKETING_DEFAULT_MONTHS": 3,
    "PARTNER_DISCOUNT": 20,
    "TENDER_EXECUTION_SHARE": 0.30,
    "STARTER_MAX": 1000000,
}
CREDIT = {"LEASING", "INVESTMENT_LOAN", "CREDIT_LINE", "OVERDRAFT", "STARTER_LOAN"}


def up(x):
    return int(math.ceil(x / CFG["ROUND"]) * CFG["ROUND"])


def down(x):
    return int(math.floor(x / CFG["ROUND"]) * CFG["ROUND"])


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
    R = sum(m["income"] for m in summary["monthly"].values()) / n
    E = sum(m["expense"] for m in summary["monthly"].values()) / n
    return {k: v / n for k, v in sums.items()}, R, E, n


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
    r = annual / 100 / 12
    rows, debt = [], P
    pay = None
    for k in range(1, n + 1):
        interest = round(debt * r)
        if k <= g:
            principal = 0
        else:
            if pay is None:
                m = n - g
                pay = round(P * r / (1 - (1 + r) ** -m))
            principal = debt if k == n else pay - interest
        rows.append({"month": k, "principal": principal, "interest": interest, "total": principal + interest})
        debt -= principal
    assert debt == 0
    return rows


def build_offer(kind, items, case, score_total, route, grace_on=True, share=1.0):
    goals = {g["goalType"] for g in case["goalsData"]["goals"]}
    by_product = {}
    for i in items:
        if i["product"] in CREDIT | {"BANK_GUARANTEE"}:
            by_product.setdefault(i["product"], []).append(i)
    products, monthly, overpay = [], {}, 0
    for prod, its in by_product.items():
        amount = down(sum(x["amount"] for x in its) * share) if share < 1 else sum(x["amount"] for x in its)
        if amount <= 0:
            continue
        rt = rate(prod, score_total, route)
        if prod == "BANK_GUARANTEE":
            term = 12
            fee = round(amount * rt / 100 * term / 12)
            overpay += fee
            products.append({"product": prod, "amount": amount, "termMonths": term, "ratePercent": rt,
                             "monthlyPayment": 0, "coversItems": [x["id"] for x in its], "fee": fee})
            continue
        term = CFG["TERM"][prod]
        grace = 0
        if grace_on and prod in ("INVESTMENT_LOAN", "CREDIT_LINE", "STARTER_LOAN") and (
                goals & {"NEW_LOCATION", "START_BUSINESS"}):
            grace = CFG["GRACE"]
        if prod == "OVERDRAFT":
            rows = [{"month": k, "total": round(amount * rt / 1200), "interest": round(amount * rt / 1200)} for k in range(1, term + 1)]
            note = "проценты, если лимит выбран полностью"
        else:
            rows = schedule(amount, rt, term, grace)
            note = None
        for r_ in rows:
            monthly[r_["month"]] = monthly.get(r_["month"], 0) + r_["total"]
        overpay += sum(r_["interest"] for r_ in rows) if prod != "OVERDRAFT" else 0
        p = {"product": prod, "amount": amount, "termMonths": term, "ratePercent": rt,
             "monthlyPayment": max(r_["total"] for r_ in rows), "coversItems": [x["id"] for x in its]}
        if grace:
            p["gracePeriodMonths"] = grace
        if note:
            p["note"] = note
        products.append(p)
    partner = [i for i in items if i["product"] == "PARTNER_SERVICE"]
    total = sum(p["amount"] for p in products)
    first = monthly.get(1, 0)
    full = max(monthly.values()) if monthly else 0
    return {"kind": kind, "products": products, "totalAmount": total, "firstMonthsPayment": first,
            "fullPayment": full, "overpayment": overpay,
            "partner": [{"title": i["title"], "amount": i["amount"],
                         "withDiscount": round(i["amount"] * (100 - CFG["PARTNER_DISCOUNT"]) / 100)} for i in partner]}


def payback(case, offer):
    okved = case["plannedOkved"] or None
    if not okved and case["hasBusiness"]:
        okved = json.loads((MOCK_DATA / "egrip.json").read_text(encoding="utf-8"))[case["inn"]]["okvedMain"]["code"]
    ind = rs.industry(okved) if okved else None
    if not ind or not ind.get("typicalBreakEvenMonths"):
        return None
    n = ind["typicalBreakEvenMonths"]
    bad = math.ceil(n * 1.5)
    return {"good": math.ceil(n * 0.75), "normal": n, "bad": bad if bad <= 60 else None}


def offers_for(case, score_total, route):
    est, st = estimate(case)
    if est["missing"]:
        return est, None, f"INFO_REQUESTED: не хватает {est['missing']}"
    main = build_offer("MAIN", est["items"], case, score_total, route)
    reduced = False
    if st:
        R, E = st[1], st[2]
        F = R - E
        safe = F / CFG["DSCR"]
        share = 1.0
        while main["fullPayment"] > safe and share > 0.1:
            share = round(share - 0.01, 2)
            main = build_offer("MAIN", est["items"], case, score_total, route, share=share)
            reduced = True
        if main["fullPayment"] > safe:
            return est, None, "MANUAL_REVIEW: даже 10% сметы не проходит по безопасному платежу"
        stress = 0.8 * R - E
        start_smaller = main["fullPayment"] > stress
    else:
        start_smaller = False
    main["termsChanged"] = reduced
    est["startSmallerSuggested"] = start_smaller
    out = [main]
    if start_smaller or reduced:
        sm = build_offer("SMALLER", est["items"], case, score_total, route,
                         share=CFG["SMALLER_SHARE"] * (main["totalAmount"] / est["total"] if reduced else 1))
        sm["termsChanged"] = True
        out.append(sm)
    if any(p.get("gracePeriodMonths") for p in main["products"]) and len(out) < 3:
        alt = build_offer("ALTERNATIVE", est["items"], case, score_total, route, grace_on=False,
                          share=main["totalAmount"] / est["total"] if reduced else 1.0)
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


def recommendation(case, res, offers):
    """Раздел 6 правил продуктов."""
    if res["statusAfterSubmit"] == "OFFER_READY":
        return {"action": "APPROVE", "text": "Одобрено автоматически"}
    reasons = set(res["manualReasons"])
    total = res["score"]["total"]
    if reasons & {"PASSPORT_HOLDER_MISMATCH", "PASSPORT_HOLDER_UNKNOWN"}:
        return {"action": "REQUEST_INFO", "text": "Уточните паспортные данные: они не совпадают с записью о паспорте"}
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
        why = ", ".join(sorted(reasons)) or "причину ручной проверки"
        return {"action": "APPROVE", "text": f"Риск приемлемый: проверьте {why}"}
    return {"action": "CHANGE_TERMS", "text": "Предложите вариант «Начать меньше»"}


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
            "whyItFits": why_it_fits(o)}


def why_it_fits(o):
    out = []
    g = max((p.get("gracePeriodMonths", 0) for p in o["products"]), default=0)
    if g:
        out.append(f"Отсрочка {g} мес.: пока бизнес запускается, платите только проценты — {money(o['firstMonthsPayment'])} ₽")
    if any(p["product"] == "LEASING" for p in o["products"]):
        out.append("Оборудование в лизинге — не нужен залог")
    if o["partner"]:
        out.append(f"Реклама у партнёра банка со скидкой {CFG['PARTNER_DISCOUNT']}%")
    if o["kind"] == "SMALLER":
        out.insert(0, "Если выручка упадёт на 20%, платёж всё равно по силам")
    if o["kind"] == "ALTERNATIVE":
        out.insert(0, "Без отсрочки — переплата меньше")
    return out[:3]


def main():
    path = TESTS / "expected-results.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = {c["code"]: c for c in json.loads((TESTS / "cases.json").read_text(encoding="utf-8"))["cases"]}
    for res in data["results"]:
        for k in ("estimate", "offers", "offersRoute", "recommendation", "contractExample", "submitNote"):
            res.pop(k, None)
        if not res["score"] or res["statusAfterSubmit"] == "REJECTED":
            continue
        case = cases[res["code"]]
        route = "AUTO" if res["statusAfterSubmit"] == "OFFER_READY" else "STAFF"
        est, offers, stop = offers_for(case, res["score"]["total"], route)
        res["estimate"] = {"items": est["items"], "total": est["total"],
                           "startSmallerSuggested": bool(est.get("startSmallerSuggested"))}
        res["offers"] = [to_api_offer(o, i) for i, o in enumerate(offers or [])]
        res["offersRoute"] = route
        if stop:
            res["submitNote"] = stop
        res["recommendation"] = recommendation(case, res, offers)
        if res["code"] == "T01":
            res["contractExample"] = render_contract(case, est, offers[0], rs.EVAL)
    data["productRules"] = "contract/docs/product-rules-v1.md (утверждено 25.10.2026)"
    data["note"] = ("Посчитано эталонными скриптами tests/reference_scoring.py и reference_offers.py. "
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
