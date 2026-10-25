"""Шаг 3. Шесть внешних проверок и «корзины».

Как это работает:
1. call_mocks() одновременно (в 6 потоках) вызывает заглушки: паспорт, ЕГРИП, налоги, БКИ,
   приставы, банкротство. Каждому вызову даём не больше MOCKS_TIMEOUT_SECONDS (5 с).
2. Для каждого ответа своя функция решает: state (OK/WARNING/FAIL/ERROR),
   basket (NONE/MINUS/MANUAL/STOP) и code — точный повод.
3. evaluate_checks() собирает итог: список CheckResult для клиента и внутренние данные
   (сырые ответы и причины MANUAL/STOP) — они понадобятся для расчёта баллов.

Правила: contract/mocks-contract.md, scoring-model-v1.md (3.2, 5), statuses.md («Уточнения проверок»).
Не ответил сервис (503/таймаут/сеть) → state=ERROR, basket=NONE: это НЕ отказ и НЕ MANUAL.
"""
from __future__ import annotations

import datetime as dt
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import httpx

from .. import texts
from ..clock import add_months, parse_date
from ..config import get_settings

SOURCES = ("PASSPORT", "FNS_EGRIP", "FNS_TAX_DEBT", "BKI", "FSSP", "BANKRUPTCY")


# ---------------------------------------------------------------- вызовы заглушек

@dataclass
class MockAnswer:
    status: int | None      # None — сервис не ответил (таймаут, сеть)
    body: dict | list | None

    @property
    def unavailable(self) -> bool:
        return self.status is None or self.status >= 500

    @property
    def error_code(self) -> str | None:
        return self.body.get("code") if isinstance(self.body, dict) else None


def _request(method: str, path: str, json_body: dict | None = None) -> MockAnswer:
    s = get_settings()
    try:
        r = httpx.request(method, s.MOCKS_URL.rstrip("/") + path, json=json_body,
                          timeout=s.MOCKS_TIMEOUT_SECONDS)
    except httpx.HTTPError:
        return MockAnswer(None, None)
    try:
        body = r.json()
    except ValueError:
        body = None
    return MockAnswer(r.status_code, body)


def call_mocks(passport: dict, inn: str) -> dict[str, MockAnswer]:
    p = passport
    calls = {
        "PASSPORT": ("POST", "/passport/check", {k: p.get(k) for k in (
            "series", "number", "lastName", "firstName", "middleName", "birthDate", "issueDate")}),
        "FNS_EGRIP": ("GET", f"/fns/egrip/{inn}", None),
        "FNS_TAX_DEBT": ("GET", f"/fns/tax-debt/{inn}", None),
        "BKI": ("POST", "/bki/report", {"passport": {k: p.get(k) for k in (
            "series", "number", "lastName", "firstName", "birthDate")}, "inn": inn}),
        "FSSP": ("POST", "/fssp/search", {k: p.get(k) for k in (
            "lastName", "firstName", "middleName", "birthDate")}),
        "BANKRUPTCY": ("GET", f"/bankruptcy/{inn}", None),
    }
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        futures = {src: pool.submit(_request, *args) for src, args in calls.items()}
        return {src: f.result() for src, f in futures.items()}


# ---------------------------------------------------------------- общие помощники

def norm_name(v) -> str:
    """trim, схлопнуть пробелы, верхний регистр, Ё→Е — как в паспортной проверке."""
    if v is None:
        return ""
    return re.sub(r"\s+", " ", str(v)).strip().upper().replace("Ё", "Е")


def _is_int(v, minimum: int = 0) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= minimum


class Verdict:
    """Результат одной проверки: то, что видит клиент, + внутренний повод."""

    def __init__(self, source: str, state: str, basket: str, code: str | None = None):
        self.source, self.state, self.basket, self.code = source, state, basket, code

    def public(self) -> dict:
        out = {"source": self.source, "state": self.state, "basket": self.basket,
               "clientText": texts.check_client_text(self.source, self.state)}
        if self.code:
            out["code"] = self.code
        return out


def unavailable(source: str) -> Verdict:
    return Verdict(source, "ERROR", "NONE", f"{source}_UNAVAILABLE")


# ---------------------------------------------------------------- паспорт (вариант Б)

PASSPORT_FIELDS = ["LAST_NAME", "FIRST_NAME", "MIDDLE_NAME", "BIRTH_DATE", "ISSUE_DATE"]


