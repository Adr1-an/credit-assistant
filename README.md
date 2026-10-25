# Бэкенд — «Умный финансовый навигатор для ИП»

Python 3.12, FastAPI, PostgreSQL. Делается строго по `contract/` v0.9. Порт 8000, все запросы под `/api`, Swagger на `/docs`.

**Готово всё, что есть в `openapi.yaml`: 33 запроса.** Список запросов и поля всех схем в нашем Swagger проверены программно — они совпадают с контрактом. На всех 16 тестовых клиентах результат совпадает с `tests/expected-results.json`: проверки, баллы по каждому фактору, зона, статус, причины MANUAL, смета, все предложения до рубля, рекомендация сотруднику, договор T01.

## Как проходит заявка (и где это в коде)

| Шаг | Запросы | Код |
| --- | --- | --- |
| 1. Паспорт и ИНН | `POST /applications`, `GET /applications/{id}` | `services/applications.py` |
| 2–3. Согласие, 6 проверок | `POST /consent`, `POST /checks` | `services/checks.py` — заглушки и корзины |
| 4. Выписка или анкета | `POST /statement`, `POST /questionnaire` | `services/statement.py` — разбор CSV |
| 5–6. Цели | `GET /question-sets`, `PUT /goals`, `GET/POST /dialog`, `POST /handoff`, `GET /okved`, `POST /okved/suggest` | `services/goals.py` — проверка ответов |
| 7. Смета | `GET/PUT /estimate` | `services/estimate.py` |
| 8. Решение | `POST /submit`, `POST /info-response` | `services/scoring.py` (баллы), `services/flow.py` (маршрут) |
| 9. Предложения | `GET /offers`, `POST /offers/{offerId}/select` | `services/offers.py` — ставки, график, безопасный платёж |
| 10. Договор и подпись | `GET /contract`, `POST /contract/ask`, `POST /sign/code`, `POST /sign` | `services/contract.py` |
| После выдачи | `GET /schedule`, `GET /notifications`, `POST /notifications/{id}/choose`, `POST /demo/applications/{id}/advance-month` | `services/after.py` |
| Сотрудник | `GET /staff/applications`, `GET /staff/applications/{id}`, `POST /staff/applications/{id}/decision` | `services/staff.py` |
| Демо | `GET /demo/clients`, `GET /demo/statements/{inn}`, `GET /health` | `routers/reference.py` |

`routers/` — тонкий слой: принять запрос, вызвать функцию из `services/`, отдать ответ. Вся логика — в `services/`.

## Остальные файлы

```
app/config.py    — ВСЕ числа из правил: ставки, сроки, пороги зон, шкалы 11 факторов, границы ответов.
                   Любую простую настройку можно поменять переменной окружения (KEY_RATE=15).
app/clock.py     — дата оценки (EVALUATION_DATE) и календарные месяцы
app/statuses.py  — статусы, тексты, разрешённые переходы (иначе 409), nextAction
app/schemas.py   — схемы из openapi.yaml. Ответ проходит через схему, поэтому лишнее
                   (например, баллы в клиентском Application) наружу попасть не может
app/models.py    — таблицы applications и history
app/texts.py     — тексты, которых нет в контракте (для клиента и сотрудника) — ждут БА
app/refdata.py   — чтение справочников contract/ и tests/ как данных (код оттуда не импортируется)
app/ai/          — ЗАГЛУШКА ИИ (см. ниже)
```

## Главные правила и как они соблюдены

- **ИИ ничего не решает.** Баллы, зона, смета, ставки — `scoring.py`, `estimate.py`, `offers.py`; ИИ туда не вызывается. Ответ ИИ в диалоге проверяется (известные `goalType`/`questionId`, типы значений). Не прошёл проверку — считаем, что ИИ недоступен (503).
- **Клиент не видит баллы.** `Application` в схеме не имеет таких полей; баллы — только в `/api/staff/...`. Заранее посчитанные для сотрудника предложения клиент не видит, пока сотрудник не одобрит (`GET /offers` → 409).
- **Числа — в настройках.** `config.py`: `Settings` (меняются через окружение), `SCORING` (шкалы факторов), `ANSWER_LIMITS` (границы ответов).
- **Дата оценки** — `EVALUATION_DATE`, иначе сегодня. Сохраняется в заявке вместе с результатом проверок.
- **Деньги — целые рубли, даты — YYYY-MM-DD, ошибки — `{code, message, details}`.** Ошибки FastAPI переведены в 400 `VALIDATION_ERROR`, ошибки паспорта — в `PASSPORT_INVALID`, ошибки ИНН — в `INN_INVALID`.
- **Точный расчёт.** Средние и доли считаются дробями (`Fraction`), поэтому на границах порогов нет ошибок округления.

