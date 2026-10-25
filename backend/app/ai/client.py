"""Запрос к модели по стандарту OpenAI Chat Completions (gpt2giga, Ollama, vLLM — без разницы).

Только стандартная библиотека Python: блоку ИИ не нужны дополнительные пакеты.
Любая проблема (выключено, нет ответа, не JSON) → AIUnavailable.
"""
import json
import re
import time
import urllib.error
import urllib.request

from . import config
from .errors import AIUnavailable

# Если прокси/модель не понимает response_format, запоминаем и дальше просим JSON только словами
_schema_unsupported = False
_health_cache: dict = {"at": 0.0, "ok": False, "key": None}
HEALTH_TTL_SECONDS = 30


def _request(url: str, s: config.Settings, body: dict | None, timeout: float) -> dict:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="GET" if body is None else "POST")
    req.add_header("Content-Type", "application/json")
    if s.api_key:
        req.add_header("Authorization", f"Bearer {s.api_key}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def is_available() -> bool:
    """ИИ включён и прокси отвечает. Результат кешируется на 30 секунд."""
    s = config.load()
    if not s.enabled:
        return False
    key = (s.base_url, s.api_key)
    now = time.monotonic()
    if _health_cache["key"] == key and now - _health_cache["at"] < HEALTH_TTL_SECONDS:
        return _health_cache["ok"]
    try:
        _request(f"{s.base_url}/models", s, None, timeout=min(3.0, s.timeout))
        ok = True
    except Exception:
        ok = False
    _health_cache.update(at=now, ok=ok, key=key)
    return ok


_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)


def _parse_content(content) -> dict:
    if not isinstance(content, str):
        raise AIUnavailable("Модель вернула не текст")
    m = _FENCE.match(content)
    if m:
        content = m.group(1)
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end < start:
        raise AIUnavailable("В ответе модели нет JSON-объекта")
    try:
        obj = json.loads(content[start:end + 1])
    except json.JSONDecodeError as e:
        raise AIUnavailable(f"Ответ модели — не JSON: {e.msg}") from None
    if not isinstance(obj, dict):
        raise AIUnavailable("Ответ модели — не JSON-объект")
    return obj


def chat_json(task: str, system: str, user: str, schema: dict) -> dict:
    """Отправить задачу модели и получить JSON-объект. Проверку смысла делает вызывающая функция."""
    global _schema_unsupported
    s = config.load()
    if not s.enabled:
        raise AIUnavailable("ИИ выключен (LLM_ENABLED=false или не задан LLM_BASE_URL)")
    schema_text = json.dumps(schema, ensure_ascii=False)
    body = {
        "model": s.model,
        "temperature": s.temperature,
        "messages": [
            {"role": "system", "content": f"{system}\n\nСхема ответа (JSON Schema):\n{schema_text}"},
            {"role": "user", "content": user},
        ],
    }
    if not _schema_unsupported:
        body["response_format"] = {"type": "json_schema",
                                   "json_schema": {"name": task, "schema": schema, "strict": True}}
    url = f"{s.base_url}/chat/completions"
    try:
        try:
            resp = _request(url, s, body, timeout=s.timeout)
        except urllib.error.HTTPError as e:
            if e.code in (400, 422) and "response_format" in body:
                # Прокси не принял структурированный вывод — один повтор без него
                _schema_unsupported = True
                body.pop("response_format")
                resp = _request(url, s, body, timeout=s.timeout)
            else:
                raise
        content = resp["choices"][0]["message"]["content"]
    except AIUnavailable:
        raise
    except urllib.error.HTTPError as e:
        raise AIUnavailable(f"Модель ответила ошибкой HTTP {e.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise AIUnavailable(f"Модель недоступна: {e}") from None
    except (KeyError, IndexError, TypeError, ValueError):
        raise AIUnavailable("Ответ модели не в формате OpenAI") from None
    return _parse_content(content)
