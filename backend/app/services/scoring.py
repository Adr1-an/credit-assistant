"""Шаг 8. Модель баллов — contract/scoring-model-v1.md (утверждена).

11 факторов: BUSINESS 40 + OWNER 30 + IDEA 20 + INDUSTRY 10 = 100.
У стартапа и ИП младше 3 месяцев вместо трёх BUSINESS_* — три BUSINESS_START_*.

Источники — только проверенные данные: выписка (по детерминированным правилам), БКИ, ЕГРИП,
налоги, отраслевой справочник. Слова клиента, анкета, смета, прогноз окупаемости — НЕ влияют на баллы.
ИИ здесь не участвует вообще.

Зона (раздел 5 и псевдокод раздела 11):
- стартап: GREEN только если нет MANUAL, GOOD_BKI и 1 ≤ common.amount ≤ STARTUP_AUTO_APPROVE_LIMIT;
- ИП: есть MANUAL, < 12 месяцев выписки или ИП моложе 12 месяцев → YELLOW;
  иначе total < 40 → RED, total ≥ 80 → GREEN, остальное YELLOW.
Доли считаем точными дробями (Fraction), границы сравниваем точно.
"""
from __future__ import annotations

import datetime as dt
from fractions import Fraction

from .. import refdata, texts
from ..clock import add_months, full_months, parse_date
from ..config import SCORING, get_settings
from .checks import bki_facts, bki_valid
from .goals import answers_map, requested_amount
from .statement import avg_expense, avg_income

BLOCKS = ("BUSINESS", "OWNER", "IDEA", "INDUSTRY")


def _ge(value, scale):
    for threshold, pts in scale:
        if value >= Fraction(threshold):
            return pts
    return 0


def _le(value, scale):
    for threshold, pts in scale:
        if value <= threshold:
            return pts
    return 0


def _lt(value, scale):
    for threshold, pts in scale:
        if value < threshold:
            return pts
    return 0


def _pct(x: Fraction) -> str:
    """Процент для текста: ROUND_HALF_UP до 1 знака (на баллы не влияет)."""
    from .statement import round_half_up
    v = round_half_up(x, 1)
    return f"{v:g}".replace(".", ",")


def factor(code: str, block: str, points: int, max_points: int, text: str) -> dict:
    lost = max_points - points
    return {"code": code, "block": block, "points": points, "maxPoints": max_points,
            "reason": f"{'−' + str(lost) if lost else '0'}: {text}"}


def okved_for(has_business: bool, check_data: dict, goals: dict | None) -> str | None:
    """Для ИП — okvedMain из ЕГРИП, для стартапа — подтверждённый клиентом start.okved."""
    if has_business:
        eg = (check_data.get("raw") or {}).get("FNS_EGRIP") or {}
        body = eg.get("body") if eg.get("status") == 200 else None
        return ((body or {}).get("okvedMain") or {}).get("code")
    return answers_map(goals).get("start.okved")


def business_age(check_data: dict, eval_date: dt.date) -> int | None:
    eg = (check_data.get("raw") or {}).get("FNS_EGRIP") or {}
    if eg.get("status") != 200 or not isinstance(eg.get("body"), dict):
        return None
    reg = parse_date(eg["body"].get("registrationDate"))
    return full_months(reg, eval_date) if reg else None


def good_bki(bki: dict | None, eval_date: dt.date) -> bool:
    """GOOD_BKI — scoring-model-v1.md, раздел 6 (полное техническое определение)."""
    s = get_settings()
    if not bki or not bki_valid(bki):
        return False
    f = bki_facts(bki, eval_date)
    if not f["fresh"] or not bki["loans"] or bki["requestsLast30Days"] > s.STARTUP_GOOD_BKI_MAX_REQUESTS:
        return False
    since12 = add_months(eval_date, -s.STARTUP_GOOD_BKI_MIN_LOAN_AGE_MONTHS)
    since36 = add_months(eval_date, -s.BKI_OVERDUE_LOOKBACK_MONTHS)
    if not any(parse_date(x["openedAt"]) <= since12 for x in bki["loans"]):
        return False
    active = [x for x in bki["loans"] if x["status"] == "ACTIVE"]
    if any(x["currentOverdueDays"] != 0 for x in active):
        return False
    if any(o["days"] > 0 and parse_date(o["date"]) >= since36 for x in bki["loans"] for o in x["overdues"]):
        return False
    return sum(x["monthlyPayment"] for x in active) <= s.STARTUP_GOOD_BKI_MAX_PAYMENT


