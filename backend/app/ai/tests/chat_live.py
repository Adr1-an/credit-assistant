"""Чат с ИИ-помощником прямо в консоли — без сайта и без бэка.

Нужен только запущенный gpt2giga и заполненный .env. Запуск из корня репозитория:
    python backend/app/ai/tests/chat_live.py            # клиент с действующим бизнесом
    python backend/app/ai/tests/chat_live.py --start    # клиент без бизнеса (открывает новый)

После каждого ответа показывается, что ИИ уже записал в итог (collected):
какие цели понял и какие ответы сохранил. Выход — пустая строка или «выход».
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def load_env(path: Path):
    if not path.is_file():
        sys.exit(f"Не найден {path}. Запускайте из корня репозитория, где лежит .env")
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env(ROOT / ".env")
os.environ.setdefault("CONTRACT_DIR", str(ROOT / "contract"))
sys.path.insert(0, str(ROOT / "backend" / "app"))

import ai  # noqa: E402

QS = json.loads((ROOT / "contract" / "question-sets.json").read_text(encoding="utf-8"))
QUESTIONS = {q["id"]: q["text"] for q in QS["common"]["questions"] + [q for g in QS["goals"] for q in g["questions"]]}
GOALS = {g["goalType"]: g["title"] for g in QS["goals"]}

START = "--start" in sys.argv
CONTEXT = {"hasBusiness": False} if START else {
    "hasBusiness": True, "okved": {"code": "13.92", "name": "Производство готовых текстильных изделий, кроме одежды"},
    "businessAgeMonths": 48, "avgMonthlyIncome": 1250000, "avgMonthlyExpense": 980000,
    "expenseByCategory": {"RENT": 120000, "SALARY": 560000, "MATERIALS": 210000}}


def show_collected(collected: dict):
    goals = collected.get("goals") or []
    if not goals:
        print("   [итог] цель пока не понята")
    for g in goals:
        print(f"   [итог] цель: {GOALS.get(g['goalType'], g['goalType'])}")
        for a in g["answers"]:
            v = "не знаю" if a["value"] is None else a["value"]
            print(f"          • {QUESTIONS.get(a['questionId'], a['questionId'])} → {v}")
    for a in collected.get("commonAnswers") or []:
        v = "не знаю" if a["value"] is None else a["value"]
        print(f"   [итог] общее: {QUESTIONS.get(a['questionId'], a['questionId'])} → {v}")


print(f"Модель: {os.environ.get('LLM_MODEL')}  ({'без бизнеса' if START else 'действующий бизнес'})")
if not ai.is_available():
    sys.exit("ИИ недоступен: проверьте, что gpt2giga запущен и в .env LLM_ENABLED=true")
print("Напишите, на что нужны деньги. Пустая строка — выход.\n")

history = []
while True:
    try:
        text = input("Вы: ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if not text or text.lower() in ("выход", "exit"):
        break
    history.append({"role": "CLIENT", "text": text})
    try:
        r = ai.dialog_step(CONTEXT, history, QS)
    except ai.AIUnavailable as e:
        print(f"   [ИИ не прошёл проверку] {e}")
        raw = getattr(ai.client, "last_content", None)
        if raw:
            print("   [что ответила модель]", str(raw)[:1500])
        history.pop()
        continue
    history.append({"role": "ASSISTANT", "text": r["assistantText"]})
    print(f"\nПомощник: {r['assistantText']}")
    if r["quickReplies"]:
        print("   [кнопки] " + " | ".join(r["quickReplies"]))
    print(f"   [состояние] {r['state']}, вопрос: {r['currentQuestionId']}")
    show_collected(r["collected"])
    if r["state"] == "SUMMARY":
        print(f"\n   [СВОДКА] {r['summaryText']}")
        print("   Дальше на сайте клиент нажмёт «Всё верно», и этот итог уйдёт в смету.")
        break
    if r["state"] == "ESCALATED":
        print("\n   [ИИ не понял цель] На сайте появятся кнопки целей.")
        break
    print()