## ИИ: папка `app/ai/` — заглушка

`app/ai/__init__.py` — **временная заглушка, её заменит человек 4**. В ней те же функции, что в `contract/llm-contract.md` (`is_available`, `dialog_step`, `suggest_okved`, `categorize_transactions`, `explain_contract`, `staff_summary`). `is_available()` возвращает `False`, остальные бросают `AIUnavailable`. Сервер включает запасной вариант:

- диалог → `503 AI_UNAVAILABLE`, сайт показывает форму;
- свой вопрос по договору → 503, готовые вопросы FAQ работают;
- подсказка ОКВЭД → 503, работает поиск `GET /okved`;
- в карточке сотрудника `aiSummary: null`.

Подстраховка из `statuses.md` уже есть: после 2 сообщений клиента без цели сервер сам ставит `ESCALATED`. `categorize_transactions` сервер не вызывает: по `llm-contract.md` его результат не влияет на расчёт.

## Запуск

### В Docker (для человека 4 — добавить в `docker-compose.yml`)

```yaml
  backend:
    build: ./backend
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: postgresql+psycopg://navigator:navigator@db:5432/navigator
      MOCKS_URL: http://mocks:8090
      EVALUATION_DATE: "2026-10-24"
    volumes:
      - ./contract:/contract:ro   # справочники: вопросы, отрасли, ОКВЭД, договор
      - ./tests:/tests:ro         # демо-клиенты и их выписки
    depends_on: [db, mocks]
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: navigator
      POSTGRES_PASSWORD: navigator
      POSTGRES_DB: navigator
```

Таблицы создаются сами при старте. ⚠️ Dockerfile написан, но не проверен сборкой: в среде разработки не было Docker. Соберите его один раз у себя.

### Без Docker

```
cd backend
pip install -r requirements.txt
python ../mocks/devserver.py &                      # заглушки на :8090
DATABASE_URL=postgresql+psycopg://navigator:navigator@localhost:5432/navigator \
MOCKS_URL=http://localhost:8090 EVALUATION_DATE=2026-10-24 \
uvicorn app.main:app --port 8000
```

## Переменные окружения

| Переменная | По умолчанию | Что это |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg://navigator:navigator@db:5432/navigator` | База |
| `MOCKS_URL` | `http://mocks:8090` | Заглушки |
| `MOCKS_TIMEOUT_SECONDS` | `5` | Сколько ждать заглушку |
| `EVALUATION_DATE` | пусто → сегодня | Дата оценки, в демо `2026-10-24` |
| `CONTRACT_DIR`, `TESTS_DIR` | `../contract`, `../tests` (в Docker `/contract`, `/tests`) | Где лежат справочники |
| `CORS_ORIGINS` | `http://localhost:3000` | С каких адресов можно ходить с браузера |
| `KEY_RATE`, `SPREAD_*`, `TERM_*`, `STARTUP_AUTO_APPROVE_LIMIT`, `ZONE_GREEN_MIN`, … | из правил | Полный список с пояснениями — `app/config.py` |

## Автотесты (95 штук)

```
cd backend
pip install -r requirements-dev.txt
python -m pytest -q                       # база — временный SQLite
TEST_DATABASE_URL=postgresql+psycopg://navigator:navigator@localhost:5432/navigator_test python -m pytest -q
```

Тесты сами поднимают заглушки (`mocks/devserver.py`, отдельным процессом).

| Файл | Что проверяет |
| --- | --- |
| `test_end_to_end.py` | 14 клиентов проходят воронку до submit через API. Сверяется всё из `expected-results.json`: баллы по факторам, зона, статус, причины MANUAL, смета, предложения, рекомендация. Для T01 весь путь дальше: договор слово в слово, FAQ, подпись, график, перемотка месяцев |
| `test_steps_1_3.py` | Все 16 случаев: проверки и корзины, статус после согласия. Плюс ИНН, паспорт, повторная заявка, 422 |
| `test_passport.py` | Паспортные тесты P01–P16 |
| `test_edge_cases.py` | Плохие выписки, пропущенный февраль, проверка ответов, правка сметы, handoff, все 4 решения сотрудника, запрос данных с новой выпиской, ИИ недоступен или «взломан», истёкший код, неверные статусы |