def eval_passport(a: MockAnswer) -> Verdict:
    src = "PASSPORT"
    if a.unavailable:
        return Verdict(src, "ERROR", "NONE", "PASSPORT_CHECK_UNAVAILABLE")
    if a.status == 404:
        return Verdict(src, "WARNING", "MANUAL", "PASSPORT_HOLDER_UNKNOWN")
    b = a.body
    if a.status != 200 or not isinstance(b, dict):
        return Verdict(src, "WARNING", "MANUAL", "PASSPORT_CHECK_CONFLICT")
    valid, reason, match, mism = b.get("valid"), b.get("reason"), b.get("holderMatch"), b.get("mismatchFields")
    # Любая противоречивая комбинация → CONFLICT (шаг 7 алгоритма), но не STOP
    if not isinstance(mism, list) or any(m not in PASSPORT_FIELDS for m in mism) \
            or mism != sorted(mism, key=PASSPORT_FIELDS.index):
        return Verdict(src, "WARNING", "MANUAL", "PASSPORT_CHECK_CONFLICT")
    if valid is False:
        if reason in ("LOST", "EXPIRED", "REPLACED") and match is None and mism == []:
            return Verdict(src, "FAIL", "STOP", "PASSPORT_INVALID")
        return Verdict(src, "WARNING", "MANUAL", "PASSPORT_CHECK_CONFLICT")
    if valid is True and reason is None:
        if match is True and mism == []:
            return Verdict(src, "OK", "NONE", "PASSPORT_VALID")
        if match is False and mism:
            return Verdict(src, "WARNING", "MANUAL", "PASSPORT_HOLDER_MISMATCH")
        if match is None and mism == []:
            return Verdict(src, "WARNING", "MANUAL", "PASSPORT_HOLDER_UNKNOWN")
    return Verdict(src, "WARNING", "MANUAL", "PASSPORT_CHECK_CONFLICT")


# ---------------------------------------------------------------- ЕГРИП

def eval_egrip(a: MockAnswer, has_business: bool, passport: dict) -> tuple[Verdict, str | None]:
    """Возвращает (вердикт, проблема_ИНН). Проблема ИНН — 'INN_NOT_FOUND'/'NOT_IP' при hasBusiness=true:
    тогда consent отвечает 422 и заявка возвращается в DRAFT."""
    src = "FNS_EGRIP"
    if a.unavailable:
        return unavailable(src), None
    b = a.body if isinstance(a.body, dict) else {}
    if a.status == 404:
        code = "NOT_IP" if a.error_code == "NOT_IP" else "INN_NOT_FOUND"
        if has_business:
            return Verdict(src, "FAIL", "NONE", code), code
        if code == "NOT_IP":   # стартап: «пока нет действующего ИП» — это нормально
            return Verdict(src, "OK", "NONE"), None
        return Verdict(src, "WARNING", "MANUAL", "INN_NOT_FOUND"), None
    status = b.get("status")
    if a.status != 200 or status not in ("ACTIVE", "TERMINATED") or parse_date(b.get("registrationDate")) is None:
        return Verdict(src, "WARNING", "MANUAL", "EGRIP_CONFLICT"), None
    if not has_business:
        if status == "TERMINATED":
            return Verdict(src, "OK", "NONE"), None
        return Verdict(src, "WARNING", "MANUAL", "EGRIP_ACTIVE_FOR_STARTUP"), None
    if status == "TERMINATED":
        return Verdict(src, "FAIL", "STOP", "EGRIP_TERMINATED"), None
    full = " ".join(x for x in (passport.get("lastName"), passport.get("firstName"), passport.get("middleName")) if x)
    if norm_name(b.get("fullName")) != norm_name(full):
        return Verdict(src, "WARNING", "MANUAL", "EGRIP_NAME_MISMATCH"), None
    return Verdict(src, "OK", "NONE"), None


# ---------------------------------------------------------------- налоги

