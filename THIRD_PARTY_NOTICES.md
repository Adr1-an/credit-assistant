# Сторонние компоненты

Проект использует следующие сторонние программы, сервисы и модели. Их код в репозиторий не скопирован: пакеты и образы скачиваются при сборке.

## ИИ

| Компонент | Для чего | Лицензия / условия |
| --- | --- | --- |
| [GigaChat API](https://developers.sber.ru/portal/products/gigachat-api) (ПАО Сбербанк), модель `GigaChat-2-Max` | Основная модель ИИ | Условия использования GigaChat API. Ключ хранится только в `.env` на сервере |
| [gpt2giga](https://github.com/ai-forever/gpt2giga) | Прокси: принимает запросы по стандарту OpenAI и передаёт их в GigaChat | MIT |
| [GigaChat 3.1 Lightning](https://huggingface.co/ai-sage) (GGUF) через [Ollama](https://ollama.com) | Необязательный вариант: открытая модель на своём компьютере | См. карточку модели на Hugging Face; Ollama — MIT |

## Сервер и заглушки (Python)

| Пакет | Лицензия |
| --- | --- |
| Python | PSF License |
| FastAPI | MIT |
| Uvicorn | BSD-3-Clause |
| SQLAlchemy | MIT |
| psycopg | LGPL-3.0 |
| HTTPX | BSD-3-Clause |
| python-multipart | Apache-2.0 |
| pytest (только тесты) | MIT |

## Сайт (JavaScript)

| Пакет | Лицензия |
| --- | --- |
| React, React DOM | MIT |
| Vite, @vitejs/plugin-react | MIT |
| TypeScript | Apache-2.0 |
| openapi-typescript | MIT |
| @stoplight/prism-cli (только разработка) | Apache-2.0 |
| Node.js (сборка) | MIT |

## Инфраструктура

| Компонент | Лицензия |
| --- | --- |
| PostgreSQL | PostgreSQL License |
| nginx | BSD-2-Clause |
| Docker-образы `python`, `node`, `postgres`, `nginx` | Лицензии соответствующих проектов |

Сертификат Минцифры (`certs/`) скачивается с официального портала Госуслуг и в репозиторий не входит.

Все клиенты, паспорта, ИНН и выписки в `tests/` и `mocks/data/` — вымышленные.
