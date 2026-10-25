# Сертификат Минцифры для GigaChat

GigaChat использует сертификат Национального удостоверяющего центра (Минцифры). Без него прокси gpt2giga не может связаться с GigaChat и пишет ошибку `CERTIFICATE_VERIFY_FAILED`.

1. Скачайте корневой сертификат с портала Госуслуг: https://www.gosuslugi.ru/crt (файл `russian_trusted_root_ca_pem.crt`). Подробнее: https://developers.sber.ru/docs/ru/gigachat/certificates
2. Положите файл в эту папку: `certs/russian_trusted_root_ca_pem.crt`.
3. В `.env` должна быть строка `GIGACHAT_CA_BUNDLE_FILE=/certs/russian_trusted_root_ca_pem.crt`.

Сертификат — открытый файл, но в репозиторий его не кладём: каждый скачивает его с официального сайта.
