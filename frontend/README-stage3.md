# Этап 3: выписка, анкета вместо выписки, выбор цели

Продолжает этап 2, не требует готового FastAPI для просмотра оформления.

## Где смотреть

После обновления frontend/ и запуска `npm run dev`:

- http://localhost:3000/preview — меню предпросмотра.
- http://localhost:3000/preview/statement — выбор CSV и переключение на анкету «Нет выписки».
- http://localhost:3000/preview/goals — выбор цели для действующего ИП.
- http://localhost:3000/preview/goals/new-business — выбор «Открыть бизнес».

**Важно:** эти адреса только для просмотра. Они не создают заявку, не отправляют форму и не подменяют `nextAction`. В реальном `/applications/:id` выписка показывается только при `nextAction=UPLOAD_STATEMENT`, а цели — при `nextAction=SET_GOALS`.

## Реальное API-поведение (по имеющемуся OpenAPI)

- `POST /api/applications/{id}/statement` — отправка CSV в поле multipart/form-data `file`; ответ `StatementSummary`. Затем GET заявки для актуального `nextAction`.
- `POST /api/applications/{id}/questionnaire` — JSON `Questionnaire` с полями из сгенерированных типов; ответ `Application` с `nextAction`.
- `GET /api/demo/statements/{inn}` — скачать тестовую выписку только при наличии ИНН, полученного от сервера.
- `GET /api/question-sets` — список целей. В текущем контракте он описан как `object`, поэтому до добавления точной схемы и согласования разделения inventory.amount **сохранение целей отключено**. Макет целей в предпросмотре получает названия из приложенного `question-sets.json`, а реальный экран читает API.

Ошибки отображают `message` сервера. Бизнес-переходы не рассчитываются в React. Мок Prism не хранит состояние заявок и не обязан переходить на следующий экран.

## Установка на Mac с предыдущего этапа

Разархивируйте `alfa_frontend_stage3.zip` в `~/Downloads/alfa_stage3_patch`, затем скопируйте поверх уже существующей `~/Downloads/frontend`:

```bash
cd ~/Downloads
unzip -o alfa_frontend_stage3.zip -d alfa_stage3_patch
rsync -av alfa_stage3_patch/frontend/ frontend/
cd frontend
npm run dev
```

Скопируется и исправление из предыдущего этапа для недостоверных строк `string` в ответах Prism. Ваш `package-lock.json` **не затрагивается** и остаётся в `frontend/`. Если при старте не установлены зависимости, выполните `npm install` один раз.

## Проверки

- Откройте `/preview/statement`: выберите CSV и нажмите «У меня нет выписки»; проверьте изменение полей при галочке «Есть кредиты».
- Откройте `/preview/goals`: нажмите на карточку цели. Кнопка «Продолжить к вопросам» пока неактивна по требованиям контракта.
- Проверьте узкое окно Chrome: карточки и поля должны быть в одну колонку.
- В Terminal: `npm run typecheck` и `npm run build`. Итоговую сборку следует проверить на вашем Mac: в среде генерации npm-реестр не отвечает.

Исправления в команде ожидаются в общем `openapi.yaml` и `question-sets.json`; поля в TypeScript-файлах не копируем вручную. Все денежные значения — целые рубли, без SMS и писем.
