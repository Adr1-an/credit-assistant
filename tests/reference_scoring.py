"""Эталонный расчёт по «Модели баллов» БА v1 (24.10.2026) — для сверки тестовых данных.

ЭТО НЕ КОД БЭКЕНДА. Бэк пишет свой расчёт; этот скрипт нужен, чтобы
tests/expected-results.json был посчитан по правилам, а не вписан руками.

Запуск из корня репозитория: python tests/reference_scoring.py
Читает tests/cases.json, получает ответы заглушек через mocks/logic.py,
считает проверки, факторы, зону и статус, пишет tests/expected-results.json
и сравнивает с таблицами из документа БА (раздел 9 и 10).
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
import sys
import unicodedata
from fractions import Fraction as F
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
CONTRACT = ROOT / "contract"
MOCK_DATA = ROOT / "mocks" / "data"
sys.path.insert(0, str(ROOT / "mocks"))
import logic  # noqa: E402

EVAL = dt.date(2026, 10, 24)
STARTUP_AUTO_APPROVE_LIMIT = 200000


# ---------------- даты ----------------

def add_months(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    last = [31, 29 if (y % 4 == 0 and y % 100 != 0) or y % 400 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return dt.date(y, m, min(d.day, last))


def full_months(start: dt.date, end: dt.date) -> int:
    n = 0
    while add_months(start, n + 1) <= end:
        n += 1
    return n


def window(eval_date: dt.date) -> list[str]:
    first = dt.date(eval_date.year, eval_date.month, 1)
    return [add_months(first, -i).strftime("%Y-%m") for i in range(12, 0, -1)]


# ---------------- выписка (mocks-contract.md) ----------------
EXCL = ["возврат", "сторно", "отмена операции", "refund", "reversal", "возврат налога", "возмещение налога",
        "зачисление кредита", "выдача кредита", "кредитные средства", "заем", "займ", "договор займа",
        "перевод собственных средств", "перевод между своими счетами", "перевод между счетами",
        "внутренний перевод", "пополнение счета", "внесение наличных", "взнос наличных", "депозит", "вклад",
        "субсидия", "грант", "страховое возмещение", "продажа основных средств", "продажа оборудования",
        "возврат займа"]
ACQ = ["эквайринг", "acquiring", "реестр операций по картам", "выплаты по операциям с картами",
       "зачисление по операциям с картами", "возмещение по операциям с картами", "сбп оплата товаров",
       "сбп оплата услуг"]
CUST = ["оплата по договору", "оплата по счету", "оплата за", "оплата товара", "оплата товаров", "оплата услуг",
        "оплата работ", "аванс по договору", "предоплата по договору", "выручка от реализации",
        "поступление от покупателя", "платеж покупателя", "оплата по заказу"]


def norm_purpose(s: str) -> str:
    s = (s or "").casefold().replace("ё", "е")
    s = re.sub(r"[^а-яa-z0-9]+", " ", s)
    return " ".join(s.split())


def has_phrase(text: str, phrases) -> bool:
    t = f" {text} "
    return any(f" {p} " in t for p in phrases)


def classify_in(purpose: str, cinn: str) -> str:
    p = norm_purpose(purpose)
    if has_phrase(p, EXCL):
        return "OTHER_IN"
    if has_phrase(p, ACQ):
        return "ACQUIRING"
    digits = (cinn or "").replace(" ", "")
    if has_phrase(p, CUST) and digits.isdigit() and len(digits) in (10, 12):
        return "CUSTOMER"
    return "OTHER_IN"


HEADERS = {"date", "amount", "direction", "counterparty", "counterpartyInn", "purpose"}


def parse_statement(text: str, eval_date: dt.date):
    """Возвращает summary или ('STATEMENT_UNREADABLE', причина)."""
    text = text.lstrip("﻿")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    if reader.fieldnames is None or set(reader.fieldnames) != HEADERS:
        return None, "колонки не совпадают"
    win = window(eval_date)
    months = {}
    all_in = other_in = 0
    for row in reader:
        if not any((v or "").strip() for v in row.values()):
            continue
        try:
            d = dt.date.fromisoformat(row["date"])
        except ValueError:
            return None, "дата"
        if not re.fullmatch(r"[1-9][0-9]*", row["amount"] or ""):
            return None, "сумма"
        if row["direction"] not in ("IN", "OUT"):
            return None, "направление"
        if d > eval_date:
            return None, "дата в будущем"
        ym = d.strftime("%Y-%m")
        if ym not in win:
            continue
        amt = int(row["amount"])
        mrec = months.setdefault(ym, {"income": 0, "expense": 0})
        if row["direction"] == "IN":
            all_in += amt
            cat = classify_in(row["purpose"], row["counterpartyInn"])
            if cat == "OTHER_IN":
                other_in += amt
            else:
                mrec["income"] += amt
        else:
            mrec["expense"] += amt
    if not months:
        return None, "нет операций в окне"
    present = [m for m in win if m in months]
    return {"window": win, "present": present, "monthly": {m: months[m] for m in present},
            "monthsCovered": len(present), "allIn": all_in, "otherIn": other_in}, None


# ---------------- проверки ----------------

def check(source, state, basket, code=None):
    return {"source": source, "state": state, "basket": basket, "code": code}


def run_checks(case):
    p, inn, has_b = case["passport"], case["inn"], case["hasBusiness"]
    resp, checks, manual, stop = {}, [], [], []

    def call(source, method, path, body=None):
        st, js = logic.route(method, path, body)
        resp[source] = (st, js)
        return st, js

    # Паспорт
    st, js = call("PASSPORT", "POST", "/passport/check", p)
    if st == 503:
        checks.append(check("PASSPORT", "ERROR", "NONE", "PASSPORT_CHECK_UNAVAILABLE"))
    elif st == 404:
        checks.append(check("PASSPORT", "WARNING", "MANUAL", "PASSPORT_HOLDER_UNKNOWN")); manual.append("PASSPORT_HOLDER_UNKNOWN")
    elif not js["valid"]:
        checks.append(check("PASSPORT", "FAIL", "STOP", "PASSPORT_INVALID")); stop.append("PASSPORT_INVALID")
    elif js["holderMatch"] is True:
        checks.append(check("PASSPORT", "OK", "NONE", "PASSPORT_VALID"))
    elif js["holderMatch"] is False:
        checks.append(check("PASSPORT", "WARNING", "MANUAL", "PASSPORT_HOLDER_MISMATCH")); manual.append("PASSPORT_HOLDER_MISMATCH")
    else:
        checks.append(check("PASSPORT", "WARNING", "MANUAL", "PASSPORT_HOLDER_UNKNOWN")); manual.append("PASSPORT_HOLDER_UNKNOWN")

    # ЕГРИП
    st, js = call("FNS_EGRIP", "GET", f"/fns/egrip/{inn}")
    if st == 503:
        checks.append(check("FNS_EGRIP", "ERROR", "NONE"))
    elif has_b:
        if st != 200:
            checks.append(check("FNS_EGRIP", "FAIL", "NONE", js["code"]))  # 422 → DRAFT, в тестах нет
        elif js["status"] != "ACTIVE":
            checks.append(check("FNS_EGRIP", "FAIL", "STOP", "EGRIP_TERMINATED")); stop.append("EGRIP_TERMINATED")
        else:
            name_ok = logic.norm_name(js["fullName"]) == logic.norm_name(
                " ".join(x for x in (p["lastName"], p["firstName"], p.get("middleName")) if x))
            if name_ok:
                checks.append(check("FNS_EGRIP", "OK", "NONE"))
            else:
                checks.append(check("FNS_EGRIP", "WARNING", "MANUAL", "EGRIP_NAME_MISMATCH")); manual.append("EGRIP_NAME_MISMATCH")
    else:
        if st == 404 and js["code"] == "NOT_IP":
            checks.append(check("FNS_EGRIP", "OK", "NONE"))
        elif st == 200 and js["status"] == "TERMINATED":
            checks.append(check("FNS_EGRIP", "OK", "NONE"))
        elif st == 200:
            checks.append(check("FNS_EGRIP", "WARNING", "MANUAL", "EGRIP_ACTIVE_FOR_STARTUP")); manual.append("EGRIP_ACTIVE_FOR_STARTUP")
        else:
            checks.append(check("FNS_EGRIP", "WARNING", "MANUAL", "INN_NOT_FOUND")); manual.append("INN_NOT_FOUND")

    # Налоги
    st, js = call("FNS_TAX_DEBT", "GET", f"/fns/tax-debt/{inn}")
    if st == 503:
        checks.append(check("FNS_TAX_DEBT", "ERROR", "NONE"))
    else:
        old = (EVAL - dt.date.fromisoformat(js["asOf"])).days > 30
        conflict = js["hasDebt"] != (js["debtAmount"] > 0)
        if old or conflict or js["debtAmount"] > 50000:
            checks.append(check("FNS_TAX_DEBT", "WARNING", "MANUAL")); manual.append("TAX")
        elif js["debtAmount"] > 0:
            checks.append(check("FNS_TAX_DEBT", "WARNING", "MINUS"))
        else:
            checks.append(check("FNS_TAX_DEBT", "OK", "NONE"))

    # БКИ
    st, js = call("BKI", "POST", "/bki/report", {"passport": p, "inn": inn})
    if st == 503:
        checks.append(check("BKI", "ERROR", "NONE", "BKI_UNAVAILABLE"))
    else:
        b = bki_eval(js)
        if b["stop"]:
            checks.append(check("BKI", "FAIL", "STOP", "BKI_CURRENT_OVERDUE_90")); stop.append("BKI_CURRENT_OVERDUE_90")
        elif b["manual"]:
            checks.append(check("BKI", "WARNING", "MANUAL", b["manual"])); manual.append(b["manual"])
        elif b["histDays"] > 0:
            checks.append(check("BKI", "WARNING", "MINUS"))
        else:
            checks.append(check("BKI", "OK", "NONE"))

    # ФССП
    st, js = call("FSSP", "POST", "/fssp/search", {k: p.get(k) for k in ("lastName", "firstName", "middleName", "birthDate")})
    if st == 503:
        checks.append(check("FSSP", "ERROR", "NONE"))
    elif any(x["status"] == "ACTIVE" for x in js["proceedings"]):
        checks.append(check("FSSP", "WARNING", "MANUAL", "FSSP_ACTIVE")); manual.append("FSSP_ACTIVE")
    else:
        checks.append(check("FSSP", "OK", "NONE"))

    # Банкротство
    st, js = call("BANKRUPTCY", "GET", f"/bankruptcy/{inn}")
    if st == 503:
        checks.append(check("BANKRUPTCY", "ERROR", "NONE"))
    elif js["inProcedure"]:
        checks.append(check("BANKRUPTCY", "FAIL", "STOP", "BANKRUPTCY_CURRENT")); stop.append("BANKRUPTCY_CURRENT")
    elif js["stage"] == "COMPLETED":
        c = js["completedAt"]
        if not c or dt.date.fromisoformat(c) > EVAL:
            checks.append(check("BANKRUPTCY", "WARNING", "MANUAL", "BANKRUPTCY_CONFLICT")); manual.append("BANKRUPTCY_CONFLICT")
        elif EVAL < add_months(dt.date.fromisoformat(c), 60):
            checks.append(check("BANKRUPTCY", "WARNING", "MANUAL", "BANKRUPTCY_PAST_LT_5Y")); manual.append("BANKRUPTCY_PAST_LT_5Y")
        else:
            checks.append(check("BANKRUPTCY", "OK", "NONE"))
    else:
        checks.append(check("BANKRUPTCY", "OK", "NONE"))

    errors = [c for c in checks if c["state"] == "ERROR"]
    return checks, resp, manual, stop, errors


def bki_eval(js):
    out = {"stop": False, "manual": None, "histDays": 0, "fresh": True}
    asof = dt.date.fromisoformat(js["reportAsOf"])
    if asof > EVAL or (EVAL - asof).days > 30:
        out["fresh"] = False
        out["manual"] = "BKI_REPORT_STALE"
        return out
    active = [l for l in js["loans"] if l["status"] == "ACTIVE"]
    cur = max((l["currentOverdueDays"] for l in active), default=0)
    if cur >= 90:
        out["stop"] = True
        return out
    if cur >= 1:
        out["manual"] = "BKI_CURRENT_OVERDUE"
        out["cur"] = cur
        return out
    since = add_months(EVAL, -36)
    hist = [o["days"] for l in js["loans"] for o in l["overdues"] if dt.date.fromisoformat(o["date"]) >= since]
    out["histDays"] = max(hist, default=0)
    if out["histDays"] >= 90:
        out["manual"] = "BKI_HISTORIC_OVERDUE_90"
    return out


# ---------------- факторы ----------------

def f(code, block, points, max_points):
    return {"code": code, "block": block, "points": points, "maxPoints": max_points}


def scale(v, rules, default=0):
    for cond, pts in rules:
        if cond(v):
            return pts
    return default


def score_case(case, resp, manual):
    has_b = case["hasBusiness"]
    eg_st, eg = resp["FNS_EGRIP"]
    bki = resp["BKI"][1]
    tax = resp["FNS_TAX_DEBT"][1]
    factors = []
    flags = []

    age = full_months(dt.date.fromisoformat(eg["registrationDate"]), EVAL) if has_b else None
    startup_block = (not has_b) or age < 3

    # Выписка
    summary = None
    if case["statementFile"]:
        summary, why = parse_statement((TESTS / case["statementFile"]).read_text(encoding="utf-8"), EVAL)
        assert summary, why
    n = summary["monthsCovered"] if summary else 0
    R = E = None
    if summary:
        R = F(sum(m["income"] for m in summary["monthly"].values()), n)
        E = F(sum(m["expense"] for m in summary["monthly"].values()), n)
        if summary["allIn"] == 0:
            manual.append("NO_CONFIRMED_INCOME")
        elif summary["otherIn"] * 100 > summary["allIn"] * 20:
            manual.append("OTHER_IN_OVER_20")
        if n < 12:
            manual.append("STATEMENT_INCOMPLETE")
    elif has_b:
        manual.append("NO_VERIFIED_STATEMENT")

    active = [l for l in bki["loans"] if l["status"] == "ACTIVE"]
    L = sum(l["monthlyPayment"] for l in active)

    # BUSINESS
    if startup_block:
        req = bki["requestsLast30Days"]
        factors.append(f("BUSINESS_START_CREDIT_SEARCH", "BUSINESS",
                         scale(req, [(lambda v: v <= 1, 10), (lambda v: v <= 3, 5)]), 10))
        factors.append(f("BUSINESS_START_DEBT_LOAD", "BUSINESS",
                         scale(L, [(lambda v: v == 0, 10), (lambda v: v <= 20000, 7), (lambda v: v <= 50000, 4)]), 15))
        factors.append(f("BUSINESS_START_OPERATING_HISTORY", "BUSINESS", 0, 15))
        if has_b:
            manual.append("BUSINESS_YOUNGER_3_MONTHS")
    else:
        stab = trend = buf = 0
        if summary and n >= 6:
            if R > 0:
                weak = sum(1 for m in summary["monthly"].values() if m["income"] < F(7, 10) * R)
                stab = scale(weak, [(lambda v: v == 0, 15), (lambda v: v <= 2, 10), (lambda v: v <= 4, 5)])
                pct = (R - E) / R * 100
                buf = scale(pct, [(lambda v: v >= 25, 15), (lambda v: v >= 15, 10), (lambda v: v >= 5, 5)])
            else:
                manual.append("REVENUE_ZERO")
            last6 = summary["window"][-6:]
            if all(m in summary["monthly"] for m in last6):
                prev = sum(summary["monthly"][m]["income"] for m in last6[:3])
                last = sum(summary["monthly"][m]["income"] for m in last6[3:])
                if prev == 0:
                    manual.append("TREND_PREV_ZERO")
                else:
                    t = (F(last, prev) - 1) * 100
                    trend = scale(t, [(lambda v: v >= 10, 10), (lambda v: v >= -10, 7), (lambda v: v >= -25, 3)])
        factors += [f("BUSINESS_STABILITY", "BUSINESS", stab, 15), f("BUSINESS_REVENUE_TREND", "BUSINESS", trend, 10),
                    f("BUSINESS_CASH_BUFFER", "BUSINESS", buf, 15)]

    # OWNER
    b = bki_eval(bki)
    if not b["fresh"] or b.get("cur"):
        od = 0
    elif not bki["loans"]:
        od = 12
    else:
        d = b["histDays"]
        od = scale(d, [(lambda v: v == 0, 20), (lambda v: v <= 29, 15), (lambda v: v <= 59, 8), (lambda v: v <= 89, 3)])
    factors.append(f("OWNER_OVERDUE_HISTORY", "OWNER", od, 20))
    ba = 0 if not has_b else scale(age, [(lambda v: v >= 36, 6), (lambda v: v >= 12, 4), (lambda v: v >= 3, 2)])
    factors.append(f("OWNER_BUSINESS_AGE", "OWNER", ba, 6))
    debt = tax["debtAmount"]
    tx = 4 if (not tax["hasDebt"] and debt == 0) else (2 if 1 <= debt <= 50000 else 0)
    if "TAX" in manual:
        tx = 0
    factors.append(f("OWNER_TAX_DISCIPLINE", "OWNER", tx, 4))

    # IDEA
    cov = stress = 0
    if summary and n >= 6 and R and R > 0 and not startup_block:
        Fv = R - E
        if L == 0:
            cov = 10 if Fv > 0 else 0
        else:
            r = Fv / L
            cov = scale(r, [(lambda v: v >= 2, 10), (lambda v: v >= 1, 7), (lambda v: v >= F(1, 2), 3)])
        T = (F(8, 10) * R - E) / R * 100
        stress = scale(T, [(lambda v: v >= 10, 10), (lambda v: v >= 5, 7), (lambda v: v >= 0, 3)])
    factors += [f("IDEA_VERIFIED_DEBT_COVERAGE", "IDEA", cov, 10), f("IDEA_VERIFIED_STRESS_BUFFER", "IDEA", stress, 10)]

    # INDUSTRY
    okved = eg["okvedMain"]["code"] if has_b else case["plannedOkved"]
    ind = industry(okved)
    if ind is None:
        manual.append("INDUSTRY_NOT_FOUND")
        factors += [f("INDUSTRY_BASE_RISK", "INDUSTRY", 0, 4), f("INDUSTRY_REVENUE_TREND", "INDUSTRY", 0, 3),
                    f("INDUSTRY_CLOSURE_RATE", "INDUSTRY", 0, 3)]
    else:
        g, cl = ind["growthYoYPercent"], ind["closureSharePercent"]
        if g is None or cl is None:
            manual.append("INDUSTRY_DATA_MISSING")
        factors.append(f("INDUSTRY_BASE_RISK", "INDUSTRY", {"LOW": 4, "MEDIUM": 2, "HIGH": 0}[ind["riskTier"]], 4))
        factors.append(f("INDUSTRY_REVENUE_TREND", "INDUSTRY", 0 if g is None else scale(
            g, [(lambda v: v >= 5, 3), (lambda v: v >= -5, 2), (lambda v: v >= -15, 1)]), 3))
        factors.append(f("INDUSTRY_CLOSURE_RATE", "INDUSTRY", 0 if cl is None else scale(
            cl, [(lambda v: v < 5, 3), (lambda v: v < 10, 2), (lambda v: v < 20, 1)]), 3))

    assert sum(x["maxPoints"] for x in factors) == 100
    total = sum(x["points"] for x in factors)

    # Маршрут (раздел 11 модели)
    if not has_b:
        amount = next((a["value"] for a in case["goalsData"]["commonAnswers"] if a["questionId"] == "common.amount"), None)
        auto = (not manual and good_bki(bki) and isinstance(amount, int) and 1 <= amount <= STARTUP_AUTO_APPROVE_LIMIT
                and tax["debtAmount"] == 0 and ind is not None)
        zone = "GREEN" if auto else "YELLOW"
    elif manual or n < 12 or age < 12:
        zone = "YELLOW"
    elif total < 40:
        zone = "RED"
    elif total >= 80:
        zone = "GREEN"
    else:
        zone = "YELLOW"
    blocks = {k: sum(x["points"] for x in factors if x["block"] == k) for k in ("BUSINESS", "OWNER", "IDEA", "INDUSTRY")}
    return {"total": total, "zone": zone, "blocks": blocks, "factors": factors, "manualReasons": sorted(set(manual))}


def good_bki(bki):
    if not bki_eval(bki)["fresh"] or not bki["loans"] or bki["requestsLast30Days"] > 1:
        return False
    since12, since36 = add_months(EVAL, -12), add_months(EVAL, -36)
    if not any(dt.date.fromisoformat(l["openedAt"]) <= since12 for l in bki["loans"]):
        return False
    active = [l for l in bki["loans"] if l["status"] == "ACTIVE"]
    if any(l["currentOverdueDays"] != 0 for l in active):
        return False
    if any(o["days"] > 0 and dt.date.fromisoformat(o["date"]) >= since36 for l in bki["loans"] for o in l["overdues"]):
        return False
    return sum(l["monthlyPayment"] for l in active) <= 20000


_IND = None


def industry(code):
    global _IND
    if _IND is None:
        _IND = {i["okvedCode"]: i for i in json.loads((CONTRACT / "industries.json").read_text(encoding="utf-8"))["industries"]}
    if code in _IND:
        return _IND[code]
    g = _IND.get(code.split(".")[0])
    return g if g and g["scope"] == "RUSSIA_OKVED_2DIGIT" else None


# ---------------- запуск ----------------

# Таблицы из документа БА: (BUSINESS, OWNER, IDEA, INDUSTRY, итог, зона, статус); None — Score нет
BA = {
    "T01": (37, 30, 17, 10, 94, "GREEN", "OFFER_READY"),
    "T02": (32, 13, 13, 6, 64, "YELLOW", "MANUAL_REVIEW"),
    "T03": (0, 30, 0, 2, 32, "RED", "REJECTED"),
    "T04": (None, "REJECTED"),
    "T05": (20, 24, 0, 7, 51, "GREEN", "OFFER_READY"),
    "T06": (20, 16, 0, 7, 43, "YELLOW", "MANUAL_REVIEW"),
    "T07": (0, 30, 0, 6, 36, "YELLOW", "MANUAL_REVIEW"),
    "T08": (37, 30, 17, 10, 94, "YELLOW", "MANUAL_REVIEW"),
    "T09": (37, 30, 17, 10, 94, "YELLOW", "MANUAL_REVIEW"),
    "T10": (None, "CHECKING"),
    "E01": (20, 16, 0, 6, 42, "YELLOW", "MANUAL_REVIEW"),
    "E02": (27, 18, 10, 2, 57, "YELLOW", "MANUAL_REVIEW"),
    "E03": (0, 26, 0, 6, 32, "YELLOW", "MANUAL_REVIEW"),
    # E04–E06 — следствия правил модели (февраль пропущен, граница 5 лет), в таблицах БА без отдельной строки
    "E04": (37, 30, 17, 10, 94, "YELLOW", "MANUAL_REVIEW"),
    "E05": (37, 30, 17, 10, 94, "GREEN", "OFFER_READY"),
    "E06": (37, 30, 17, 10, 94, "YELLOW", "MANUAL_REVIEW"),
}

ZONE_STATUS = {"GREEN": "OFFER_READY", "YELLOW": "MANUAL_REVIEW", "RED": "REJECTED"}


def main():
    cases = json.loads((TESTS / "cases.json").read_text(encoding="utf-8"))
    results, problems = [], []
    for case in cases["cases"]:
        checks, resp, manual, stop, errors = run_checks(case)
        if errors:
            after_consent, score, final = "CHECKING", None, "CHECKING"
        elif stop:
            after_consent, score, final = "REJECTED", None, "REJECTED"
        else:
            after_consent = "COLLECTING"
            score = score_case(case, resp, manual)
            final = ZONE_STATUS[score["zone"]]
        res = {"code": case["code"], "scenario": case["scenario"], "inn": case["inn"],
               "checks": checks, "statusAfterConsent": after_consent,
               "score": None if score is None else {k: score[k] for k in ("total", "zone", "blocks", "factors")},
               "manualReasons": None if score is None else score["manualReasons"],
               "statusAfterSubmit": None if score is None else final}
        if errors:
            res["nextActionAfterConsent"] = "RETRY_CHECKS"
        results.append(res)

        exp = BA[case["code"]]
        if exp[0] is None:
            got = (None, final)
        else:
            bl = score["blocks"]
            got = (bl["BUSINESS"], bl["OWNER"], bl["IDEA"], bl["INDUSTRY"], score["total"], score["zone"], final)
        mark = "OK " if got == exp else "РАСХОЖДЕНИЕ"
        if got != exp:
            problems.append((case["code"], exp, got))
        print(f"{mark} {case['code']}: {got}")

    out = {"version": "1.0", "evaluationDate": EVAL.isoformat(),
           "model": "Модель баллов БА v1 от 24.10.2026 (contract/scoring-model-v1.docx)",
           "note": "Посчитано эталонным скриптом tests/reference_scoring.py по данным заглушек. Входные данные — tests/cases.json.",
           "results": results}
    (TESTS / "expected-results.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if problems:
        print("\nРасхождения с документом БА:", *problems, sep="\n")
        return 1
    print("\nВсе результаты совпали с документом БА.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
