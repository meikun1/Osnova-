# Auth API — авторизация Telegram-аккаунта из мини-аппа

Эндпоинты подключены к основному FastAPI-приложению (`web/app.py`).
Все ответы возвращают объект состояния:

```json
{
  "sid": "abc123...",
  "state": "wait_code | wait_password | code_expired | success | failed | expired",
  "phone": "+79991234567",
  "code_attempts_left": 3,
  "pwd_attempts_left": 3,
  "error": null,
  "flood_wait": 0,
  "session_path": null
}
```

## Поток

```
1. POST /auth/send_code        { tg_user_id, phone }      → state=wait_code
2. POST /auth/submit_code      { sid, code }              → state=checking_code
   ↓ (фронт поллит /auth/status/{sid} раз в 500-800мс с loader'ом)
   → wait_password | wait_code(code_invalid) | code_expired | success | failed
3. POST /auth/submit_password  { sid, password }          → state=checking_password
   ↓ (поллинг с loader'ом)
   → success | wait_password(password_invalid) | failed
```

**Важно:** `submit_code` и `submit_password` НЕ ждут результат — они мгновенно возвращают `state=checking_*` и запускают проверку в фоне. Это значит, что фронт всегда успевает показать анимацию загрузки. Реальный результат фронт получает через `/auth/status/{sid}`.

Дополнительно:

| Эндпоинт                  | Когда                                                      |
| ------------------------- | ---------------------------------------------------------- |
| `POST /auth/resend_code`   | если `state=code_expired` или просто хочется новый код   |
| `GET  /auth/status/{sid}`  | поллинг состояния с фронта                                 |
| `POST /auth/cancel`        | отмена флоу                                                |

## Логика проверок

- **Неверный код** → 400, `error="code_invalid"`, `code_attempts_left` уменьшается; остаёмся в `wait_code`. После `MAX_CODE_ATTEMPTS` (по умолч. 3) → `state=failed`, `error="too_many_code_attempts"`.
- **Код истёк** → `state=code_expired`. Фронт показывает кнопку "Отправить заново" → `/auth/resend_code`.
- **Нужен 2FA** → `state=wait_password`.
- **Неверный пароль 2FA** → 400, `error="password_invalid"`. После `MAX_PWD_ATTEMPTS` → `failed`.
- **Flood wait** → `state=failed`, `error="flood_wait"`, `flood_wait=<секунды>`.
- **Таймаут всего флоу** (`AUTH_SESSION_TTL`, по умолч. 600 с) → `state=expired`. Сборщик мусора закрывает клиент.
- **Успех** → `state=success`, `session_path` указывает на `.session` файл в `SESSIONS_DIR`.

## Хранилище сессий

`.session` файлы сохраняются в `SESSIONS_DIR` (env, по умолч. `./sessions/`). Имя — номер без `+`. Это отдельный от БД мини-аппа каталог, как и просили.

Состояния флоу хранятся в памяти процесса (dict + asyncio.Lock на каждую). Для нескольких воркеров — вынести в Redis (заменить `_SESSIONS` на redis-клиент с теми же ключами).

## ENV

| Переменная           | По умолч.        |
| -------------------- | ---------------- |
| `SESSIONS_DIR`       | `./sessions`     |
| `PROXIES_FILE`       | `./proxys.txt`   |
| `AUTH_SESSION_TTL`   | `600` (сек)      |
| `MAX_CODE_ATTEMPTS`  | `3`              |
| `MAX_PWD_ATTEMPTS`   | `3`              |

## Пример клиента (JS, мини-апп)

```js
async function startAuth(phone) {
  const tgUserId = Telegram.WebApp.initDataUnsafe.user.id;
  const r = await fetch("/auth/send_code", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ tg_user_id: tgUserId, phone })
  });
  return r.json();   // → { sid, state: "wait_code", ... }
}

async function sendCode(sid, code) {
  const r = await fetch("/auth/submit_code", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ sid, code })
  });
  const data = await r.json().catch(() => null) ?? (await r.json());
  // r.ok=false при code_invalid — читаем r.json() и показываем error+attempts_left
  return data;
}

async function send2fa(sid, password) {
  const r = await fetch("/auth/submit_password", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ sid, password })
  });
  return r.json();
}
```

На фронте:

- `state === "wait_code"` → показываем поле ввода кода + счётчик попыток.
- `state === "code_expired"` → кнопка «Запросить новый код» (`/auth/resend_code`).
- `state === "wait_password"` → форма для 2FA.
- `state === "success"` → 🎉.
- `state === "expired" || "failed"` → текст ошибки по полю `error`.
