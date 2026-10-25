# Аудит фронтенда относительно контракта v1.2 (25.10.2026)

Источники: утверждённые `contract/README.md`, `contract/openapi.yaml`, `contract/statuses.md`, `contract/question-sets.json`, `contract/product-rules-v1.md`, `contract/llm-contract.md`. В этом ZIP менялись только файлы внутри `frontend/`.

## Таблица запросов

Все перечисленные ниже маршруты — **внутри префикса `/api`**. «Совпадало» означает: путь, метод и базовые транспортные поля уже соответствовали OpenAPI. Проверка с живым сервером отдельно не выполнена.

| Запрос | Было | Исправил / состояние |
| --- | --- | --- |
| GET `/health` | Уже использовался при вопросах по договору | Добавлена проверка `aiAvailable` для переключения ИИ/формы и подсказки ОКВЭД |
| POST `/applications` | 200/201 обрабатывались одинаково | Ответ различается по HTTP-коду: 200 показывает «У вас есть заявка от {дата}», 201 продолжает создание |
| GET `/applications/{id}` | Совпадало | Сохранена маршрутизация исключительно по `nextAction` |
| POST `/applications/{id}/consent` | Совпадало | Сохранены ожидание синхронных проверок и ошибки сервера |
| POST `/applications/{id}/checks` | Совпадало | Сохранена кнопка «Повторить» при `RETRY_CHECKS` |
| POST `/applications/{id}/statement` | Совпадало | Сохранена multipart-передача файла |
| POST `/applications/{id}/questionnaire` | Совпадало | Сохранена отправка анкеты JSON |
| GET `/question-sets` | Старый контракт описывал ответ как `object`, форму блокировали | Актуальная схема `QuestionSets`, динамическая форма, отправка подтверждённых ответов |
| GET `/applications/{id}/dialog` | Не было | Добавлена загрузка истории и состояний диалога |
| POST `/applications/{id}/dialog` | Не было | Добавлены отправка текста, `ASKING`, `SUMMARY`, `ESCALATED`, `quickReplies`; 503 переключает на форму |
| POST `/applications/{id}/handoff` | Не было | Передача сотруднику с `reason: GOAL_UNCLEAR` |
| PUT `/applications/{id}/goals` | Метод API был, но кнопка формы заблокирована | Подключено сохранение `GoalsData` для формы и сводки ИИ |
| GET `/okved` | Поиск уже был | Сохранено подтверждение кода пользователем |
| POST `/okved/suggest` | Не было | Добавлена необязательная подсказка только при `aiAvailable: true`, 503 скрывает подсказку |
| GET `/applications/{id}/estimate` | Совпадало | Сохранена загрузка сметы |
| PUT `/applications/{id}/estimate` | Совпадало | Сохранено редактирование строк целыми рублями |
| POST `/applications/{id}/submit` | Совпадало | Сохранён переход по ответу сервера |
| POST `/applications/{id}/info-response` | Совпадало | Сохранена multipart-отправка текста/файла |
| GET `/applications/{id}/offers` | Совпадало | Сохранены `whyItFits`, `termsChanged`, до 3 предложений |
| POST `/applications/{id}/offers/{offerId}/select` | Совпадало | Сохранён выбор предложения |
| GET `/applications/{id}/contract` | Совпадало | Сохранены пункты, summary, FAQ |
| POST `/applications/{id}/contract/ask` | Статический дисклеймер и общий текст ошибки | Дисклеймер берётся из `answer.disclaimer`; для AI_UNAVAILABLE показана фраза из ТЗ |
| POST `/applications/{id}/sign/code` | Совпадало | Сохранён экранный код без SMS |
| POST `/applications/{id}/sign` | Совпадало | Сохранена передача `code`, `understood` |
| GET `/applications/{id}/schedule` | Совпадало | Сохранён график после выдачи |
| GET `/applications/{id}/notifications` | Совпадало | Сохранены уведомления |
| POST `/applications/{id}/notifications/{notificationId}/choose` | Совпадало | Сохранён выбор реакции |
| GET `/staff/applications` | Совпадало | Сохранён список с приоритетом спорных заявок |
| GET `/staff/applications/{id}` | Баллы/история/смета уже были | Добавлены `breakEvenComparisons`, `handoff`, история диалога |
| POST `/staff/applications/{id}/decision` | Совпадало, кроме случая handoff → APPROVE | Для ручного одобрения handoff предлагается указать `newTerms` |
| GET `/demo/clients` | Совпадало | В карточках показаны паспорт и ИНН |
| GET `/demo/statements/{inn}` | Ссылка отсутствовала | Добавлена «Скачать выписку» при `hasStatement` |
| POST `/demo/applications/{id}/advance-month` | Совпадало | Сохранена демо-кнопка |

## Исправления без новых API-методов

- Обновлены локальные копии `openapi.yaml` и `question-sets.json` на согласованные версии. У вопроса `INVENTORY` используются `inventory.items` (текст) и `inventory.amount` (число) как в контракте, без старой блокировки.
- Vite по умолчанию слушает `3000`, прокси на `http://localhost:8000`, префикс `/api` сохраняется. nginx слушает `3000`, перенаправляет `/api` на `http://backend:8000`.
- Генератор типов и аудит ищут корневой `contract/openapi.yaml` и `contract/question-sets.json`, а не ошибочные `../openapi.yaml` и `../question-sets.json`.
- Исправлено отображение `retryAfterMonths: null`: больше не обещается повторное обращение через `null` месяцев.
- В форме нового бизнеса запрашивается личный ИНН, иначе после создания черновика нельзя успешно выполнить `consent` для шести проверок.
- Синтетические примеры допустимы **только** для страниц `/preview`. В рабочей воронке решения, баллы, смета, предложения и статусы берутся из сервера.

## Открытые вопросы / непроверенное

1. **Расхождение в контракте:** пример `contract/llm-contract.md` описывает `assistantText`, а `components.schemas.DialogState` в `contract/openapi.yaml` его не содержит. Согласовать с владельцем продукта, нужен ли этот атрибут в `DialogState`; пока клиент отображает `messages[]`.
2. **Сборка:** реестр npm недоступен в этой изолированной среде (ошибка DNS для `registry.npmjs.org`). В предоставленном архиве не было `package-lock.json`. Команды `npm install`, `npm run api:generate`, `npm run typecheck`, `npm run build`, Docker build с зависимостями остаются для проверки в сетевой среде; нельзя заявлять, что они прошли.
3. **Живой backend:** в доступных файлах серверные обработчики не были запущены. Поэтому не проверены реальные переходы после `saveGoals`, `handoff`, `sign` и `advance-month`. Проверку нужно провести на FastAPI и на 10 клиентах из `tests/`.
4. **Проверено локально:** синтаксис TS/TSX проверен штатным парсером TypeScript; тесты Node для smoke-утилиты — 3/3; аудит наличия маршрутов и актуальных контрактов — выполнен. Это статические проверки, не замена интеграционного теста.