def eval_tax(a: MockAnswer, eval_date: dt.date) -> Verdict:
    s, src = get_settings(), "FNS_TAX_DEBT"
    if a.unavailable:
        return unavailable(src)
    b = a.body if isinstance(a.body, dict) else {}
    if a.status == 404:
        return Verdict(src, "WARNING", "MANUAL", "TAX_NOT_FOUND")       # ВРЕМЕННО (вопрос 9)
    as_of, has_debt, amount = parse_date(b.get("asOf")), b.get("hasDebt"), b.get("debtAmount")
    if a.status != 200 or as_of is None or not isinstance(has_debt, bool) or not _is_int(amount) \
            or has_debt != (amount > 0) or as_of > eval_date:
        return Verdict(src, "WARNING", "MANUAL", "TAX_CONFLICT")
    if (eval_date - as_of).days > s.TAX_MAX_AGE_DAYS:
        return Verdict(src, "WARNING", "MANUAL", "TAX_STALE")
    if amount > s.TAX_DEBT_MINUS_LIMIT:
        return Verdict(src, "WARNING", "MANUAL", "TAX_DEBT_OVER_LIMIT")
    if amount > 0:
        return Verdict(src, "WARNING", "MINUS", "TAX_DEBT")
    return Verdict(src, "OK", "NONE")


# ---------------------------------------------------------------- БКИ

def bki_valid(b) -> bool:
    """Структура отчёта БКИ по mocks-contract.md. Невалидный отчёт нельзя считать актуальным."""
    if not isinstance(b, dict) or parse_date(b.get("reportAsOf")) is None:
        return False
    if not isinstance(b.get("loans"), list) or not _is_int(b.get("requestsLast30Days")):
        return False
    for loan in b["loans"]:
        if not isinstance(loan, dict) or loan.get("status") not in ("ACTIVE", "CLOSED"):
            return False
        if parse_date(loan.get("openedAt")) is None:
            return False
        if not _is_int(loan.get("monthlyPayment")) or not _is_int(loan.get("currentOverdueDays")):
            return False
        if not isinstance(loan.get("overdues"), list):
            return False
        for o in loan["overdues"]:
            if not isinstance(o, dict) or parse_date(o.get("date")) is None or not _is_int(o.get("days")):
                return False
    return True


def bki_facts(b: dict, eval_date: dt.date) -> dict:
    """Факты из отчёта БКИ, нужные и проверке, и баллам."""
    s = get_settings()
    as_of = parse_date(b["reportAsOf"])
    fresh = as_of <= eval_date and (eval_date - as_of).days <= s.BKI_MAX_AGE_DAYS
    active = [x for x in b["loans"] if x["status"] == "ACTIVE"]
    since = add_months(eval_date, -s.BKI_OVERDUE_LOOKBACK_MONTHS)
    hist = [o["days"] for x in b["loans"] for o in x["overdues"] if parse_date(o["date"]) >= since]
    return {
        "fresh": fresh,
        "currentOverdueDays": max((x["currentOverdueDays"] for x in active), default=0),
        "historicOverdueDays": max(hist, default=0),
        "activeMonthlyPayments": sum(x["monthlyPayment"] for x in active),
        "hasLoans": bool(b["loans"]),
        "requestsLast30Days": b["requestsLast30Days"],
    }


def eval_bki(a: MockAnswer, eval_date: dt.date) -> Verdict:
    s, src = get_settings(), "BKI"
    if a.unavailable:
        return Verdict(src, "ERROR", "NONE", "BKI_UNAVAILABLE")
    if a.status == 404:
        return Verdict(src, "WARNING", "MANUAL", "BKI_NOT_FOUND")       # ВРЕМЕННО (вопрос 9)
    if a.status != 200 or not bki_valid(a.body):
        return Verdict(src, "WARNING", "MANUAL", "BKI_CONFLICT")
    f = bki_facts(a.body, eval_date)
    if not f["fresh"]:
        return Verdict(src, "WARNING", "MANUAL", "BKI_REPORT_STALE")
    if f["currentOverdueDays"] >= s.BKI_CURRENT_OVERDUE_STOP_DAYS:
        return Verdict(src, "FAIL", "STOP", "BKI_CURRENT_OVERDUE_90")
    if f["currentOverdueDays"] >= 1:
        return Verdict(src, "WARNING", "MANUAL", "BKI_CURRENT_OVERDUE")
    if f["historicOverdueDays"] >= s.BKI_HISTORIC_OVERDUE_MANUAL_DAYS:
        return Verdict(src, "WARNING", "MANUAL", "BKI_HISTORIC_OVERDUE_90")
    if f["historicOverdueDays"] > 0:
        return Verdict(src, "WARNING", "MINUS", "BKI_HISTORIC_OVERDUE")
    return Verdict(src, "OK", "NONE")


