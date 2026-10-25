# Этап 5 — результаты рассмотрения и статус заявки

Добавлено поверх этапа 4:

- `WAIT`: трекер заявки и ожидание ответа, дата из `Application.reviewDeadline` (без выдуманного времени).
- `CHOOSE_OFFER`: `GET /api/applications/{id}/offers`, основное и альтернативные предложения, `POST /api/applications/{id}/offers/{offerId}/select`.
- `ANSWER_INFO_REQUEST`: сообщение из `Application.infoRequest.text`, форма ответа и необязательный файл; `POST /api/applications/{id}/info-response`.
- `NONE` при `REJECTED`: деликатный текст и советы **только** из `Application.rejection`.
- `NONE` при `ISSUED`: подтверждение текущего статуса (график платежей — следующий этап).

Каждый реальный экран открывается по `nextAction` из ответа сервера, а не по вычислению браузера. После действий используем возвращённую `Application`. Трекер использует `status` исключительно для отображения, не для переключения экранов. Баллы / формулы клиенту не показываем. HTTP-ошибки показываем по `message`.

## Предпросмотр без FastAPI

- `http://localhost:3000/preview/status` — заявка на рассмотрении;
- `http://localhost:3000/preview/offers` — предложения;
- `http://localhost:3000/preview/info-request` — запрос сведений;
- `http://localhost:3000/preview/rejection` — деликатный отказ.

В предпросмотре ВСЕ данные демонстрационные. Никакая кнопка не отправляет решения на сервер. Это не имитация сквозного процесса.

## Обновление на Mac без потери package-lock.json

Скачать `alfa_frontend_stage5_patch.zip` и запустить:

```bash
cd ~/Downloads
unzip -o alfa_frontend_stage5_patch.zip -d alfa_stage5_patch
rsync -av alfa_stage5_patch/frontend/ frontend/
cd ~/Downloads/frontend
npm run dev
```

В другом окне терминала после остановки Vite (`Control + C`):

```bash
npm run typecheck
npm run build
```

Патч **не содержит** ни `package.json`, ни `package-lock.json`, и не требует `npm install`. Не заменяйте рабочую папку содержимым только патча; патч нужно накладывать поверх этапа 4.

Если папка была удалена, скачайте **полный** `alfa_frontend_stage5.zip`, распакуйте в Downloads и выполните `npm install`. Тогда сохраните созданный `package-lock.json` в Git, чтобы сборка была воспроизводимой. В моём окружении npm-реестр недоступен, поэтому полноценную сборку не удалось подтвердить.

## Ограничения

- Prism возвращает схематические ответы и не хранит состояние заявок. Для реальных переходов необходим FastAPI.
- `SIGN`, после выдачи и кабинет `/staff` — последующие этапы.
- Новый контракт `question-sets` и разделение `inventory.amount` ещё нужны для включения сохранения целей из этапа 4.
- Никаких кодов скоринга, новых статусов, полей или переходов в OpenAPI не добавлено.
