"""Настройки сервера.

Все числа из правил (ставки, сроки, пороги, лимиты) живут здесь, а не в коде.
Каждое значение можно переопределить переменной окружения с тем же именем,
например KEY_RATE=15 или STARTUP_AUTO_APPROVE_LIMIT=250000.

Значения по умолчанию взяты из:
- contract/product-rules-v1.md, раздел 2 (продукты);
- contract/scoring-model-v1.md (пороги зон, стартап);
- contract/mocks-contract.md (таймаут заглушек, сроки актуальности данных).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, fields
from functools import lru_cache
from pathlib import Path

# backend/app/config.py → корень репозитория на два уровня выше папки app
REPO_ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default, cast):
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    if cast is bool:
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return cast(raw)


@dataclass(frozen=True)
class Settings:
    # ---------- инфраструктура ----------
    DATABASE_URL: str = "postgresql+psycopg://navigator:navigator@db:5432/navigator"
    MOCKS_URL: str = "http://mocks:8090"
    MOCKS_TIMEOUT_SECONDS: float = 5.0          # mocks-contract.md: «не дольше 5 секунд»
    CONTRACT_DIR: str = str(REPO_ROOT / "contract")
    TESTS_DIR: str = str(REPO_ROOT / "tests")
    EVALUATION_DATE: str = ""                   # YYYY-MM-DD; пусто — сегодняшняя дата
    CORS_ORIGINS: str = "http://localhost:3000"  # через запятую

    # ---------- актуальность внешних данных (mocks-contract.md, модель баллов 3.2) ----------
    BKI_MAX_AGE_DAYS: int = 30
    TAX_MAX_AGE_DAYS: int = 30
    TAX_DEBT_MINUS_LIMIT: int = 50000           # 1…50 000 — MINUS, больше — MANUAL
    BANKRUPTCY_MANUAL_YEARS: int = 5
    BKI_OVERDUE_LOOKBACK_MONTHS: int = 36
    BKI_CURRENT_OVERDUE_STOP_DAYS: int = 90     # текущая просрочка ≥90 → STOP
    BKI_HISTORIC_OVERDUE_MANUAL_DAYS: int = 90  # историческая просрочка ≥90 → MANUAL

    # ---------- процесс ----------
    REVIEW_SLA_DAYS: int = 2                    # ВРЕМЕННО (вопрос 6): срок ответа сотрудника
    SIGN_CODE_TTL_MINUTES: int = 10             # ВРЕМЕННО (вопрос 7): срок жизни кода подписи
    DIALOG_MAX_ATTEMPTS: int = 2                # statuses.md: после 2 сообщений без цели — ESCALATED

    # ---------- модель баллов: зоны и стартап ----------
    ZONE_GREEN_MIN: int = 80
    ZONE_RED_MAX: int = 39                      # total < 40 → RED
    GREEN_MIN_BUSINESS_AGE_MONTHS: int = 12
    STARTUP_BLOCK_MAX_AGE_MONTHS: int = 2       # ИП 0–2 полных месяца → блок стартапа
    STARTUP_AUTO_APPROVE_LIMIT: int = 200000
    STARTUP_GOOD_BKI_MAX_PAYMENT: int = 20000
    STARTUP_GOOD_BKI_MAX_REQUESTS: int = 1
    STARTUP_GOOD_BKI_MIN_LOAN_AGE_MONTHS: int = 12
    OTHER_IN_MAX_SHARE_PERCENT: int = 20
    INDUSTRY_MAX_AGE_MONTHS: int = 12

    # ---------- правила продуктов (product-rules-v1.md, раздел 2) ----------
    KEY_RATE: float = 14.0
    SPREAD_LEASING: float = 4
    SPREAD_INVESTMENT_LOAN: float = 5
    SPREAD_CREDIT_LINE: float = 6
    SPREAD_OVERDRAFT: float = 7
    SPREAD_STARTER_LOAN: float = 8
    GUARANTEE_FEE: float = 3.0
    TERM_LEASING: int = 36
    TERM_INVESTMENT_LOAN: int = 36
    TERM_CREDIT_LINE: int = 18
    TERM_OVERDRAFT: int = 12
    TERM_STARTER_LOAN: int = 24
    TERM_BANK_GUARANTEE: int = 12
    GRACE_MONTHS: int = 3
    LEASING_MIN: int = 300000
    ROUND: int = 10000
    DSCR: float = 1.3
    OVERDRAFT_SHARE: float = 0.30
    BUFFER_SHARE: float = 0.10
    SMALLER_SHARE: float = 0.60
    STRESS_REVENUE_SHARE: float = 0.80          # «при падении выручки на 20%» (и в модели баллов)
    MIN_SHARE: float = 0.10                     # «если не проходит даже 10% сметы»
    STAFF_MONTHS: int = 3
    RENT_MONTHS: int = 3
    SALARY_PER_EMPLOYEE: int = 60000
    MARKETING_DEFAULT_MONTHS: int = 3
    PARTNER_DISCOUNT: float = 20
    TENDER_EXECUTION_SHARE: float = 0.30
    STARTER_MAX: int = 1000000
    MIN_STATEMENT_MONTHS_FOR_OVERDRAFT: int = 6
    AUTO_RATE_DISCOUNT_SCORE: int = 90          # автоодобрение и ≥90 баллов → −1 п.п.
    AUTO_RATE_DISCOUNT: float = 1
    STAFF_RATE_MARKUP: float = 2
    PAYBACK_GOOD_SHARE: float = 0.75
    PAYBACK_BAD_SHARE: float = 1.5
    PAYBACK_BAD_MAX_MONTHS: int = 60
    PAYMENT_DAY_MAX: int = 28
    PENALTY_PERCENT_PER_DAY: str = "0,1"

    # ---------- после выдачи (product-rules-v1.md, раздел 8) ----------
    DROP_REVENUE_SHARE: float = 0.60
    DROP_THRESHOLD_SHARE: float = 0.70
    GROWTH_REVENUE_SHARE: float = 1.25
    GROWTH_MONTHS_IN_ROW: int = 3
    LIMIT_INCREASE_SHARE: float = 0.50
    INTEREST_ONLY_MONTHS: int = 2
    RESTRUCTURE_EXTRA_MONTHS: int = 6

    def spread(self, product: str) -> float:
        return float(getattr(self, f"SPREAD_{product}"))

    def term(self, product: str) -> int:
        return int(getattr(self, f"TERM_{product}"))

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


# Границы ответов анкеты и целей — scoring-model-v1.md, раздел 8 (серверная валидация MVP).
# (min, max) включительно. Ключ — questionId или поле Questionnaire.
ANSWER_LIMITS = {
    "questionnaire.monthlyRevenue": (0, 100_000_000),
    "questionnaire.monthlyExpenses": (0, 100_000_000),
    "questionnaire.otherLoansMonthlyPayment": (0, 50_000_000),
    "questionnaire.employees": (0, 500),
    "common.amount": (1, 50_000_000),
    "money": (0, 100_000_000),            # все остальные money-поля
    "money.positive": (1, 100_000_000),   # обязательные положительные бюджеты (ниже)
    "common.term": (1, 120), "location.breakEven": (1, 120), "start.breakEven": (1, 120),
    "marketing.months": (1, 60), "inventory.turnover": (1, 60),
    "tender.term": (1, 120),
    "months": (1, 120),                   # прочие months
    "location.staff": (0, 500),
    "cashgap.when": (1, 365),
    "start.experience": (0, 80),
    "number": (0, 100_000),               # прочие number (в текущих вопросах не встречаются)
    "text": (1, 1000),
    "start.city": (1, 120),
}
POSITIVE_MONEY = {"inventory.amount", "cashgap.amount", "tender.contract", "marketing.budget"}

# Шкалы 11 факторов — scoring-model-v1.md, разделы 2 и 4. Пары (порог, баллы), проверяются по порядку;
# если ни один порог не подошёл — 0 баллов. Знак сравнения указан в комментарии.
SCORING = {
    "MIN_MONTHS_FOR_FACTORS": 6,
    "WEAK_MONTH_SHARE": "0.70",                                  # месяц слабый, если выручка < 70% средней
    "BUSINESS_STABILITY": [(0, 15), (2, 10), (4, 5)],             # слабых месяцев ≤ порога
    "BUSINESS_REVENUE_TREND": [(10, 10), (-10, 7), (-25, 3)],    # изменение, % ≥ порога
    "BUSINESS_CASH_BUFFER": [(25, 15), (15, 10), (5, 5)],        # остаток, % ≥ порога
    "OWNER_OVERDUE_HISTORY": [(0, 20), (29, 15), (59, 8), (89, 3)],  # дней просрочки ≤ порога
    "OWNER_OVERDUE_NO_LOANS": 12,                                # loans = []
    "OWNER_BUSINESS_AGE": [(36, 6), (12, 4), (3, 2)],            # полных месяцев ≥ порога
    "OWNER_TAX_OK": 4, "OWNER_TAX_SMALL_DEBT": 2,
    "IDEA_VERIFIED_DEBT_COVERAGE": [("2", 10), ("1", 7), ("1/2", 3)],  # F/L ≥ порога
    "IDEA_COVERAGE_NO_LOANS": 10,                                # L = 0 и F > 0
    "IDEA_VERIFIED_STRESS_BUFFER": [(10, 10), (5, 7), (0, 3)],   # запас, % ≥ порога
    "INDUSTRY_BASE_RISK": {"LOW": 4, "MEDIUM": 2, "HIGH": 0},
    "INDUSTRY_REVENUE_TREND": [(5, 3), (-5, 2), (-15, 1)],       # рост, % ≥ порога
    "INDUSTRY_CLOSURE_RATE": [(5, 3), (10, 2), (20, 1)],         # доля закрытий, % < порога
    "BUSINESS_START_CREDIT_SEARCH": [(1, 10), (3, 5)],           # запросов БКИ ≤ порога
    "BUSINESS_START_DEBT_LOAD": [(0, 10), (20000, 7), (50000, 4)],  # платежей в месяц ≤ порога
}


@lru_cache
def get_settings() -> Settings:
    """Читает переменные окружения один раз и отдаёт готовые настройки."""
    values = {f.name: _env(f.name, f.default, type(f.default)) for f in fields(Settings)}
    return Settings(**values)
