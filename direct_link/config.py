from __future__ import annotations

import os
from dataclasses import dataclass

@dataclass
class DirectLinkConfig:
    session_secret: str
    redirect_url: str = (
        "https://t.me/uzmigrant_miniapp_bot?startapp=profile"
    )
    cookie_name: str = "dl_session"
    session_max_age: int = 30 * 86400
    init_data_ttl: int = 86400
    manual_url: str = "https://example.com/manuals/direct-link"

    @classmethod
    def from_env(cls) -> "DirectLinkConfig":
        return cls(
            session_secret=os.environ["DIRECT_LINK_SESSION_SECRET"],
            redirect_url=os.getenv(
                "DIRECT_LINK_REDIRECT_URL",
                "https://t.me/uzmigrant_miniapp_bot?startapp=profile",
            ),
            session_max_age=int(
                os.getenv("DIRECT_LINK_SESSION_MAX_AGE", str(30 * 86400))
            ),
            init_data_ttl=int(os.getenv("DIRECT_LINK_INIT_DATA_TTL", "86400")),
            manual_url=os.getenv(
                "DIRECT_LINK_MANUAL_URL",
                "https://example.com/manuals/direct-link",
            ),
        )
