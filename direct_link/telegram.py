from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

class InitDataError(Exception):
    pass

@dataclass
class TgUser:
    id: int
    username: str = ""

def verify_init_data(
    init_data: str, bot_token: str, max_age: int
) -> tuple[TgUser, str]:
    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError as e:
        raise InitDataError("malformed") from e

    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InitDataError("no hash")

    data_check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received_hash):
        raise InitDataError("bad signature")

    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError as e:
        raise InitDataError("bad auth_date") from e
    if auth_date <= 0 or time.time() - auth_date > max_age:
        raise InitDataError("expired")

    try:
        u = json.loads(pairs.get("user", ""))
    except json.JSONDecodeError as e:
        raise InitDataError("bad user") from e

    return (
        TgUser(id=int(u["id"]), username=u.get("username", "")),
        pairs.get("start_param", ""),
    )
