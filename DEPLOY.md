# Запуск на своём VPS одной командой (Docker)

Поднимает весь стек: бот-менеджер + дочерние боты + мини-апп (FastAPI),
PostgreSQL и Caddy с автоматическим HTTPS на твой домен.

## Требования
- VPS (Ubuntu/Debian), установленные **Docker** и **Docker Compose v2**.
- Домен, у которого DNS **A-запись** указывает на IP сервера.
- Открытые порты **80** и **443** (для HTTPS-сертификата и мини-аппа).

## Установка Docker (если ещё нет)
```bash
curl -fsSL https://get.docker.com | sh
```

## Запуск
```bash
git clone <твой-репозиторий> osnova && cd osnova
cp .env.docker.example .env
nano .env            # заполни DOMAIN, MANAGER_BOT_TOKEN, пароли, секрет
docker compose up -d --build
```

Готово. Caddy сам выпустит HTTPS-сертификат для `DOMAIN`,
приложение поднимется, база создастся автоматически.

## Полезные команды
```bash
docker compose logs -f app      # логи бота
docker compose ps               # статус контейнеров
docker compose restart app      # перезапуск бота
docker compose down             # остановить всё
docker compose up -d --build    # обновить после git pull
```

## Перенос данных из Neon (если нужно сохранить ботов/статистику)
```bash
# дамп из Neon
pg_dump "postgresql://USER:PASS@ep-xxx.neon.tech/db?sslmode=require" > dump.sql
# залить в локальную базу контейнера
docker compose exec -T db psql -U osnova -d osnova < dump.sql
```
Папку с уже полученными сессиями скопируй в volume `sessions_data`
(или просто положи .session-файлы и смонтируй).

## Важно
- Запущен **один** экземпляр — никакого `TelegramConflictError`.
- Когда переедешь на VPS, **выключи Railway** (иначе два инстанса с одним
  токеном будут конфликтовать).
- Данные (база, сессии, сертификаты) лежат в Docker volumes и переживают
  перезапуск/обновление.
