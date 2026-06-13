# Запуск Osnova на своём VPS

Готовая инструкция под домен **najhgaor.xyz** и сервер **62.60.153.103**.
Весь стек (бот-менеджер + дочерние боты + мини-апп + PostgreSQL + HTTPS)
поднимается одной командой через Docker.

---

## Шаг 1. DNS (сделать заранее, ещё до запуска)

В панели домена `najhgaor.xyz` добавь запись:

| Тип | Имя | Значение | TTL |
|-----|-----|----------|-----|
| A   | `@` | `62.60.153.103` | Auto |

Проверь, что домен резолвится на сервер:
```bash
dig +short najhgaor.xyz      # должно вернуть 62.60.153.103
```
Без этого Caddy не сможет выпустить HTTPS-сертификат.

> Если на Cloudflare — поставь «облачко» в режим **DNS only** (серое).

---

## Шаг 2. Подготовка сервера

Подключись к VPS по SSH и склонируй проект:
```bash
git clone -b main https://github.com/meikun1/Osnova-.git osnova
cd osnova
```

---

## Шаг 3. Файл .env

Создай файл с настройками:
```bash
nano .env
```
Вставь содержимое, которое тебе дали в чате (там домен, пароли и секреты
уже заполнены). Останется вписать только **MANAGER_BOT_TOKEN** —
скопируй его из Railway → Variables (или из @BotFather).

Шаблон лежит в `.env.docker.example`.

---

## Шаг 4. Запуск

```bash
chmod +x deploy.sh
./deploy.sh
```
Скрипт сам поставит Docker (если нет), соберёт образ и поднимет всё.
Caddy автоматически выпустит HTTPS-сертификат для `najhgaor.xyz`.

Смотри логи:
```bash
docker compose logs -f app
```
Готово, когда увидишь `Менеджер запущен` и **нет** `TelegramConflictError`.

---

## Шаг 5. Выключи Railway

Когда бот поднялся на VPS — **останови сервис в Railway** (Stop/Remove),
иначе два инстанса с одним токеном будут конфликтовать (`getUpdates`).

---

## Управление

```bash
docker compose logs -f app      # логи
docker compose ps               # статус контейнеров
docker compose restart app      # перезапуск бота
docker compose down             # остановить всё
git pull && docker compose up -d --build   # обновить из репозитория
```

---

## Перенос данных из Neon (по желанию)

Если нужно сохранить ботов и статистику из Railway/Neon:
```bash
pg_dump "postgresql://USER:PASS@ep-xxx.neon.tech/db?sslmode=require" > dump.sql
docker compose exec -T db psql -U osnova -d osnova < dump.sql
```
Папку `sessions/` с уже полученными .session-файлами скопируй в volume
`sessions_data` (или положи рядом и перезапусти).

---

## Что где хранится

- **База** — в Docker volume `db_data` (Postgres).
- **Сессии** — в volume `sessions_data`.
- **Сертификаты** — в volume `caddy_data`.

Всё переживает перезапуск и обновление контейнеров.
