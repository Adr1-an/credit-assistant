# Этап 7 — кабинет сотрудника

## Что есть

- `/staff`: реальные заявки из `GET /api/staff/applications`, фильтры по `status` и `zone`, заявки с `needsAttention` сверху.
- `/staff/applications/:id`: данные `GET /api/staff/applications/{id}`: проверки, выписка с графиком и таблицей, цели и ответы, смета, скоринг с причинами, рекомендация, сводка ИИ (или причины из правил), история.
- Четыре решения: `APPROVE`, `CHANGE_TERMS`, `REQUEST_INFO`, `REJECT` через `POST /api/staff/applications/{id}/decision`. Комментарий обязателен. В режиме настоящей заявки отправка разрешена только для `MANUAL_REVIEW`, как в statuses.md.
- Без регистрации и паролей, по договорённости команды. Баллы и причины доступны только в кабинете сотрудника.
- Адаптивная вёрстка для узких экранов.

## Предпросмотр без бэкенда

- `/preview/staff` — синтетический список с фильтрами.
- `/preview/staff/application` — синтетическая карточка с графиком и заполняемой формой решений. Отправка решения отключена.

В живых маршрутах `/staff` нет хардкоденных заявок, баллов и решений. Все данные только от API. Примеры из `staffDemo.ts` подключены исключительно к путям `/preview/...`.

## Установка на Mac поверх этапа 6

Рекомендуется патч `ALFA_STAGE7_PATCH.zip`, поскольку именно в папке `~/Downloads/alfa_stage6/frontend` уже установлен и проверен `package-lock.json`.

```bash
cd ~/Downloads
unzip -o ALFA_STAGE7_PATCH.zip -d alfa_stage7_patch
rsync -av alfa_stage7_patch/frontend/ alfa_stage6/frontend/
cd alfa_stage6/frontend
npm run typecheck
npm run build
npm run dev
```

Если вы удалили этап 6, используйте полный архив `ALFA_STAGE7_FULL.zip`:

```bash
cd ~/Downloads
unzip -o ALFA_STAGE7_FULL.zip -d alfa_stage7
cd alfa_stage7/frontend
npm install
npm run typecheck
npm run build
npm run dev
```

Не выполняйте `npm audit fix --force` без отдельной проверки совместимости. Сохраните `package-lock.json` в Git.

## Важные границы

- `source`, `points`, `code`, `zone`, `status`, `nextAction`, `needsAttention`, `action` и все остальные данные получаем из сгенерированных типов OpenAPI.
- Ошибки показываем по полю `message`; `ApiError` хранит `code` для сценарной логики.
- Список отображает ответы сервера, а решения никогда не пересчитываются на фронтенде.
- Текущий контракт `question-sets` не типизирован полностью: для подписей вопросов в карточке дополнительно используем `GET /api/question-sets` с проверкой формата. При недоступности справочника показываем коды вопросов.
- Если LLM не дал сводку (`aiSummary: null`), показываем `score.flags` / причины `score.factors`, а не придуманную сводку.
- Для полной интеграции потребуется свежий OpenAPI от команды и Python-сервер. Prism не хранит изменения статусов.

## Проверки

1. Откройте `/preview/staff`. Спорные заявки расположены первыми, фильтры работают.
2. Нажмите «Открыть заявку»: появится карточка `/preview/staff/application`.
3. Прокрутите до графика и убедитесь, что его числовые данные есть в таблице.
4. Проверьте переключение всех четырёх действий и дополнительные поля. В предпросмотре отправка отключена.
5. На `/staff` должен выполняться запрос к `/api/staff/applications`, а не подставляться вымышленные заявки.
6. Выполните `npm run typecheck` и `npm run build`. Проверка успешна, если обе команды заканчиваются без ошибок.
