"""Схемы ответов модели и их проверка. Не прошло — AIUnavailable (llm-contract.md, правила 2–3)."""
import logging
import re

from .errors import AIUnavailable
from . import guard

log = logging.getLogger("app.ai")

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
    # По полю на тему: GigaChat заполняет поля надёжнее, чем пишет нужное число пунктов в массиве
    "staff_summary": {"type": "object", "additionalProperties": False,
                      "required": ["risk", "score", "statement", "offer", "missing"],
                      "properties": {k: NULLABLE_STR for k in ("risk", "score", "statement", "offer", "missing")}},
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
# Подписи кнопок для вопросов с выбором (коды — из question-sets.json; подписи — только для показа клиенту)
OPTION_LABELS = {
    "NEW": "Новое", "USED": "Б/у",
    "REPLACEMENT": "Замена старого", "EXPANSION": "Расширение",
    "OWN": "Своё помещение", "RENT_FOUND": "Аренда, уже нашёл", "RENT_NOT_FOUND": "Аренда, ещё ищу",
    "NOT_NEEDED": "Помещение не нужно",
}
UNKNOWN_LABEL = "Не знаю"


def fixed_replies(q: dict) -> list[str] | None:
    """Кнопки для вопроса с выбором или да/нет — всегда одинаковые, не от модели."""
    if q["type"] == "choice":
        out = [OPTION_LABELS.get(o, o) for o in q.get("options", [])]
    elif q["type"] == "boolean":
        out = ["Да", "Нет"]
    else:
        return None
    if q.get("unknownAllowed"):
        out.append(UNKNOWN_LABEL)
    return out[:5]


CODE = re.compile(r"^[A-Z][A-Z0-9_]*$")
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


_OKVED_CODES: set | None = None   # коды справочника на время одной проверки диалога


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
        if isinstance(v, str) and OKVED.match(v.strip()) and (_OKVED_CODES is None or v.strip() in _OKVED_CODES):
            return v.strip()
        fail(f"{qid}: не код ОКВЭД из справочника")
    if t == "text":
        if not isinstance(v, str):
            fail(f"{qid}: нужен текст")
        s = guard.clean_client_text(v.strip(), 120 if qid == "start.city" else 1000)
        if not s:
            fail(f"{qid}: пустой текст")
        return s
    fail(f"{qid}: неизвестный тип вопроса")


def _answers(raw, allowed: dict, where: str, dropped: list | None = None) -> list:
    """Ответы одной цели. Чужой вопрос или повтор — весь ответ модели отбрасывается (контракт, правило 3).
    Неподходящее значение (например, «пекарня» вместо кода ОКВЭД) — убираем только этот ответ:
    вопрос зададут ещё раз или его заполнит форма. Причина — в dropped (для лога)."""
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
        try:
            out.append({"questionId": qid, "value": check_value(allowed[qid], a.get("value"))})
        except AIUnavailable as e:
            if dropped is None:
                raise
            dropped.append(str(e).replace("Ответ ИИ не прошёл проверку: ", ""))
    return out


def _missing_required(goals: list, goals_qs: dict, common_qs: dict, common: list) -> str | None:
    """Первый обязательный вопрос без ответа (null при unknownAllowed считается ответом)."""
    for g in goals:
        have = {a["questionId"] for a in g["answers"]}
        for qid, q in goals_qs[g["goalType"]].items():
            if q.get("required") and qid not in have:
                return qid
    have = {a["questionId"] for a in common}
    for qid, q in common_qs.items():
        if q.get("required") and qid not in have:
            return qid
    return None


def dialog_step(r: dict, question_sets: dict, okved_codes: set | None = None) -> dict:
    global _OKVED_CODES
    _OKVED_CODES = okved_codes
    goals_qs = {g["goalType"]: {q["id"]: q for q in g["questions"]} for g in question_sets.get("goals", [])}
    common_qs = {q["id"]: q for q in question_sets.get("common", {}).get("questions", [])}
    for k in ("summaryText", "currentQuestionId"):
        if isinstance(r.get(k), str) and r[k].strip().lower() in ("", "null", "none"):
            r[k] = None   # GigaChat иногда пишет null строкой
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
    goals, seen, dropped = [], set(), []
    for g in raw_goals:
        gt = g.get("goalType") if isinstance(g, dict) else None
        if gt not in goals_qs or gt in seen:
            fail(f"цель {gt!r} не из списка или повторяется")
        seen.add(gt)
        goals.append({"goalType": gt, "answers": _answers(g.get("answers", []), goals_qs[gt], gt, dropped)})
    common = _answers(col.get("commonAnswers", []), common_qs, "common", dropped)
    if state == "SUMMARY" and not goals:
        fail("сводка без целей")
    all_qs = {**common_qs, **{k: v for g in goals_qs.values() for k, v in g.items()}}
    qid = r.get("currentQuestionId")
    if state == "SUMMARY":
        # Сводка, а обязательный вопрос без ответа (модель поторопилась или ответ убрали выше) —
        # вместо сводки задаём этот вопрос, иначе «Всё верно» упадёт на PUT /goals.
        miss = _missing_required(goals, goals_qs, common_qs, common)
        if miss:
            state, qid, summary = "ASKING", miss, None
            text = all_qs[miss]["text"]
            dropped.append(f"сводка без ответа на обязательный {miss} — задаём этот вопрос")
    if state == "ASKING" and not goals:
        qid = None   # уточняющий вопрос «на что нужны деньги?»; через 2 сообщения сервер сам ставит ESCALATED
    elif state == "ASKING":
        allowed = set(common_qs) | {q for g in goals for q in goals_qs[g["goalType"]]}
        if qid not in allowed:
            fail(f"вопрос {qid!r} не из целей клиента")
    else:
        qid = None
    # кнопки модели относятся к её вопросу; если вопрос заменили выше — её кнопки не показываем
    replies = (r.get("quickReplies") or []) if state == "ASKING" and r.get("currentQuestionId") == qid else []
    if not isinstance(replies, list):
        replies = []
    fixed = fixed_replies(all_qs[qid]) if qid in all_qs else None
    if fixed is not None:
        replies = fixed
    reply_len = 70 if qid in all_qs and all_qs[qid]["type"] == "okved" else 40   # «10.71 Производство хлеба…»
    replies = [guard.clean_client_text(x.strip(), reply_len) for x in replies
               if isinstance(x, str) and x.strip() and not CODE.match(x.strip())][:5]   # коды вроде REPLACEMENT не показываем
    for d in dropped:
        log.warning("ИИ (диалог): часть ответа убрана — %s", d)
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


