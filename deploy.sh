#!/usr/bin/env bash
# Запуск проекта на VPS одной командой.
#   chmod +x deploy.sh && ./deploy.sh
set -e
cd "$(dirname "$0")"

# 1. Docker (поставим, если его нет)
if ! command -v docker >/dev/null 2>&1; then
  echo "==> Docker не найден, устанавливаю..."
  curl -fsSL https://get.docker.com | sh
fi

# 2. Проверка .env
if [ ! -f .env ]; then
  echo "❌ Нет файла .env рядом со скриптом."
  echo "   Создай его:  nano .env  и вставь значения (см. SETUP.md)."
  exit 1
fi

if grep -q "ВСТАВЬ_ТОКЕН" .env; then
  echo "❌ В .env не вписан MANAGER_BOT_TOKEN. Открой:  nano .env"
  exit 1
fi

# 3. Сборка и запуск
echo "==> Поднимаю стек (app + Postgres + Caddy)..."
docker compose up -d --build

echo
echo "✅ Запущено. Полезное:"
echo "   docker compose logs -f app     # логи бота"
echo "   docker compose ps              # статус"
echo "   docker compose restart app     # перезапуск"