# ---------------------------------------------------------------- приставы

def eval_fssp(a: MockAnswer) -> Verdict:
    src = "FSSP"
    if a.unavailable:
        return unavailable(src)
    if a.status == 404:
        return Verdict(src, "WARNING", "MANUAL", "FSSP_NOT_FOUND")      # ВРЕМЕННО (вопрос 9)
    b = a.body if isinstance(a.body, dict) else {}
    procs = b.get("proceedings")
    if a.status != 200 or not isinstance(procs, list) or any(
            not isinstance(p, dict) or p.get("status") not in ("ACTIVE", "FINISHED") for p in procs):
        return Verdict(src, "WARNING", "MANUAL", "FSSP_CONFLICT")
    if any(p["status"] == "ACTIVE" for p in procs):
        return Verdict(src, "WARNING", "MANUAL", "FSSP_ACTIVE")
    return Verdict(src, "OK", "NONE")


# ---------------------------------------------------------------- банкротство

def eval_bankruptcy(a: MockAnswer, eval_date: dt.date) -> Verdict:
    s, src = get_settings(), "BANKRUPTCY"
    if a.unavailable:
        return unavailable(src)
    if a.status == 404:
        return Verdict(src, "WARNING", "MANUAL", "BANKRUPTCY_NOT_FOUND")  # ВРЕМЕННО (вопрос 9)
    b = a.body if isinstance(a.body, dict) else {}
    conflict = Verdict(src, "WARNING", "MANUAL", "BANKRUPTCY_CONFLICT")
    if a.status != 200:
        return conflict
    in_proc, stage = b.get("inProcedure"), b.get("stage")
    started_raw, completed_raw = b.get("startedAt"), b.get("completedAt")
    started, completed = parse_date(started_raw), parse_date(completed_raw)
    if (started_raw is not None and started is None) or (completed_raw is not None and completed is None):
        return conflict
    if in_proc is True:
        if stage in ("RESTRUCTURING", "REALIZATION") and completed_raw is None:
            return Verdict(src, "FAIL", "STOP", "BANKRUPTCY_CURRENT")
        return conflict
    if in_proc is not False:
        return conflict
    if stage is None:
        return Verdict(src, "OK", "NONE") if completed_raw is None else conflict
    if stage != "COMPLETED" or completed is None or completed > eval_date \
            or (started is not None and completed < started):
        return conflict
    # Правило пяти лет: MANUAL, пока evaluationDate < completedAt + 5 календарных лет
    if eval_date < add_months(completed, 12 * s.BANKRUPTCY_MANUAL_YEARS):
        return Verdict(src, "WARNING", "MANUAL", "BANKRUPTCY_PAST_LT_5Y")
    return Verdict(src, "OK", "NONE")


# ---------------------------------------------------------------- итог

def evaluate_checks(passport: dict, inn: str, has_business: bool, eval_date: dt.date,
                    answers: dict[str, MockAnswer] | None = None) -> dict:
    """Вызывает заглушки и возвращает:
    checks — список CheckResult (порядок: паспорт, ЕГРИП, налоги, БКИ, ФССП, банкротство);
    errors / stops / manuals / minuses — коды по корзинам; innProblem — для 422;
    raw — сырые ответы заглушек (для баллов)."""
    answers = answers or call_mocks(passport, inn)
    egrip_verdict, inn_problem = eval_egrip(answers["FNS_EGRIP"], has_business, passport)
    verdicts = [
        eval_passport(answers["PASSPORT"]),
        egrip_verdict,
        eval_tax(answers["FNS_TAX_DEBT"], eval_date),
        eval_bki(answers["BKI"], eval_date),
        eval_fssp(answers["FSSP"]),
        eval_bankruptcy(answers["BANKRUPTCY"], eval_date),
    ]
    return {
        "checks": [v.public() for v in verdicts],
        "errors": [v.source for v in verdicts if v.state == "ERROR"],
        "stops": [v.code for v in verdicts if v.basket == "STOP"],
        "manuals": [v.code for v in verdicts if v.basket == "MANUAL"],
        "minuses": [v.code for v in verdicts if v.basket == "MINUS"],
        "innProblem": inn_problem,
        "raw": {src: {"status": a.status, "body": a.body} for src, a in answers.items()},
        "evaluationDate": eval_date.isoformat(),
    }
