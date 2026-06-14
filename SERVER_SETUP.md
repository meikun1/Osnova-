# Запуск на сервере (docker compose)

Поднимает всё одной командой: бот-менеджер + Postgres + Caddy с плагином
Cloudflare. Бот сам пишет per-domain блоки в Caddyfile и делает горячий
reload через admin API.

---

## 1. Подготовка сервера

- Любой VPS / выделенный сервер с публичным **IPv4**.
- ОС: Ubuntu 22.04+ / Debian 12+ (или любой Linux с Docker).
- Открытые наружу порты: **80**, **443**.
- Установлен Docker + плагин compose:

  ```bash
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker $USER
  # переавторизуйся (logout/login), чтобы группа применилась
  ```

## 2. Клон репозитория

```bash
git clone https://github.com/meikun1/Osnova-.git
cd Osnova-
```

## 3. Заполнить `.env`

```bash
cp .env.docker.example .env
nano .env
```

Что **обязательно** заполнить:

| Переменная | Что вписать |
|---|---|
| `MANAGER_BOT_TOKEN` | Токен бота-менеджера из @BotFather |
| `DOMAIN_SERVER_IP` | Публичный IPv4 этого сервера (узнать: `curl ifconfig.me`) |
| `CADDY_ACME_EMAIL` | Любой ваш email — нужен Let's Encrypt'у для уведомлений |
| `POSTGRES_PASSWORD` | Любой стойкий пароль (например `openssl rand -hex 16`) |
| `DIRECT_LINK_SESSION_SECRET` | `openssl rand -hex 32` |

## 4. Заполнить `cf_pool.json`

Это **единственный файл, в котором лежат CF-токены**. Создай его из шаблона:

```bash
cp cf_pool.example.json cf_pool.json
nano cf_pool.json
```

Формат:

```json
[
  {"api_token": "cfut_твой_токен_1", "label": "acc-001"},
  {"api_token": "cfut_твой_токен_2", "label": "acc-002"}
]
```

Минимум — один токен. Как создать токен: см. `DOMAIN_BIND.md` →
раздел «Где создаётся Cloudflare API Token».

> Дубли по `api_token` при импорте пропускаются — файл можно просто
> дополнять и перезапускать стек, ничего не дублируется.

## 5. Запуск

```bash
docker compose up -d --build
```

Первый запуск длится 5–10 минут (Docker собирает кастомный Caddy с
плагином Cloudflare через xcaddy).

Логи:

```bash
docker compose logs -f app    # бот
docker compose logs -f caddy  # caddy
docker compose logs -f db     # postgres
```

В логах `app` должно появиться:

```
cf_pool: импорт завершён. Добавлено: N. В пуле всего: N, свободно: N.
Менеджер запущен.
```

## 6. Проверка боевого флоу

1. В Telegram открой своего бота-менеджера → `/start`.
2. Нажми **🌐 Привязать свой домен**, отправь домен (например `example.com`).
3. Бот вернёт **2 NS-сервера Cloudflare** — пропиши их у регистратора.
4. Жди распространения NS (15 мин – 24 ч, обычно ≤ 1 ч на `.xyz` / `.online`).
5. Как только Caddy выпустит сертификат — бот **сам пришлёт** «🔒 SSL-сертификат выпущен».
6. После этого кнопка **⚙️ Создать бота** разблокируется. Раньше — нет.

## 7. Обновления

```bash
git pull
docker compose up -d --build
```

База и Caddyfile в **именованных volume'ах**, обновление их не сносит.

## 8. Полный сброс (на свой страх)

```bash
docker compose down -v   # удалит и БД, и Caddyfile с выпущенными сертами
```

---

## FAQ / траблшут

**`caddy` не стартует, ругается на email** — проверь, что `CADDY_ACME_EMAIL`
в `.env` валидный.

**`app` ругается `CF_POOL: файл /app/cf_pool.json не найден`** — ты
запустил `docker compose up` до того, как создал `cf_pool.json` в корне
репо. Создай файл и пересоздай контейнер `app`:
```bash
docker compose up -d --force-recreate app
```

**Бот пишет «в пуле нет свободных аккаунтов»** — все токены из пула уже
закреплены за пользователями. Добавь новые в `cf_pool.json` и:
```bash
docker compose restart app
```

**SSL не выпускается даже через сутки** — у регистратора прописаны
не те NS, или NS не сохранились. Проверь:
<https://www.whatsmydns.net/> → введи свой домен → выбери `NS`.

**Хочу подменить домен мини-аппа** — выстави `MINIAPP_BASE_URL` в `.env`
и перезапусти `app`.