## Вопросы к контракту (временные решения)

Пока владелец продукта не ответил, сервер работает по варианту из этого списка. В коде такие места помечены `ВРЕМЕННО (вопрос N)`.

1. Тексты рекомендаций сотруднику: `action` — как в эталоне, текст — по `product-rules`, человеческими словами («не совпадает дата выдачи»; «проверьте — банкротство завершено менее 5 лет назад»).
2. `whyItFits` — как в эталоне `reference_offers.py`.
3. Стартап просит больше 1 000 000 → `termsChanged = true` (по правилам; эталон этого не делает).
4. `nextAction` в COLLECTING: после целей — `REVIEW_ESTIMATE`, после `PUT /estimate` — `SUBMIT`. Submit разрешён в обоих случаях.
5. Submit без целей или (у ИП) без выписки и анкеты → 409 `INVALID_STATUS`, `details.missing`.
6. Срок ответа сотрудника — `REVIEW_SLA_DAYS=2`.
7. Срок жизни кода подписи — `SIGN_CODE_TTL_MINUTES=10`.
8. Тексты проверок и советы при отказе — `app/texts.py`, ждут БА. `retryAfterMonths` не заполняется.
9. Заглушка ответила 404 «не найден» (налоги, БКИ, приставы, банкротство) → MANUAL.
10. CHANGE_TERMS: остаётся только MAIN; сумма округляется вниз до 10 000. APPROVE без построенного предложения (handoff, цель «Другое», не прошёл безопасный платёж) → 400.
11. После выдачи:
    - в месяц падения выручки платёж считается внесённым;
    - RESTRUCTURE только фиксируется + уведомление INFO (запроса для сотрудника в контракте нет);
    - вариант `OVERDRAFT` не предлагается;
    - рост лимита — только если в договоре есть овердрафт и есть выписка; новая средняя = 125% прежней.
12. Новая выписка в ответ на запрос данных → баллы и предложения пересчитываются для сотрудника, статус MANUAL_REVIEW.
13. Правка сметы: строка «Подушка» пересчитывается по правилу, если клиент не правил её сам.
14. `topCustomers`: топ-3 по ИНН (или по названию, если ИНН нет) среди подтверждённой выручки.
15. Две одинаковые цели → 400. Ограничений «стартап ↔ START_BUSINESS» нет.
16. `requestedAmount` в списке сотрудника: `common.amount`, иначе итог сметы.
17. Дата выдачи и первого платежа считается от `EVALUATION_DATE`.
18. `Contract.downloadUrl` не заполняется: запроса на скачивание полного договора нет.
19. `GET /demo/clients` отдаёт только поля схемы `DemoClient`; `code` (T01…) отсекается.
20. Сборка: `contract/` и `tests/` подключаются томами только для чтения.
21. В `ErrorCode` нет кода для непредвиденной ошибки сервера. 500 отдаёт `INTERNAL_ERROR` — нужно согласовать.
22. STOP и недоступный сервис одновременно → заявка остаётся в CHECKING (раздел 11 модели: сначала «сервис не ответил»).
23. Коды проверок и флагов придуманы бэком там, где контракт их не задаёт (`EGRIP_NAME_MISMATCH`, `TAX_STALE`, `BKI_HISTORIC_OVERDUE`, `FSSP_ACTIVE` и т.д.; тексты — `texts.FLAG_TEXT`). Часть совпадает с эталоном.
24. Порядок решения при submit:
    - красная зона → REJECTED;
    - цель «Другое» → MANUAL_REVIEW;
    - не хватает цены оборудования или суммы стартапа → INFO_REQUESTED «Укажите …»;
    - зелёная зона без прошедшего безопасного платежа → MANUAL_REVIEW (CHANGE_TERMS);
    - иначе по зоне.
25. `startSmallerSuggested` до отправки считается по базовым ставкам (без −1/+2), после submit — по итоговым.
26. Входящий JSON с неизвестными полями отклоняется (400). Фронту нельзя слать лишние поля.
27. Если ИИ не ответил, сообщение клиента в истории диалога не сохраняется.
28. Округление строк графика до рубля — как в эталоне: Python `round()` (на ровно 0,5 — к чётному).
