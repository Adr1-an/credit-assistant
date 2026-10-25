"""Защита: текст клиента — данные, а не команды; ИИ ничего не обещает и не выдумывает цифр.

1. Всё, что написал человек, попадает в промпт только внутри <client_text>…</client_text>,
   а угловые скобки в нём заменяются — клиент не может «закрыть» тег и дописать свои правила.
2. Ответы модели проверяются: нет обещаний одобрения и ставок, числа — только из исходных данных.
"""
import copy
import json
import re

MAX_CLIENT_TEXT = 2000
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_client_text(text, limit: int = MAX_CLIENT_TEXT) -> str:
    s = "" if text is None else str(text)
    s = _CTRL.sub(" ", s).replace("<", "‹").replace(">", "›")
    return s[:limit]


def client_text(text, limit: int = MAX_CLIENT_TEXT) -> str:
    return f"<client_text>{clean_client_text(text, limit)}</client_text>"


def data(tag: str, obj) -> str:
    """Служебные данные (не от клиента) — компактный JSON в своём теге."""
    return f"<{tag}>{json.dumps(obj, ensure_ascii=False, separators=(',', ':'))}</{tag}>"


# ---------- проверки ответов ----------

# Обещания решения, ставок, процентов — ИИ этого делать нельзя (llm-contract.md, правило 1)
PROMISE = re.compile(r"(одобр|гарантир|ставк|процент|%|обязательно\s+(?:получите|дадут|выдадут)|кредит\s+(?:вам\s+)?(?:дадут|выдадут))", re.I)
# Совет специалисту одобрить/отказать — решение принимает человек
DECISION = re.compile(r"(рекоменд\w*|совету\w*|следует|нужно|стоит|предлага\w*)\s+(?:\w+\s+){0,2}(одобр|отказ|отклон)", re.I)
_NUM = re.compile(r"\d[\d   ]*(?:[.,]\d+)?")


def numbers(text: str) -> set[str]:
    out = set()
    for m in _NUM.findall(text or ""):
        n = re.sub(r"[\s  ]", "", m).replace(",", ".").rstrip(".")
        if n:
            out.add(n)
            out.add(n.split(".")[0])
    return out


def unknown_numbers(answer: str, *sources: str) -> set[str]:
    """Числа из ответа, которых нет ни в одном источнике."""
    allowed = set()
    for s in sources:
        allowed |= numbers(s)
    return {n for n in numbers(answer) if n not in allowed}


def has_promise(text: str) -> bool:
    return bool(PROMISE.search(text or ""))


def has_decision(text: str) -> bool:
    return bool(DECISION.search(text or ""))


# ---------- что можно отправлять во внешнюю модель ----------

# Персональные данные во внешний ИИ не уходят: ему не нужны паспорт, ИНН и ФИО
_PERSONAL_KEYS = {"passport", "inn", "applicantName", "counterpartyInn", "fullName", "lastName", "firstName",
                  "middleName", "birthDate", "series", "number", "issueDate", "aiSummary", "history"}


def strip_card(card: dict) -> dict:
    """Карточка для сводки: без персональных данных, текст клиента — в <client_text>."""
    def walk(o, key=None):
        if isinstance(o, dict):
            out = {}
            for k, v in o.items():
                if k in _PERSONAL_KEYS:
                    continue
                if k == "clientText":
                    out[k] = client_text(v)
                elif k == "messages" and isinstance(v, list):
                    out[k] = [{"role": m.get("role"),
                               "text": client_text(m.get("text")) if m.get("role") == "CLIENT" else m.get("text")}
                              for m in v if isinstance(m, dict)]
                else:
                    out[k] = walk(v, k)
            return out
        if isinstance(o, list):
            return [walk(x) for x in o]
        return o
    return walk(copy.deepcopy(card))