def calculate(has_business: bool, check_data: dict, statement: dict | None, goals: dict | None,
              eval_date: dt.date) -> dict:
    s = get_settings()
    raw = check_data["raw"]
    manual: list[str] = list(check_data.get("manuals") or [])
    factors: list[dict] = []
    min_n = SCORING["MIN_MONTHS_FOR_FACTORS"]

    bki = raw["BKI"]["body"] if raw["BKI"]["status"] == 200 and bki_valid(raw["BKI"]["body"]) else None
    bf = bki_facts(bki, eval_date) if bki else None
    tax = raw["FNS_TAX_DEBT"]["body"] if raw["FNS_TAX_DEBT"]["status"] == 200 else None

    age = business_age(check_data, eval_date) if has_business else None
    startup_block = (not has_business) or age is None or age <= s.STARTUP_BLOCK_MAX_AGE_MONTHS

    # ---------- выписка ----------
    n = statement["monthsCovered"] if statement else 0
    R = E = None
    if statement:
        R, E = avg_income(statement), avg_expense(statement)
        if statement["allIn"] == 0:
            manual.append("NO_CONFIRMED_INCOME")
        elif statement["otherIn"] * 100 > statement["allIn"] * s.OTHER_IN_MAX_SHARE_PERCENT:
            manual.append("OTHER_IN_OVER_20")
        if n < 12:
            manual.append("STATEMENT_INCOMPLETE")
    elif has_business:
        manual.append("NO_VERIFIED_STATEMENT")

    L = bf["activeMonthlyPayments"] if bf else 0

    # ---------- BUSINESS ----------
    if startup_block:
        if bf:
            req = bf["requestsLast30Days"]
            p1 = _le(req, SCORING["BUSINESS_START_CREDIT_SEARCH"])
            p2 = _le(L, SCORING["BUSINESS_START_DEBT_LOAD"])
            t1, t2 = f"запросов в БКИ за 30 дней — {req}", f"действующие платежи по кредитам — {L} ₽ в месяц, доход не подтверждён"
        else:
            p1 = p2 = 0
            t1 = t2 = "кредитная история не получена"
        factors += [factor("BUSINESS_START_CREDIT_SEARCH", "BUSINESS", p1, 10, t1),
                    factor("BUSINESS_START_DEBT_LOAD", "BUSINESS", p2, 15, t2),
                    factor("BUSINESS_START_OPERATING_HISTORY", "BUSINESS", 0, 15,
                           "нет проверенной операционной истории")]
        if has_business:
            manual.append("BUSINESS_YOUNGER_3_MONTHS")
    else:
        stab = trend = buf = 0
        t_stab = t_trend = t_buf = "нет выписки хотя бы за 6 месяцев"
        if statement and n >= min_n:
            if R > 0:
                weak = sum(1 for v in statement["monthlyIncome"].values() if v < Fraction(SCORING["WEAK_MONTH_SHARE"]) * R)
                stab = _le(weak, SCORING["BUSINESS_STABILITY"])
                t_stab = f"месяцев с выручкой ниже 70% средней — {weak} из {n}"
                margin = (R - E) / R * 100
                buf = _ge(margin, SCORING["BUSINESS_CASH_BUFFER"])
                t_buf = f"остаток после расходов — {_pct(margin)}% поступлений"
            else:
                manual.append("REVENUE_ZERO")
                t_stab = t_buf = "подтверждённой выручки нет"
            last6 = statement["window"][-6:]
            if all(m in statement["monthlyIncome"] for m in last6):
                prev = sum(statement["monthlyIncome"][m] for m in last6[:3])
                last = sum(statement["monthlyIncome"][m] for m in last6[3:])
                if prev == 0:
                    manual.append("TREND_PREV_ZERO")
                    t_trend = "в предыдущие 3 месяца выручки не было — тренд не считается"
                else:
                    change = (Fraction(last, prev) - 1) * 100
                    trend = _ge(change, SCORING["BUSINESS_REVENUE_TREND"])
                    t_trend = f"выручка за 3 последних месяца {'выросла' if change >= 0 else 'упала'} на {_pct(abs(change))}%"
            else:
                t_trend = "нет операций во всех 6 последних месяцах"
        factors += [factor("BUSINESS_STABILITY", "BUSINESS", stab, 15, t_stab),
                    factor("BUSINESS_REVENUE_TREND", "BUSINESS", trend, 10, t_trend),
                    factor("BUSINESS_CASH_BUFFER", "BUSINESS", buf, 15, t_buf)]

    # ---------- OWNER ----------
    if not bf or not bf["fresh"]:
        od, t_od = 0, "кредитная история не оценена (нет актуального отчёта БКИ)"
    elif bf["currentOverdueDays"] > 0:
        od, t_od = 0, f"текущая просрочка {bf['currentOverdueDays']} дн."
    elif not bf["hasLoans"]:
        od, t_od = SCORING["OWNER_OVERDUE_NO_LOANS"], "кредитной истории нет"
    else:
        d = bf["historicOverdueDays"]
        od = _le(d, SCORING["OWNER_OVERDUE_HISTORY"])
        t_od = "просрочек за 36 месяцев нет" if d == 0 else f"наибольшая просрочка за 36 месяцев — {d} дн."
    factors.append(factor("OWNER_OVERDUE_HISTORY", "OWNER", od, 20, t_od))

    if not has_business or age is None:
        ba, t_ba = 0, "ИП не зарегистрирован"
    else:
        ba, t_ba = _ge(age, SCORING["OWNER_BUSINESS_AGE"]), f"ИП зарегистрирован {age} мес. назад"
    factors.append(factor("OWNER_BUSINESS_AGE", "OWNER", ba, 6, t_ba))

    tax_manual = any(c.startswith("TAX_") for c in manual)
    debt = (tax or {}).get("debtAmount")
    if tax_manual or not tax:
        tx, t_tx = 0, "налоговые данные требуют проверки"
    elif not tax["hasDebt"] and debt == 0:
        tx, t_tx = SCORING["OWNER_TAX_OK"], "задолженности перед ФНС нет"
    elif 1 <= debt <= s.TAX_DEBT_MINUS_LIMIT:
        tx, t_tx = SCORING["OWNER_TAX_SMALL_DEBT"], f"задолженность перед ФНС {debt} ₽"
    else:
        tx, t_tx = 0, f"задолженность перед ФНС {debt} ₽"
    factors.append(factor("OWNER_TAX_DISCIPLINE", "OWNER", tx, 4, t_tx))

    # ---------- IDEA ----------
    cov = stress = 0
    t_cov = t_stress = "подтверждённый денежный поток для оценки отсутствует"
    if statement and n >= min_n and R and R > 0 and not startup_block:
        free = R - E
        if L == 0:
            cov = SCORING["IDEA_COVERAGE_NO_LOANS"] if free > 0 else 0
            t_cov = "действующих кредитных платежей нет" + ("" if free > 0 else ", но остатка после расходов нет")
        else:
            ratio = free / L
            cov = _ge(ratio, SCORING["IDEA_VERIFIED_DEBT_COVERAGE"])
            t_cov = f"остаток покрывает кредитные платежи в {_pct(ratio)} раза"
        T = (Fraction(str(s.STRESS_REVENUE_SHARE)) * R - E) / R * 100
        stress = _ge(T, SCORING["IDEA_VERIFIED_STRESS_BUFFER"])
        t_stress = f"при снижении выручки на 20% запас — {_pct(T)}%"
    factors += [factor("IDEA_VERIFIED_DEBT_COVERAGE", "IDEA", cov, 10, t_cov),
                factor("IDEA_VERIFIED_STRESS_BUFFER", "IDEA", stress, 10, t_stress)]

    # ---------- INDUSTRY ----------
    okved = okved_for(has_business, check_data, goals)
    ind = refdata.find_industry(okved)
    if ind is None:
        manual.append("INDUSTRY_NOT_FOUND")
        msg = f"отрасль {okved or '—'} не найдена в справочнике"
        factors += [factor("INDUSTRY_BASE_RISK", "INDUSTRY", 0, 4, msg),
                    factor("INDUSTRY_REVENUE_TREND", "INDUSTRY", 0, 3, msg),
                    factor("INDUSTRY_CLOSURE_RATE", "INDUSTRY", 0, 3, msg)]
    else:
        as_of = parse_date(ind.get("dataAsOf"))
        if as_of is None or as_of > eval_date or add_months(as_of, s.INDUSTRY_MAX_AGE_MONTHS) < eval_date:
            manual.append("INDUSTRY_DATA_STALE")
        g, cl = ind.get("growthYoYPercent"), ind.get("closureSharePercent")
        if g is None or cl is None:
            manual.append("INDUSTRY_DATA_MISSING")
        tier = ind.get("riskTier")
        factors.append(factor("INDUSTRY_BASE_RISK", "INDUSTRY", SCORING["INDUSTRY_BASE_RISK"].get(tier, 0), 4,
                              f"категория риска отрасли — {tier}"))
        factors.append(factor("INDUSTRY_REVENUE_TREND", "INDUSTRY",
                              0 if g is None else _ge(Fraction(str(g)), SCORING["INDUSTRY_REVENUE_TREND"]), 3,
                              "нет данных о динамике отрасли" if g is None else f"динамика отрасли за год — {g:g}%"))
        factors.append(factor("INDUSTRY_CLOSURE_RATE", "INDUSTRY",
                              0 if cl is None else _lt(Fraction(str(cl)), SCORING["INDUSTRY_CLOSURE_RATE"]), 3,
                              "нет данных о закрытиях" if cl is None else f"доля закрытий в отрасли — {cl:g}%"))

    assert sum(f["maxPoints"] for f in factors) == 100
    total = sum(f["points"] for f in factors)
    manual = list(dict.fromkeys(manual))  # без повторов, порядок сохраняем

    # ---------- зона ----------
    amount = requested_amount(goals)
    gb = good_bki(bki, eval_date)
    if not has_business:
        auto = (not manual and gb and amount is not None and 1 <= amount <= s.STARTUP_AUTO_APPROVE_LIMIT
                and tax is not None and tax.get("debtAmount") == 0 and ind is not None)
        zone = "GREEN" if auto else "YELLOW"
    elif manual or n < 12 or age is None or age < s.GREEN_MIN_BUSINESS_AGE_MONTHS:
        zone = "YELLOW"
    elif total <= s.ZONE_RED_MAX:
        zone = "RED"
    elif total >= s.ZONE_GREEN_MIN:
        zone = "GREEN"
    else:
        zone = "YELLOW"

    flags = [{"code": c["code"], "basket": c["basket"], "text": texts.flag_text(c["code"])}
             for c in check_data["checks"] if c["basket"] in ("STOP", "MINUS", "MANUAL") and c.get("code")]
    check_codes = {f["code"] for f in flags}
    flags += [{"code": m, "basket": "MANUAL", "text": texts.flag_text(m)} for m in manual if m not in check_codes]

    return {
        "score": {"total": total, "zone": zone, "factors": factors, "flags": flags},
        "manualReasons": manual,
        "goodBki": gb,
        "requestedAmount": amount,
        "okved": okved,
        "businessAgeMonths": age,
        "evaluationDate": eval_date.isoformat(),
    }


def blocks(score: dict) -> dict:
    return {b: sum(f["points"] for f in score["factors"] if f["block"] == b) for b in BLOCKS}
