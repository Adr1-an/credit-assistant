"""ЗАГЛУШКА пакета ИИ. Её заменит человек 4 (contract/llm-contract.md).

Сигнатуры функций — точно как в контракте. Пока каждая функция бросает AIUnavailable,
а сервер в ответ включает запасной вариант: форма вместо чата, готовые ответы FAQ,
aiSummary = null и т.д. Так бэк полностью работает без ИИ.
"""
from typing import Optional  # noqa: F401  (как в контракте)


class AIUnavailable(Exception):
    """ИИ выключен, не ответил, или ответ не прошёл проверку. Сервер включает запасной вариант."""


def is_available() -> bool:
    return False


def dialog_step(context: dict, history: list[dict], question_sets: dict) -> dict:
    """Шаги 5–6. Следующий вопрос или сводка. Возвращает DialogStepResult."""
    raise AIUnavailable("Заглушка: ИИ ещё не подключён")


def suggest_okved(text: str, okved_catalog: list[dict]) -> list[dict]:
    """До 3 кодов ОКВЭД из okved_catalog. Возвращает [{code, name}]."""
    raise AIUnavailable("Заглушка: ИИ ещё не подключён")


def categorize_transactions(rows: list[dict], categories: list[str]) -> list[dict]:
    """Разложить операции выписки по категориям, которые не распознали правила."""
    raise AIUnavailable("Заглушка: ИИ ещё не подключён")


def explain_contract(contract: dict, question: str) -> str:
    """Ответ на вопрос «Что будет, если…» по договору этого клиента."""
    raise AIUnavailable("Заглушка: ИИ ещё не подключён")


def staff_summary(card: dict) -> str:
    """Короткая сводка для сотрудника: на что обратить внимание."""
    raise AIUnavailable("Заглушка: ИИ ещё не подключён")
