"""Импорт пула CF-аккаунтов из JSON в БД при старте.

Формат cf_pool.json:
[
  {"email": "acc1@gmail.com", "api_token": "cfut_xxx", "label": "acc1"},
  {"email": "acc2@gmail.com", "api_token": "cfut_yyy"}
]

Дубли по api_token пропускаются — файл можно просто дополнять и перезапускать
бота, ничего не теряется.
"""
from __future__ import annotations

import json
import logging
import os
import threading

import config
from database import cf_pool_add, cf_pool_stats

logger = logging.getLogger(__name__)

_file_lock = threading.Lock()


def append_token_to_json(api_token: str, label: str | None = None,
                         email: str | None = None) -> bool:
    """Дописывает токен в cf_pool.json (атомарно, с fsync).
    Дубли по api_token пропускаются. Возвращает True если добавлено."""
    path = config.CF_POOL_JSON_PATH
    if not path:
        return False
    api_token = (api_token or "").strip()
    if not api_token:
        return False

    with _file_lock:
        data: list = []
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                if text:
                    raw = json.loads(text)
                    if isinstance(raw, list):
                        data = raw
                    elif isinstance(raw, dict):
                        # старый формат: одиночный объект без массива
                        data = [raw]
            except Exception as e:
                logger.warning(
                    "cf_pool: %s повреждён или не JSON-массив, перезапишу: %s",
                    path, e,
                )
                data = []

        for item in data:
            if isinstance(item, dict) and (item.get("api_token") or "").strip() == api_token:
                return False  # уже есть

        entry: dict = {"api_token": api_token}
        if label:
            entry["label"] = label
        if email:
            entry["email"] = email
        data.append(entry)

        # Пишем прямо в файл, без tmp+replace: bind-mount одиночного файла
        # в Docker не даёт сделать rename поверх ("Device or resource busy").
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
        except Exception as e:
            logger.error("cf_pool: не смог записать %s: %s", path, e)
            return False
    return True


def sync_db_to_json() -> int:
    """Дописывает в cf_pool.json все токены, которые есть в БД, но
    отсутствуют в файле. Возвращает число дописанных."""
    from database import _db, _lock  # локальный импорт — циклы не нужны
    with _lock:
        rows = _db.all("SELECT email, api_token, label FROM cf_accounts ORDER BY id")
    added = 0
    for r in rows:
        token = (r["api_token"] or "").strip()
        if not token or not token.isascii():
            continue
        if append_token_to_json(token, label=r.get("label"), email=r.get("email")):
            added += 1
    return added


def import_cf_pool_from_json() -> None:
    path = config.CF_POOL_JSON_PATH
    if not path or not os.path.exists(path):
        logger.info("cf_pool: файл %s не найден, пропуск импорта", path)
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error("cf_pool: не удалось прочитать %s: %s", path, e)
        return
    if not isinstance(data, list):
        logger.error("cf_pool: ожидался JSON-массив в %s", path)
        return

    added = 0
    for item in data:
        token = (item.get("api_token") or "").strip()
        if not token:
            continue
        if cf_pool_add(item.get("email"), token, item.get("label")):
            added += 1

    stats = cf_pool_stats()
    logger.info(
        "cf_pool: импорт завершён. Добавлено: %d. В пуле всего: %d, свободно: %d.",
        added, stats["total"], stats["free"],
    )
