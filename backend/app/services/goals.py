"""Шаги 5–6. Проверка целей и ответов (PUT /goals) и анкеты (POST /questionnaire).

Правила проверки — question-sets.json + scoring-model-v1.md, раздел 8:
- goalType и questionId — только из question-sets.json, вопрос — из «своей» группы;
- обязательный вопрос (required) должен быть в ответах; null («не знаю») — только если unknownAllowed;
- значение по type: money/months/number — целое, boolean — true/false, choice — из options,
  text — 1…1000 символов после trim, okved — код из справочника;
- разумные границы чисел — config.ANSWER_LIMITS.
Любая ошибка → 400 VALIDATION_ERROR, в details — список проблем.
"""
from __future__ import annotations

from .. import refdata
from ..config import ANSWER_LIMITS, POSITIVE_MONEY
from ..errors import ApiError


def _bad(problems: list[dict]) -> ApiError:
    return ApiError(400, "VALIDATION_ERROR", "Проверьте ответы на вопросы", {"problems": problems})


def _as_int(v):
    """Целое число. 3.0 из JSON тоже считаем целым; True/False — нет."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return None


def _limits(qid: str, qtype: str) -> tuple[int, int]:
    if qid in ANSWER_LIMITS:
        return ANSWER_LIMITS[qid]
    if qtype == "money":
        return ANSWER_LIMITS["money.positive" if qid in POSITIVE_MONEY else "money"]
    return ANSWER_LIMITS[qtype]


def check_value(q: dict, value):
    """Проверяет одно значение. Возвращает (нормализованное значение, текст ошибки или None)."""
    qid, qtype = q["id"], q["type"]
    if value is None:
        return None, None if q["unknownAllowed"] else "ответ «не знаю» для этого вопроса не допускается"
    if qtype in ("money", "months", "number"):
        iv = _as_int(value)
        if iv is None:
            return None, "нужно целое число"
        lo, hi = _limits(qid, qtype)
        if not lo <= iv <= hi:
            return None, f"число должно быть от {lo} до {hi}"
        return iv, None
    if qtype == "boolean":
        return (value, None) if isinstance(value, bool) else (None, "нужно true или false")
    if qtype == "choice":
        return (value, None) if value in q["options"] else (None, f"допустимо: {', '.join(q['options'])}")
    if qtype == "text":
        if not isinstance(value, str):
            return None, "нужен текст"
        v = value.strip()
        lo, hi = _limits(qid, "text")
        if not lo <= len(v) <= hi:
            return None, f"текст от {lo} до {hi} символов"
        return v, None
    if qtype == "okved":
        if isinstance(value, str) and value in refdata.okved_by_code():
            return value, None
        return None, "код ОКВЭД не найден в справочнике"
    return None, "неизвестный тип вопроса"


def _check_group(answers: list[dict], group: str, where: str, problems: list[dict]) -> list[dict]:
    qs = refdata.questions_by_id()
    seen, out = set(), []
    for a in answers:
        qid = a["questionId"]
        q = qs.get(qid)
        if q is None or q["group"] != group:
            problems.append({"field": f"{where}.{qid}", "problem": "такого вопроса нет в этой группе"})
            continue
        if qid in seen:
            problems.append({"field": f"{where}.{qid}", "problem": "на вопрос ответили дважды"})
            continue
        seen.add(qid)
        value, err = check_value(q, a["value"])
        if err:
            problems.append({"field": f"{where}.{qid}", "problem": err})
        else:
            out.append({"questionId": qid, "value": value})
    # обязательные вопросы группы
    group_questions = (refdata.question_sets()["common"]["questions"] if group == "common" else
                       next(g["questions"] for g in refdata.question_sets()["goals"] if g["goalType"] == group))
    for q in group_questions:
        if q["required"] and q["id"] not in seen:
            problems.append({"field": f"{where}.{q['id']}", "problem": "обязательный вопрос без ответа"})
    return out


def validate_goals(data: dict) -> dict:
    """Проверяет GoalsData и возвращает очищенную копию (trim текста, 3.0 → 3)."""
    problems: list[dict] = []
    goals = data.get("goals") or []
    types = [g["goalType"] for g in goals]
    if not 1 <= len(goals) <= 3:
        problems.append({"field": "goals", "problem": "нужно от 1 до 3 целей"})
    if len(set(types)) != len(types):  # ВРЕМЕННО (вопрос 15)
        problems.append({"field": "goals", "problem": "одна и та же цель указана дважды"})
    clean_goals = [{"goalType": g["goalType"],
                    "answers": _check_group(g.get("answers") or [], g["goalType"], f"goals[{i}]", problems)}
                   for i, g in enumerate(goals)]
    common = _check_group(data.get("commonAnswers") or [], "common", "commonAnswers", problems)
    if problems:
        raise _bad(problems)
    out = {"source": data["source"], "goals": clean_goals, "commonAnswers": common}
    if data.get("clientText"):
        out["clientText"] = data["clientText"]
    return out


def answers_map(goals: dict | None) -> dict:
    """{questionId: value} по всем целям и общим вопросам."""
    out = {}
    if not goals:
        return out
    for g in goals.get("goals", []):
        for a in g["answers"]:
            out[a["questionId"]] = a["value"]
    for a in goals.get("commonAnswers", []):
        out[a["questionId"]] = a["value"]
    return out


def goal_types(goals: dict | None) -> list[str]:
    return [g["goalType"] for g in (goals or {}).get("goals", [])]


def requested_amount(goals: dict | None):
    """Запрошенная сумма — ТОЛЬКО common.amount (модель баллов, раздел 6)."""
    v = answers_map(goals).get("common.amount")
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def validate_questionnaire(q: dict) -> dict:
    problems = []
    for k, v in q.items():
        if v is None or k == "hasOtherLoans":
            continue
        lo, hi = ANSWER_LIMITS[f"questionnaire.{k}"]
        if not lo <= v <= hi:
            problems.append({"field": k, "problem": f"число должно быть от {lo} до {hi}"})
    if problems:
        raise ApiError(400, "VALIDATION_ERROR", "Проверьте ответы анкеты", {"problems": problems})
    return {k: v for k, v in q.items() if v is not None}
