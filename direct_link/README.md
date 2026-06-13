# Модуль «Прямая ссылка» (async / aiogram)

Часть менеджера ботов. Внутри настроек каждого бота — переключатель
«Прямая ссылка». При включении:

- Генерируется одна постоянная `startapp`-ссылка на этот бот.
- Каждому открытию мини-аппа сравнивается `start_param` со ссылкой.
- Не совпало → пользователя редиректит на сторонний мини-апп.
- Бот перестаёт отвечать на `/start` (через middleware aiogram).

## Файлы

```
direct_link/
├── __init__.py
├── config.py                  — DirectLinkConfig
├── storage.py                 — async Protocol хранилища
├── db_template.py             — ЗАГЛУШКА: реализуй под свою БД
├── telegram.py                — verify_init_data
├── module.py                  — DirectLinkModule (FastAPI роуты + логика)
├── aiogram_integration.py     — DirectLinkMiddleware для блокировки /start
└── DirectLinkPanel.jsx        — React-компонент панели настроек
```

## Модель данных

```sql
CREATE TABLE direct_link_bots (
    bot_id          BIGINT PRIMARY KEY,
    enabled         BOOLEAN NOT NULL DEFAULT FALSE,
    startapp_token  TEXT    NOT NULL,
    token_version   INTEGER NOT NULL DEFAULT 1,
    created_at      BIGINT  NOT NULL,
    updated_at      BIGINT  NOT NULL
);
```

`startapp_token` создаётся один раз при первом обращении. `token_version`
растёт при ротации — инвалидирует все ранее выданные куки сразу.

## Подключение бэка

```python
from fastapi import FastAPI, Request, HTTPException
from direct_link import DirectLinkConfig, DirectLinkModule
from direct_link.db_template import HostDBStorage

app = FastAPI()

async def get_bot_token(bot_id: int) -> str | None:
    return await my_bots.get_token(bot_id)

async def get_bot_username(bot_id: int) -> str | None:
    return await my_bots.get_username(bot_id)

async def verify_admin(request: Request, bot_id: int) -> None:
    user = await current_user(request)
    if not user or not await user.owns_bot(bot_id):
        raise HTTPException(403)

direct_link = DirectLinkModule(
    DirectLinkConfig.from_env(),
    storage=HostDBStorage(my_db_pool),
    get_bot_token=get_bot_token,
    get_bot_username=get_bot_username,
    verify_admin=verify_admin,
)
direct_link.mount(app)
```

Все три колбэка — **async**.

## Интеграция с aiogram

```python
from aiogram import Dispatcher
from direct_link.aiogram_integration import DirectLinkMiddleware

dp = Dispatcher()
dp.message.middleware(DirectLinkMiddleware(direct_link))

# Дальше обычные хендлеры — middleware сам глушит /start, когда нужно.
```

Middleware смотрит `event.bot.id` и зовёт `module.is_enabled_for(bot_id)`.
Если модуль включён — апдейт с `/start` (включая `/start payload` и
`/start@BotName`) молча отбрасывается до твоих хендлеров. Остальные
команды и сообщения проходят без изменений.

## Переменные окружения

```
DIRECT_LINK_SESSION_SECRET=<длинная случайная строка>
DIRECT_LINK_REDIRECT_URL=https://t.me/uzmigrant_miniapp_bot?startapp=profile
DIRECT_LINK_MANUAL_URL=https://your.docs/manuals/direct-link
DIRECT_LINK_SESSION_MAX_AGE=2592000
DIRECT_LINK_INIT_DATA_TTL=86400
```

## API

### Публичные (зовёт миниапп)

| Метод | URL | Назначение |
|---|---|---|
| POST | `/dl/{bot_id}/auth/start` | Проверка initData + start_param |
| GET  | `/dl/{bot_id}/auth/me` | Проверка куки при повторных открытиях |

Ответ: `{ "mode": "granted" }` либо `{ "mode": "stub", "redirect_url": "..." }`.

### Админские (зовёт UI менеджера)

| Метод | URL | Назначение |
|---|---|---|
| GET  | `/dl/admin/{bot_id}` | Текущее состояние + ссылка |
| POST | `/dl/admin/{bot_id}/toggle` | `{enabled: bool}` |
| POST | `/dl/admin/{bot_id}/rotate` | Перевыпустить токен |

Авторизация — через `verify_admin`-колбэк.

## Фронт мини-аппа

```js
const tg = window.Telegram.WebApp;
tg.ready();

const r = await fetch(`/dl/${BOT_ID}/auth/start`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  credentials: "include",
  body: JSON.stringify({ init_data: tg.initData }),
});
const { mode, redirect_url } = await r.json();

if (mode === "granted") {
  renderApp();
} else {
  tg.openTelegramLink(redirect_url);
  tg.close();
}
```

## UI менеджера

```jsx
import DirectLinkPanel from "./direct_link/DirectLinkPanel";

<DirectLinkPanel
  botId={selectedBotId}
  onBack={() => navigate(`/bots/${selectedBotId}/settings`)}
/>
```
