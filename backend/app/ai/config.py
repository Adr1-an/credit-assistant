"""Настройки блока ИИ из переменных окружения (contract/llm-contract.md)."""
import os
from dataclasses import dataclass


def _bool(v: str | None, default: bool) -> bool:
    if v is None or v.strip() == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _float(v: str | None, default: float) -> float:
    try:
        return float(v) if v not in (None, "") else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    enabled: bool
    base_url: str
    api_key: str
    model: str
    timeout: float
    temperature: float


def load() -> Settings:
    """Читается при каждом вызове: настройки можно менять без перезапуска тестов."""
    base = os.environ.get("LLM_BASE_URL", "").strip().rstrip("/")
    return Settings(
        # Без адреса ИИ считается выключенным: у жюри без .env всё работает через форму
        enabled=_bool(os.environ.get("LLM_ENABLED"), default=False) and bool(base),
        base_url=base,
        api_key=os.environ.get("LLM_API_KEY", "").strip(),
        model=os.environ.get("LLM_MODEL", "GigaChat-2-Max").strip(),
        timeout=_float(os.environ.get("LLM_TIMEOUT_SECONDS"), 30.0),
        temperature=_float(os.environ.get("LLM_TEMPERATURE"), 0.2),
    )
