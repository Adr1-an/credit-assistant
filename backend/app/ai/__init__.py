"""Блок ИИ: пять функций из contract/llm-contract.md. Бэк вызывает только их.

Владелец папки — человек 4. Сигнатуры не менять без согласования с бэком.
Любая проблема (ИИ выключен, не ответил, ответ не прошёл проверку) → AIUnavailable,
бэк ловит его и включает запасной вариант (форма, готовые ответы, aiSummary = null).
"""
import json
import re
from pathlib import Path
from typing import Optional  # noqa: F401  (как в контракте)

from . import client, guard, validate
from .errors import AIUnavailable

__all__ = ["AIUnavailable", "is_available", "dialog_step", "suggest_okved",
           "categorize_transactions", "explain_contract", "staff_summary"]

_PROMPTS = Path(__file__).resolve().parent / "prompts"
MAX_HISTORY = 30          # сообщений диалога в промпте
MAX_ROWS = 50             # строк выписки за один вызов
MAX_CARD_CHARS = 14000    # карточка для сводки


def _prompt(name: str) -> str:
    return (_PROMPTS / f"{name}.md").read_text(encoding="utf-8")


def is_available() -> bool:
    """ИИ включён (LLM_ENABLED=true, задан LLM_BASE_URL) и прокси отвечает."""
    return client.is_available()


def _with_labels(question_sets: dict) -> dict:
    """Копия question_sets с подписями вариантов: клиент нажимает «Аренда, уже нашёл», модель пишет RENT_FOUND."""
    qs = json.loads(json.dumps(question_sets))
    for q in qs.get("common", {}).get("questions", []) + [q for g in qs.get("goals", []) for q in g.get("questions", [])]:
        if q.get("options"):
            q["optionLabels"] = {o: validate.OPTION_LABELS.get(o, o) for o in q["options"]}
    return qs


def dialog_step(context: dict, history: list[dict], question_sets: dict) -> dict:
    """Шаги 5–6. Следующий вопрос или сводка. Возвращает DialogStepResult (llm-contract.md, задача 1)."""
    lines = []
    for m in (history or [])[-MAX_HISTORY:]:
        if not isinstance(m, dict):
            continue
        if m.get("role") == "CLIENT":
            lines.append("Клиент: " + guard.client_text(m.get("text")))
        else:
            lines.append("Ассистент: " + guard.clean_client_text(m.get("text"), 1000))
    user = "\n".join([
        guard.data("context", context or {}),
        guard.data("question_sets", _with_labels(question_sets or {})),
        "<dialog>\n" + ("\n".join(lines) or "(диалог только начинается)") + "\n</dialog>",
        "Сделай следующий шаг диалога.",
    ])
    raw = client.chat_json("dialog_step", _prompt("dialog_step"), user, validate.SCHEMAS["dialog_step"])
    return validate.dialog_step(raw, question_sets or {})


def suggest_okved(text: str, okved_catalog: list[dict]) -> list[dict]:
    """До 3 кодов ОКВЭД из okved_catalog. Возвращает [{code, name}]."""
    catalog = [{"code": c["code"], "name": c["name"]} for c in (okved_catalog or []) if "code" in c and "name" in c]
    if not catalog:
        raise AIUnavailable("Пустой справочник ОКВЭД")
    user = "\n".join([guard.data("okved_catalog", catalog), guard.client_text(text, 500), "Подбери коды."])
    raw = client.chat_json("suggest_okved", _prompt("suggest_okved"), user, validate.SCHEMAS["suggest_okved"])
    return validate.suggest_okved(raw, catalog)


def categorize_transactions(rows: list[dict], categories: list[str]) -> list[dict]:
    """Разложить операции выписки по категориям, которые не распознали правила.

    Результат — только подсказка для показа: в баллах и выручке не используется (llm-contract.md, задача 3).
    """
    rows = list(rows or [])[:MAX_ROWS]
    if not rows:
        return []
    safe = [{"rowId": str(r.get("rowId")), "direction": r.get("direction"), "amount": r.get("amount"),
             "purpose": guard.clean_client_text(r.get("purpose"), 300),
             "counterparty": guard.clean_client_text(r.get("counterparty"), 200)} for r in rows]
    user = "\n".join([guard.data("categories", list(categories or [])), guard.data("rows", safe), "Разложи операции."])
    raw = client.chat_json("categorize_transactions", _prompt("categorize_transactions"), user,
                           validate.SCHEMAS["categorize_transactions"])
    return validate.categorize_transactions(raw, safe, list(categories or []))


_CLAUSE_REF = re.compile(r"пункт\w*\s+\d{1,2}", re.I)


def explain_contract(contract: dict, question: str) -> str:
    """Ответ на вопрос «Что будет, если…» по договору этого клиента. 2–5 предложений."""
    contract_json = json.dumps(contract or {}, ensure_ascii=False)
    user = "\n".join([guard.data("contract", contract or {}), guard.client_text(question, 500),
                      "Ответь на вопрос клиента по этому договору."])
    raw = client.chat_json("explain_contract", _prompt("explain_contract"), user, validate.SCHEMAS["explain_contract"])
    answer = raw.get("answer")
    if isinstance(answer, str):   # GigaChat иногда дописывает служебное поле в текст
        answer = re.sub(r"\s*\(?foundInContract\s*[=:]\s*\w+\)?\.?", "", answer).strip()
    answer = validate.text_field(answer, "answer", 900)
    # «пункт 5» — номер пункта на сайте, а не число из договора: его не считаем выдуманной цифрой
    n_clauses = len((contract or {}).get("clauses") or [])

    def _drop_ref(m):
        return "" if int(re.search(r"\d+", m.group()).group()) <= n_clauses else m.group()

    validate.explain_contract({"answer": _CLAUSE_REF.sub(_drop_ref, answer) or answer}, contract_json, question or "")
    return answer


def staff_summary(card: dict) -> str:
    """Короткая сводка для сотрудника: 3–5 пунктов «на что обратить внимание». Решения не даёт."""
    safe = guard.strip_card(card or {})
    card_json = json.dumps(safe, ensure_ascii=False, separators=(",", ":"))
    if len(card_json) > MAX_CARD_CHARS:
        for k in ("contract", "offers", "statement", "dialog", "estimate"):
            if len(card_json) <= MAX_CARD_CHARS:
                break
            safe.pop(k, None)
            card_json = json.dumps(safe, ensure_ascii=False, separators=(",", ":"))
    user = "\n".join([f"<card>{card_json}</card>", "Напиши сводку для специалиста."])
    raw = client.chat_json("staff_summary", _prompt("staff_summary"), user, validate.SCHEMAS["staff_summary"])
    return validate.staff_summary(raw, card_json, safe)
