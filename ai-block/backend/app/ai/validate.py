"""Схемы ответов модели и их проверка. Не прошло — AIUnavailable (llm-contract.md, правила 2–3)."""
import re

from .errors import AIUnavailable
from . import guard

NULLABLE_STR = {"type": ["string", "null"]}
ANSWER = {"type": "object", "additionalProperties": False, "required": ["questionId", "value"],
          "properties": {"questionId": {"type": "string"},
                         "value": {"type": ["string", "number", "boolean", "null"]}}}

SCHEMAS = {
    "dialog_step": {
        "type": "object", "additionalProperties": False,
        "required": ["state", "assistantText", "currentQuestionId", "quickReplies", "collected", "summaryText"],
        "properties": {
            "state": {"type": "string", "enum": ["ASKING", "SUMMARY", "ESCALATED"]},
            "assistantText": {"type": "string"},
            "currentQuestionId": NULLABLE_STR,
            "quickReplies": {"type": "array", "items": {"type": "string"}},
            "collected": {
                "type": "object", "additionalProperties": False, "required": ["source", "goals", "commonAnswers"],
                "properties": {
                    "source": {"type": "string", "enum": ["AI"]},
                    "goals": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False, "required": ["goalType", "answers"],
                        "properties": {"goalType": {"type": "string"}, "answers": {"type": "array", "items": ANSWER}}}},
                    "commonAnswers": {"type": "array", "items": ANSWER}}},
            "summaryText": NULLABLE_STR}},
    "suggest_okved": {"type": "object", "additionalProperties": False, "required": ["codes"],
                      "properties": {"codes": {"type": "array", "items": {"type": "string"}}}},
    "categorize_transactions": {
        "type": "object", "additionalProperties": False, "required": ["items"],
        "properties": {"items": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["rowId", "category"],
            "properties": {"rowId": {"type": "string"}, "category": {"type": "string"}}}}}},
    "explain_contract": {"type": "object", "additionalProperties": False, "required": ["answer", "foundInContract"],
                         "properties": {"answer": {"type": "string"}, "foundInContract": {"type": "boolean"}}},
    "staff_summary": {"type": "object", "additionalProperties": False, "required": ["points"],
                      "properties": {"points": {"type": "array", "items": {"type": "string"}}}},
}


def fail(msg: str):
    raise AIUnavailable(f"Ответ ИИ не прошёл проверку: {msg}")


def text_field(v, name: str, max_len: int, required: bool = True) -> str | None:
    if v is None and not required:
        return None
    if not isinstance(v, str) or not v.strip():
        fail(f"{name} пустой")
    v = v.strip()
    if len(v) > max_len:
        fail(f"{name} длиннее {max_len} символов")
    return v


# ---------- dialog_step ----------

# Пределы ответов — scoring-model-v1, раздел 8
LIMITS = {
    "common.amount": (1, 50_000_000), "marketing.months": (1, 60), "inventory.turnover": (1, 60),
    "cashgap.when": (1, 365), "start.experience": (0, 80), "location.staff": (0, 500),
}
TYPE_LIMITS = {"money": (0, 100_000_000), "months": (1, 120), "number": (0, 500)}
OKVED = re.compile(r"^\d{2}(\.\d{1,2}){0,2}$")


def _num(v, integer: bool):
    if isinstance(v, bool):
        return None
    if isinstance(v, str):
        t = v.replace(" ", "").replace(" ", "").replace(",", ".")
        try:
            v = float(t)
        except ValueError:
            return None
    if isinstance(v, (int, float)):
        if integer:
            return int(v) if float(v).is_integer() else None
        return int(v) if float(v).is_integer() else float(v)
    return None


def check_value(q: dict, v):
    """Проверить и привести значение ответа к типу вопроса (question-sets.json)."""
    qid, t = q["id"], q["type"]
    if v is None or (isinstance(v, str) and v.strip().lower() in ("", "не знаю", "null")):
        if q.get("unknownAllowed"):
            return None
        fail(f"{qid}: «не знаю» здесь нельзя")
    if t in ("money", "months", "number"):
        n = _num(v, integer=t in ("money", "months"))
        lo, hi = LIMITS.get(qid, TYPE_LIMITS[t])
        if n is None or not lo <= n <= hi:
            fail(f"{qid}: число вне допустимых границ")
        if q.get("required") and not q.get("unknownAllowed") and t == "money" and n == 0 \
                and qid in ("inventory.amount", "cashgap.amount", "tender.contract", "marketing.budget"):
            fail(f"{qid}: сумма должна быть больше 0")
        return n
    if t == "boolean":
        if isinstance(v, bool):
            return v
        fail(f"{qid}: нужно да/нет")
    if t == "choice":
        if v in q.get("options", []):
            return v
        fail(f"{qid}: вариант не из списка")
    if t == "okved":
        if isinstance(v, str) and OKVED.match(v.strip()):
            return v.strip()
        fail(f"{qid}: неверный код ОКВЭД")
    if t == "text":
        if not isinstance(v, str):
            fail(f"{qid}: нужен текст")
        s = guard.clean_client_text(v.strip(), 120 if qid == "start.city" else 1000)
        if not s:
            fail(f"{qid}: пустой текст")
        return s
    fail(f"{qid}: неизвестный тип вопроса")


