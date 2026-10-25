"""Шаг 10. Договор с пояснениями — product-rules-v1.md, раздел 7 + шаблоны contract-clauses.json.

Демонстрационный договор, не юридический документ. Пункты выбираются по признакам предложения
(есть отсрочка / лизинг / овердрафт / гарантия), в {плейсхолдеры} подставляются цифры.
Готовые ответы FAQ храним рядом (faqAnswers) — для /contract/ask без ИИ.
"""
from __future__ import annotations

import datetime as dt

from .. import refdata, texts
from ..clock import add_months
from ..config import get_settings
from .goals import goal_types
from .offers import PRODUCT_TITLES, money


def first_payment_date(issue_date: dt.date) -> dt.date:
    """Первый платёж — через месяц после выдачи, то же число; если число больше 28 — 28-е."""
    first = add_months(issue_date, 1)
    cap = get_settings().PAYMENT_DAY_MAX
    return first.replace(day=cap) if first.day > cap else first


def render_contract(app_id: str, offer: dict, estimate: dict | None, goals: dict | None,
                    issue_date: dt.date) -> dict:
    s = get_settings()
    tpl = refdata.contract_clauses()
    prods = offer["products"]
    grace = max((p.get("gracePeriodMonths", 0) for p in prods), default=0)
    first = first_payment_date(issue_date)
    covered = {i for p in prods if p["product"] == "LEASING" for i in p.get("coversItems", [])}
    leasing = [i["title"] for i in (estimate or {}).get("items", []) if i["id"] in covered]
    flags = {"always": True, "hasGrace": grace > 0, "noGrace": grace == 0, "hasLeasing": bool(leasing),
             "noLeasing": not leasing, "hasOverdraft": any(p["product"] == "OVERDRAFT" for p in prods),
             "hasGuarantee": any(p["product"] == "BANK_GUARANTEE" for p in prods)}
    od = next((p["amount"] for p in prods if p["product"] == "OVERDRAFT"), 0)
    gu = next((p for p in prods if p["product"] == "BANK_GUARANTEE"), None)
    goals_text = ", ".join(texts.GOAL_TITLES[g] for g in goal_types(goals)) or "развитие бизнеса"
    values = {
        "contractNumber": f"НВ-{issue_date.year}-{app_id[:8]}",
        "totalAmount": money(offer["totalAmount"]),
        "goalsText": goals_text,
        "productsText": "; ".join(f"{PRODUCT_TITLES[p['product']]} {money(p['amount'])} ₽ под {p['ratePercent']:g}% "
                                  f"на {p['termMonths']} мес." for p in prods),
        "maxTermMonths": max(p["termMonths"] for p in prods),
        "graceMonths": grace,
        "firstMonthsPayment": money(offer["firstMonthsPayment"]),
        "fullPayment": money(offer["fullPayment"]),
        "overpayment": money(offer["overpayment"]),
        "firstPaymentDate": first.strftime("%d.%m.%Y"),
        "paymentDay": first.day,
        "leasingItems": ", ".join(t[:1].lower() + t[1:] for t in leasing),
        "overdraftLimit": money(od),
        "guaranteeAmount": money(gu["amount"]) if gu else "",
        "guaranteeFee": money(gu["fee"]) if gu else "",
        "penaltyPercent": s.PENALTY_PERCENT_PER_DAY,
    }

    def fill(t: str) -> str:
        return t.format(**values)

    clauses = [{"id": c["id"], "title": c["title"], "legalText": fill(c["legalText"]),
                "plainText": fill(c["plainText"]), "important": c["important"]}
               for c in tpl["clauses"] if flags[c["when"]]]
    summary = [fill(x["text"]) for x in tpl["summary"] if flags[x["when"]]]
    faq = [f for f in tpl["faq"] if flags[f.get("when", "always")]]
    return {
        "clauses": clauses,
        "summary": summary,
        "faq": [{"id": f["id"], "question": f["question"]} for f in faq],
        "faqAnswers": {f["id"]: fill(f["answer"]) for f in faq},   # служебное, наружу не уходит
        "firstPaymentDate": first.isoformat(),                      # служебное, для графика
    }
