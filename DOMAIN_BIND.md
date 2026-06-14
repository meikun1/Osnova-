# Привязка своего домена

Пошаговая инструкция, как привязать свой домен к боту через Cloudflare + Caddy.

---

## 1. Что нужно подготовить

1. **Купленный домен** у любого регистратора (Namecheap, REG.RU, GoDaddy, …).
2. **Аккаунт Cloudflare** — бесплатный тариф подходит. Регистрация: <https://dash.cloudflare.com/sign-up>.
3. **API Token Cloudflare** (Bearer):
   - Cloudflare Dash → **My Profile** → **API Tokens** → **Create Token**
   - Шаблон **«Edit zone DNS»**
   - Permissions (две строки):
     - `Zone` → `DNS` → `Edit`
     - `Zone` → `Zone` → `Read`
   - Zone Resources: `Include` → `All zones`
   - **Continue → Create Token → скопировать значение** (показывается один раз).

---

## 2. Переменные окружения

Бот читает настройки из env. Пропишите перед запуском:

| Переменная | Назначение | Пример |
|---|---|---|
| `DOMAIN_CF_TOKEN` | API Token из шага 1.3 | `cfut_abc123...` |
| `DOMAIN_SERVER_IP` | Публичный IP вашего сервера | `1.2.3.4` |
| `DOMAIN_CADDYFILE` | Абсолютный путь к Caddyfile | `/etc/caddy/Caddyfile` |
| `DOMAIN_CADDY_EXE` | Путь к бинарю Caddy | `/usr/local/bin/caddy` |
| `DOMAIN_TARGET` | Куда reverse_proxy шлёт трафик | `127.0.0.1:8000` |

На Railway это вкладка **Variables**. Локально — `.env` или `export ...` перед `python bot.py`.

---

## 3. Caddy

Нужен кастомный билд Caddy с модулем `github.com/caddy-dns/cloudflare` (для DNS-01 challenge).

```bash
go install github.com/caddyserver/xcaddy/cmd/xcaddy@latest
xcaddy build --with github.com/caddy-dns/cloudflare
```

В корне Caddyfile должен быть глобальный блок с ACME-issuer:

```caddy
{
    email YOUR_EMAIL@gmail.com
    cert_issuer acme {
        dns cloudflare {
            api_token YOUR_CF_API_TOKEN
        }
    }
}

:80 {
    redir https://{host}{uri} 301
}
```

Замените `YOUR_EMAIL@gmail.com` и `YOUR_CF_API_TOKEN` на реальные значения. Дальше бот сам дописывает per-domain блоки.

Запустите Caddy так, чтобы он слушал HTTP API на `127.0.0.1:2019` (стандарт):

```bash
caddy run --config /etc/caddy/Caddyfile
```

---

## 4. Привязка из бота

1. В главном меню нажмите **🌐 Привязать свой домен**.
2. Отправьте доменное имя без `http://` и без `www`:
   ```
   example.com
   ```
3. Бот выполнит:
   - создаст зону в Cloudflare,
   - добавит `A`-запись `example.com → DOMAIN_SERVER_IP` (proxied),
   - включит SSL **Strict** + отключит Browser Integrity Check / Bot Fight Mode,
   - допишет блок в Caddyfile и сделает `caddy reload`,
   - вернёт **NS-серверы Cloudflare**.

---

## 5. Прописать NS у регистратора

Бот в ответном сообщении выдаст пару NS-серверов вида:

```
isla.ns.cloudflare.com
kirk.ns.cloudflare.com
```

Зайдите в личный кабинет регистратора домена → раздел **DNS / Name Servers** →
замените текущие NS на те, что прислал бот → сохраните.

Распространение NS обычно занимает **от 1 до 24 часов**.
После этого Caddy сам выпустит SSL-сертификат через DNS-01 — никаких ручных действий не нужно.

---

## 6. Проверка

- `https://example.com` открывается — бот работает на вашем домене.
- В Cloudflare dashboard зона **Active** (зелёная).
- В логах Caddy — успешный выпуск сертификата от Let's Encrypt.

---

## Возможные ошибки

| Сообщение бота | Что значит | Что делать |
|---|---|---|
| `Невалидный формат домена` | Пример `example.com`, не `https://...` | Отправить чистое имя |
| `Этот домен уже зарегистрирован в другом Cloudflare-аккаунте` | Зона занята | Удалить в чужом аккаунте или использовать другой домен |
| `Caddy reload не прошёл` | Битый Caddyfile или Caddy не запущен | Проверить syntax: `caddy validate --config <path>` |
| `Cloudflare API: ...` | Невалидный токен / нет прав | Перепроверить шаг 1.3 |

---

## Удаление домена

Делается вручную (UI пока нет):

```python
from domain_flow import remove_domain_from_caddy, reload_caddy, cf_get_zone_id, cf_delete_zone
import config

remove_domain_from_caddy("example.com", config.DOMAIN_CADDYFILE)
reload_caddy(config.DOMAIN_CADDY_EXE, config.DOMAIN_CADDYFILE)

zone_id = cf_get_zone_id("example.com", config.DOMAIN_CF_TOKEN)
if zone_id:
    cf_delete_zone(zone_id, config.DOMAIN_CF_TOKEN)
```
