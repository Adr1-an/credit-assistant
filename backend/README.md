# Сервер (бэк)

Python 3.11+, FastAPI, SQLAlchemy, PostgreSQL (для запуска без Docker можно SQLite). Работает строго по `contract/`.

## Запуск без Docker

Все команды — из корня репозитория, если не сказано иначе.

1. Заглушки внешних сервисов (отдельное окно):
   ```
   python mocks/devserver.py
   ```
2. Зависимости сервера:
   ```
   cd backend
   python -m pip install -r requirements.txt
   ```
3. Настройки (Windows, командная строка `cmd`):
   ```
   set DATABASE_URL=sqlite:///./app.db
   set MOCKS_URL=http://localhost:8090
   set EVALUATION_DATE=2026-10-24
   ```
   В PowerShell: `$env:DATABASE_URL="sqlite:///./app.db"` и так далее. В Linux/macOS: `export DATABASE_URL=sqlite:///./app.db`.
4. Запуск (из папки `backend`):
   ```
   python -m uvicorn app.main:app --port 8000
   ```
5. Проверка: http://localhost:8000/api/health и http://localhost:8000/docs

ИИ выключен, пока не заданы `LLM_ENABLED=true` и `LLM_BASE_URL` (см. `.env.example` в корне и `contract/llm-contract.md`). Без ИИ всё работает через форму.

## Тесты

Из папки `backend`:
```
python -m pip install -r requirements-dev.txt
python -m pytest -q
```
Тесты сами запускают заглушки и временную базу SQLite и сверяют 16 случаев с `tests/expected-results.json`.

## Устройство

| Папка | Что внутри |
| --- | --- |
| `app/main.py` | Точка входа, все запросы — под `/api` |
| `app/config.py` | Все числа правил (ставки, сроки, пороги) — меняются переменными окружения |
| `app/routers/` | Запросы API |
| `app/services/` | Проверки, выписка, баллы, смета, предложения, договор, кабинет сотрудника, после выдачи |
| `app/ai/` | Блок ИИ (владелец — человек 4), бэк только вызывает его функции |
| `tests/` | Автотесты сервера |
