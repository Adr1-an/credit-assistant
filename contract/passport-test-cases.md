# Паспортная заглушка: приёмочные тесты (вариант Б)

Статус: согласовано БА; проверить на тестовых синтетических данных до реализации.

## Эталонная запись в mocks/data/ (пример, не формат обязательного хранения)

```json
{
  "series": "4010", "number": "123456", "valid": true, "reason": null,
  "holder": {"lastName":"Иванова","firstName":"Мария","middleName":"Сергеевна","birthDate":"1988-05-20","issueDate":"2018-06-14"}
}
```

Сервис получает запрос с теми же семью полями, но эталон читает независимо из `mocks/data/passports.json`. Хранение `holder` в данных заглушки — тестовый пример, **не** часть HTTP ответа.

| Тест | Изменение запроса или эталона | Ответ `valid / holderMatch / mismatchFields` | Сервер |
| --- | --- | --- | --- |
| P01 | Полное совпадение | `true / true / []` | `PASSPORT_VALID / NONE` |
| P02 | `lastName=Иванов` вместо эталона | `true / false / [LAST_NAME]` | `PASSPORT_HOLDER_MISMATCH / MANUAL` |
| P03 | `birthDate=1988-05-21` | `true / false / [BIRTH_DATE]` | `MANUAL` |
| P04 | `issueDate=2018-06-15` | `true / false / [ISSUE_DATE]` | `MANUAL` |
| P05 | Эталон `valid=false, reason=LOST` | `false / null / []`, `reason=LOST` | `PASSPORT_INVALID / STOP`, `REJECTED` |
| P06 | Нет обязательных эталонных полей владельца | `true / null / []` | `PASSPORT_HOLDER_UNKNOWN / MANUAL` |
| P07 | Нет документа по серии+номеру | HTTP 404 `NOT_FOUND` | `MANUAL` без автоотказа |
| P08 | HTTP 503 / >5 сек | нет успешного ответа | `state=ERROR`, `CHECKING`, `RETRY_CHECKS` |
| P09 | `lastName=ИВАНОВА`, в эталоне `Иванова` | `true / true / []` | `NONE` |
| P10 | `lastName=Ёлкина`, в эталоне `Елкина` | `true / true / []` | `NONE` |
| P11 | Отчество отсутствует у обоих | `true / true / []` | `NONE` |
| P12 | Отчество отсутствует только в запросе | `true / false / [MIDDLE_NAME]` | `MANUAL` |
| P13 | Эталон `valid=true, reason=LOST` | некорректная комбинация | `PASSPORT_CHECK_CONFLICT / MANUAL` |
| P14 | Эталон `valid=false, reason=null` | некорректная комбинация | `PASSPORT_CHECK_CONFLICT / MANUAL` |

## Контрольные правила

- В `mismatchFields` одновременно несколько различий перечисляются в фиксированном порядке: `LAST_NAME`, `FIRST_NAME`, `MIDDLE_NAME`, `BIRTH_DATE`, `ISSUE_DATE`.
- Вариант `valid=false` с признанной причиной имеет приоритет над сравнением владельца.
- Отдельная проверка ФИО с ЕГРИП остаётся независимой.
- ФИО, паспорт и даты никогда не возвращаются из эталона в HTTP ответе заглушки.
