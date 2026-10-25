"""Логика заглушек внешних сервисов (без зависимостей).

Правила — contract/mocks-contract.md. Данные — mocks/data/*.json.
Один и тот же route() используют app.py (FastAPI) и devserver.py (стандартная библиотека).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent / "data"))

SERVICES = ("FNS_EGRIP", "FNS_TAX_DEBT", "BKI", "FSSP", "BANKRUPTCY", "PASSPORT")


def _load(name: str):
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


class Data:
    def __init__(self):
        self.egrip = _load("egrip.json")
        self.tax = _load("tax-debt.json")
        self.bki = _load("bki.json")
        self.fssp = _load("fssp.json")
        self.bankruptcy = _load("bankruptcy.json")
        self.passports = _load("passports.json")
        self.failures = _load("failures.json")


_DATA: Data | None = None


def data() -> Data:
    global _DATA
    if _DATA is None:
        _DATA = Data()
    return _DATA


# ---------- общие ответы ----------

def err(status: int, code: str, message: str):
    return status, {"code": code, "message": message}


def not_found(what: str):
    return err(404, "NOT_FOUND", f"{what} не найден в тестовых данных")


def unavailable():
    return err(503, "SERVICE_UNAVAILABLE", "Сервис временно недоступен (тестовый сценарий сбоя)")


def fails(service: str, inn: str | None = None, passport_key: str | None = None) -> bool:
    f = data().failures
    if inn and service in f.get("byInn", {}).get(inn, []):
        return True
    if passport_key and service in f.get("byPassport", {}).get(passport_key, []):
        return True
    return False


INN_RE = re.compile(r"^[0-9]{12}$")
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


def is_date(v) -> bool:
    if not isinstance(v, str) or not DATE_RE.match(v):
        return False
    try:
        dt.date.fromisoformat(v)
        return True
    except ValueError:
        return False


def norm_name(v) -> str:
    """trim, схлопнуть пробелы, верхний регистр, Ё→Е (mocks-contract.md, паспорт, шаг 4)."""
    if v is None:
        return ""
    s = re.sub(r"\s+", " ", str(v)).strip().upper()
    return s.replace("Ё", "Е")


# ---------- сервисы ----------

def egrip(inn: str):
    if not INN_RE.match(inn):
        return err(400, "VALIDATION_ERROR", "ИНН должен состоять из 12 цифр")
    if fails("FNS_EGRIP", inn=inn):
        return unavailable()
    rec = data().egrip.get(inn)
    if rec is None:
        return not_found("ИНН")
    if rec.get("_notIp"):
        return err(404, "NOT_IP", "Этот ИНН не принадлежит действующему ИП")
    return 200, rec


def tax_debt(inn: str):
    if not INN_RE.match(inn):
        return err(400, "VALIDATION_ERROR", "ИНН должен состоять из 12 цифр")
    if fails("FNS_TAX_DEBT", inn=inn):
        return unavailable()
    rec = data().tax.get(inn)
    return (200, rec) if rec is not None else not_found("ИНН")


def bankruptcy(inn: str):
    if not INN_RE.match(inn):
        return err(400, "VALIDATION_ERROR", "ИНН должен состоять из 12 цифр")
    if fails("BANKRUPTCY", inn=inn):
        return unavailable()
    rec = data().bankruptcy.get(inn)
    return (200, rec) if rec is not None else not_found("ИНН")


def bki_report(body: dict):
    inn = (body or {}).get("inn")
    passport = (body or {}).get("passport") or {}
    if not isinstance(inn, str) or not INN_RE.match(inn):
        return err(400, "VALIDATION_ERROR", "Нужен ИНН из 12 цифр")
    if not passport.get("series") or not passport.get("number"):
        return err(400, "VALIDATION_ERROR", "Нужны серия и номер паспорта")
    if fails("BKI", inn=inn):
        return unavailable()
    rec = data().bki.get(inn)
    return (200, rec) if rec is not None else not_found("Человек")


def fssp_search(body: dict):
    body = body or {}
    if not body.get("lastName") or not body.get("firstName") or not is_date(body.get("birthDate")):
        return err(400, "VALIDATION_ERROR", "Нужны фамилия, имя и дата рождения")
    key = (norm_name(body.get("lastName")), norm_name(body.get("firstName")),
           norm_name(body.get("middleName")), body["birthDate"])
    for rec in data().fssp:
        rk = (norm_name(rec["lastName"]), norm_name(rec["firstName"]),
              norm_name(rec.get("middleName")), rec["birthDate"])
        if rk == key:
            if fails("FSSP", inn=rec.get("inn")):
                return unavailable()
            return 200, {"proceedings": rec["proceedings"]}
    return not_found("Человек")


PASSPORT_FIELDS = ("LAST_NAME", "FIRST_NAME", "MIDDLE_NAME", "BIRTH_DATE", "ISSUE_DATE")


def passport_check(body: dict):
    """Вариант Б, алгоритм из mocks-contract.md → «Проверка паспорта», шаги 1–7."""
    b = body or {}
    # шаг 1 — валидация
    ok = (isinstance(b.get("series"), str) and re.fullmatch(r"[0-9]{4}", b["series"])
          and isinstance(b.get("number"), str) and re.fullmatch(r"[0-9]{6}", b["number"])
          and isinstance(b.get("lastName"), str) and b["lastName"].strip()
          and isinstance(b.get("firstName"), str) and b["firstName"].strip()
          and is_date(b.get("birthDate")) and is_date(b.get("issueDate"))
          and (b.get("middleName") is None or isinstance(b.get("middleName"), str)))
    if not ok:
        return err(400, "VALIDATION_ERROR", "Некорректные поля паспорта")
    key = f"{b['series']} {b['number']}"
    if fails("PASSPORT", passport_key=key):
        return unavailable()
    # шаг 2 — поиск только по серии и номеру
    rec = data().passports.get(key)
    if rec is None:
        return not_found("Паспорт")
    # Специальные тестовые записи P13/P14: заглушка нарочно отдаёт противоречивый ответ,
    # чтобы бэк проверил обработку PASSPORT_CHECK_CONFLICT (docs/passport-test-cases.md)
    if "_rawResponse" in rec:
        return 200, rec["_rawResponse"]
    # шаг 3 — недействительный документ
    if not rec["valid"]:
        return 200, {"valid": False, "reason": rec["reason"], "holderMatch": None, "mismatchFields": []}
    # шаг 6 — неполная эталонная запись
    required = ("lastName", "firstName", "birthDate", "issueDate")
    if any(not rec.get(k) for k in required) or "middleName" not in rec:
        return 200, {"valid": True, "reason": None, "holderMatch": None, "mismatchFields": []}
    # шаги 4–5 — сравнение
    mism = []
    if norm_name(b["lastName"]) != norm_name(rec["lastName"]):
        mism.append("LAST_NAME")
    if norm_name(b["firstName"]) != norm_name(rec["firstName"]):
        mism.append("FIRST_NAME")
    if norm_name(b.get("middleName")) != norm_name(rec.get("middleName")):
        mism.append("MIDDLE_NAME")
    if b["birthDate"] != rec["birthDate"]:
        mism.append("BIRTH_DATE")
    if b["issueDate"] != rec["issueDate"]:
        mism.append("ISSUE_DATE")
    return 200, {"valid": True, "reason": None, "holderMatch": not mism, "mismatchFields": mism}


# ---------- маршрутизация ----------

ROUTES = [
    ("GET", re.compile(r"^/health$"), lambda m, b: (200, {"status": "ok"})),
    ("GET", re.compile(r"^/fns/egrip/([^/]+)$"), lambda m, b: egrip(m.group(1))),
    ("GET", re.compile(r"^/fns/tax-debt/([^/]+)$"), lambda m, b: tax_debt(m.group(1))),
    ("GET", re.compile(r"^/bankruptcy/([^/]+)$"), lambda m, b: bankruptcy(m.group(1))),
    ("POST", re.compile(r"^/bki/report$"), lambda m, b: bki_report(b)),
    ("POST", re.compile(r"^/fssp/search$"), lambda m, b: fssp_search(b)),
    ("POST", re.compile(r"^/passport/check$"), lambda m, b: passport_check(b)),
]


def route(method: str, path: str, body=None):
    path = path.split("?", 1)[0].rstrip("/") or "/"
    for meth, rx, fn in ROUTES:
        m = rx.match(path)
        if m:
            if meth != method:
                return err(405, "VALIDATION_ERROR", "Метод не поддерживается")
            if method == "POST" and not isinstance(body, dict):
                return err(400, "VALIDATION_ERROR", "Тело запроса должно быть JSON-объектом")
            return fn(m, body)
    return err(404, "NOT_FOUND", "Нет такого адреса у заглушки")
