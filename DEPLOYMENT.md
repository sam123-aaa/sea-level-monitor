# Развёртывание Sea Level Monitor

Приложение использует SQLite. Перед запуском на Render задайте секретные переменные среды:

- `SECRET_KEY` — случайная строка не менее 32 байт;
- `ADMIN_USERNAME` и `ADMIN_PASSWORD` — имя и уникальный пароль администратора;
- `ADMIN_EMAIL` — необязательный адрес администратора;
- `SQLITE_PATH` — путь к файлу базы внутри постоянного диска;
- `BACKUP_PATH` — каталог резервных копий на постоянном диске.

Подключите постоянный диск Render и укажите его путь в `SQLITE_PATH` и `BACKUP_PATH`. Если переменные администратора не заданы, известная демонстрационная учётная запись отключается, а новые пользователи автоматически не создаются. При повторном запуске приложения пароль существующего администратора не меняется, кроме старой учётной записи из репозитория, которая заменяется паролем из окружения.

Локальный запуск после установки `requirements.txt`:

```powershell
$env:SECRET_KEY = "replace-with-a-random-secret"
$env:ADMIN_USERNAME = "admin"
$env:ADMIN_PASSWORD = "replace-with-a-unique-password"
python app.py
```

Обмен небольшими CSV-файлами:

```powershell
python scripts/csv_exchange.py export tide_gauges work/stations.csv
python scripts/csv_exchange.py import tide_gauges work/stations.csv
```

Резервное копирование через веб-интерфейс требует JWT администратора уровня 5. Каталог резервных копий не заменяет копирование на отдельное хранилище.