def _answers(raw, allowed: dict, where: str) -> list:
    if not isinstance(raw, list):
        fail(f"{where}: ответы не списком")
    out, seen = [], set()
    for a in raw:
        if not isinstance(a, dict):
            fail(f"{where}: ответ не объект")
        qid = a.get("questionId")
        if qid not in allowed:
            fail(f"{where}: вопрос {qid!r} не из списка")
        if qid in seen:
            fail(f"{where}: вопрос {qid} дважды")
        seen.add(qid)
        out.append({"questionId": qid, "value": check_value(allowed[qid], a.get("value"))})
    return out


def dialog_step(r: dict, question_sets: dict) -> dict:
    goals_qs = {g["goalType"]: {q["id"]: q for q in g["questions"]} for g in question_sets.get("goals", [])}
    common_qs = {q["id"]: q for q in question_sets.get("common", {}).get("questions", [])}
    state = r.get("state")
    if state not in ("ASKING", "SUMMARY", "ESCALATED"):
        fail("неизвестное состояние")
    text = text_field(r.get("assistantText"), "assistantText", 600)
    summary = text_field(r.get("summaryText"), "summaryText", 1500, required=(state == "SUMMARY"))
    for t in (text, summary or ""):
        if guard.has_promise(t):
            fail("ИИ пообещал решение, ставку или процент")
    col = r.get("collected")
    if not isinstance(col, dict):
        fail("collected не объект")
    raw_goals = col.get("goals")
    if not isinstance(raw_goals, list) or len(raw_goals) > 3:
        fail("целей не 0–3")
    goals, seen = [], set()
    for g in raw_goals:
        gt = g.get("goalType") if isinstance(g, dict) else None
        if gt not in goals_qs or gt in seen:
            fail(f"цель {gt!r} не из списка или повторяется")
        seen.add(gt)
        goals.append({"goalType": gt, "answers": _answers(g.get("answers", []), goals_qs[gt], gt)})
    common = _answers(col.get("commonAnswers", []), common_qs, "common")
    if state != "ESCALATED" and not goals:
        fail("нет ни одной цели")
    qid = r.get("currentQuestionId")
    if state == "ASKING":
        allowed = set(common_qs) | {q for g in goals for q in goals_qs[g["goalType"]]}
        if qid not in allowed:
            fail(f"вопрос {qid!r} не из целей клиента")
    else:
        qid = None
    replies = r.get("quickReplies") or []
    if not isinstance(replies, list):
        replies = []
    replies = [guard.clean_client_text(x.strip(), 40) for x in replies if isinstance(x, str) and x.strip()][:4]
    return {"state": state, "assistantText": text, "currentQuestionId": qid, "quickReplies": replies,
            "collected": {"source": "AI", "goals": goals, "commonAnswers": common}, "summaryText": summary}


# ---------- остальные задачи ----------

def suggest_okved(r: dict, catalog: list[dict]) -> list[dict]:
    by_code = {c["code"]: c for c in catalog}
    codes = r.get("codes")
    if not isinstance(codes, list):
        fail("codes не список")
    out = []
    for c in codes:
        if c not in by_code:
            fail(f"код {c!r} не из справочника")
        if c not in [x["code"] for x in out]:
            out.append({"code": c, "name": by_code[c]["name"]})   # название — из справочника, не от модели
    return out[:3]


def categorize_transactions(r: dict, rows: list[dict], categories: list[str]) -> list[dict]:
    ids = {str(x.get("rowId")) for x in rows}
    items = r.get("items")
    if not isinstance(items, list):
        fail("items не список")
    out, seen = [], set()
    for it in items:
        if not isinstance(it, dict):
            fail("элемент не объект")
        rid, cat = str(it.get("rowId")), it.get("category")
        if rid not in ids:
            fail(f"строка {rid!r} не из выписки")
        if cat not in categories:
            fail(f"категория {cat!r} не из списка")
        if rid not in seen:
            seen.add(rid)
            out.append({"rowId": rid, "category": cat})
    return out


PROMISE_CONTRACT = re.compile(r"(одобр|гарантир|скидк|обязательно\s+(?:получите|пойд[её]т|согласу))", re.I)


def explain_contract(r: dict, contract_text: str, question: str) -> str:
    ans = text_field(r.get("answer"), "answer", 900)
    if PROMISE_CONTRACT.search(ans):
        fail("ИИ пообещал то, чего нет в договоре")
    extra = guard.unknown_numbers(ans, contract_text, question)
    if extra:
        fail(f"в ответе числа, которых нет в договоре: {sorted(extra)}")
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", ans) if s.strip()]
    if len(sentences) > 6:
        fail("ответ длиннее 5 предложений")
    return ans


def staff_summary(r: dict, card_text: str) -> str:
    pts = r.get("points")
    if not isinstance(pts, list) or not 3 <= len(pts) <= 5:
        fail("нужно 3–5 пунктов")
    out = []
    for p in pts:
        p = text_field(p, "пункт", 300)
        if guard.has_decision(p) or re.search(r"гарантир", p, re.I):
            fail("ИИ дал решение вместо специалиста")
        extra = guard.unknown_numbers(p, card_text, "из 100 баллов")   # «94 из 100» — шкала, а не выдумка
        if extra:
            fail(f"в сводке числа, которых нет в карточке: {sorted(extra)}")
        out.append(p)
    return "\n".join(f"• {p}" for p in out)
