"""Справочники из папок contract/ и tests/.

Сервер ЧИТАЕТ эти файлы как данные (JSON, CSV), но не импортирует оттуда код.
Пути задаются переменными CONTRACT_DIR и TESTS_DIR (в Docker — смонтированные папки).
Файлы читаются один раз и кешируются (lru_cache).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .config import get_settings


def _contract(name: str) -> Path:
    return Path(get_settings().CONTRACT_DIR) / name


def _tests(name: str) -> Path:
    return Path(get_settings().TESTS_DIR) / name


def _read_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@lru_cache
def question_sets() -> dict:
    return _read_json(_contract("question-sets.json"))


@lru_cache
def questions_by_id() -> dict[str, dict]:
    """questionId → вопрос (+ к какой группе относится: 'common' или goalType)."""
    qs = question_sets()
    out = {q["id"]: {**q, "group": "common"} for q in qs["common"]["questions"]}
    for g in qs["goals"]:
        for q in g["questions"]:
            out[q["id"]] = {**q, "group": g["goalType"]}
    return out


@lru_cache
def okved_catalog() -> list[dict]:
    return _read_json(_contract("okved.json"))


@lru_cache
def okved_by_code() -> dict[str, dict]:
    return {o["code"]: o for o in okved_catalog()}


@lru_cache
def industries() -> dict[str, dict]:
    return {i["okvedCode"]: i for i in _read_json(_contract("industries.json"))["industries"]}


def find_industry(code: str | None) -> dict | None:
    """Точное совпадение ОКВЭД, иначе — только двухзначная группа со scope=RUSSIA_OKVED_2DIGIT."""
    if not code:
        return None
    ind = industries()
    if code in ind:
        return ind[code]
    group = ind.get(code.split(".")[0])
    if group and group.get("scope") == "RUSSIA_OKVED_2DIGIT":
        return group
    return None


@lru_cache
def contract_clauses() -> dict:
    return _read_json(_contract("contract-clauses.json"))


@lru_cache
def demo_clients() -> list[dict]:
    return _read_json(_tests("demo-clients.json"))


def demo_statement_path(inn: str) -> Path | None:
    """Путь к тестовой выписке. ИНН проверяем строго (12 цифр), чтобы нельзя было выйти из папки."""
    if not re.fullmatch(r"[0-9]{12}", inn or ""):
        return None
    p = _tests("statements") / f"{inn}.csv"
    return p if p.is_file() else None


def _norm(s: str) -> str:
    return " ".join(s.casefold().replace("ё", "е").split())


def search_okved(query: str) -> list[dict]:
    q = _norm(query)
    return [o for o in okved_catalog() if o["code"].startswith(q) or q in _norm(o["name"])]