SUMMARY_FIELDS = ("risk", "score", "statement", "offer", "missing")
BLOCK_MAX = {"BUSINESS": 40, "OWNER": 30, "IDEA": 20, "INDUSTRY": 10}   # scoring-model-v1
BLOCK_RU = {"BUSINESS": "Бизнес", "OWNER": "Владелец", "IDEA": "Идея", "INDUSTRY": "Отрасль"}
ZONE_RU = {"GREEN": "зелёная", "YELLOW": "жёлтая", "RED": "красная"}


def _money(n) -> str:
    return f"{int(n):,}".replace(",", " ") + " ₽"


def card_facts(card: dict) -> list[str]:
    """Пункты, которые код собирает сам из карточки, если модель написала мало. Только готовые факты."""
    out = []
    score = card.get("score") or {}
    for f in (score.get("flags") or [])[:2]:
        if isinstance(f, dict) and f.get("text"):
            out.append(f"Флаг для проверки: {f['text']}.")
    if isinstance(score.get("total"), (int, float)):
        z = ZONE_RU.get(score.get("zone"), score.get("zone") or "")
        out.append(f"Баллы: {score['total']} из 100" + (f", зона {z}." if z else "."))
    blocks = score.get("blocks") or {}
    shares = {b: blocks[b] / mx for b, mx in BLOCK_MAX.items() if isinstance(blocks.get(b), (int, float))}
    if shares and min(shares.values()) < 1:
        b = min(shares, key=shares.get)
        out.append(f"Меньше всего баллов в блоке «{BLOCK_RU[b]}»: {blocks[b]} из {BLOCK_MAX[b]}.")
    st = card.get("statement") or card.get("statementSummary") or {}
    if isinstance(st, dict) and isinstance(st.get("avgMonthlyIncome"), (int, float)):
        line = f"По выписке средний доход {_money(st['avgMonthlyIncome'])} в месяц"
        if isinstance(st.get("avgMonthlyExpense"), (int, float)):
            line += f", расходы {_money(st['avgMonthlyExpense'])}"
        out.append(line + ".")
    rec = card.get("recommendation") or {}
    if isinstance(rec, dict) and rec.get("text"):
        out.append(f"Подсказка системы: {rec['text'].rstrip('.')}.")
    return out


def _words(t: str) -> set[str]:
    return {w[:6] for w in re.findall(r"[а-яёa-z]{5,}", t.lower())}


def _similar(a: str, b: str) -> bool:
    """Пункты про одно и то же (2+ общих слова) — не повторяем."""
    return len(_words(a) & _words(b)) >= 2


def staff_summary(r: dict, card_text: str, card: dict | None = None) -> str:
    if "points" in r:   # старый формат ответа — тоже принимаем
        pts = r.get("points")
        if isinstance(pts, str):
            pts = [x.strip(" •-*\t") for x in re.split(r"\n+", pts)]
        pts = pts if isinstance(pts, list) else []
    else:
        pts = [r.get(k) for k in SUMMARY_FIELDS]
    out = []
    for p in pts:
        if not isinstance(p, str) or p.strip().lower() in ("", "null", "none", "нет", "нет данных"):
            continue
        p = text_field(p, "пункт", 300)
        if guard.has_decision(p) or re.search(r"гарантир", p, re.I):
            fail("ИИ дал решение вместо специалиста")
        extra = guard.unknown_numbers(p, card_text, "из 100 баллов")   # «94 из 100» — шкала, а не выдумка
        if extra:
            fail(f"в сводке числа, которых нет в карточке: {sorted(extra)}")
        out.append(p)
    if card is not None and len(out) < 3:
        for f in card_facts(card):
            if len(out) >= 3:
                break
            if not any(_similar(f, o) for o in out):
                out.append(f)
    out = out[:5]
    if len(out) < 3:
        fail(f"нужно 3–5 пунктов, пришло {len(out)}")
    return "\n".join(f"• {p}" for p in out)
