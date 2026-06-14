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

import config
from database import cf_pool_add, cf_pool_stats

logger = logging.getLogger(__name__)


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
