"""Load settings from environment / .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _csv(value: str) -> list[str]:
    return [x.strip() for x in (value or "").split(",") if x.strip()]


def _csv_int(value: str) -> list[int]:
    out: list[int] = []
    for x in _csv(value):
        try:
            out.append(int(x))
        except ValueError:
            continue
    return out


@dataclass
class Settings:
    bot_token: str
    api_id: int
    api_hash: str
    admin_ids: list[int] = field(default_factory=list)
    db_path: str = "data/bot.db"
    timezone: str = "Asia/Tehran"
    daily_post_limit: int = 60
    max_sources: int = 5
    max_dests: int = 2
    poll_interval_sec: int = 180
    queue_tick_sec: int = 60
    news_tick_min: int = 20
    groq_keys: list[str] = field(default_factory=list)
    gemini_keys: list[str] = field(default_factory=list)
    openrouter_keys: list[str] = field(default_factory=list)
    mistral_keys: list[str] = field(default_factory=list)
    minimax_keys: list[str] = field(default_factory=list)
    ai_order: list[str] = field(default_factory=lambda: ["groq", "mistral", "minimax", "gemini", "openrouter"])
    parser_session: str = ""
    navasan_key: str = ""
    tavily_key: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("BOT_TOKEN", "").strip()
        api_id = int(os.getenv("API_ID", "0") or 0)
        api_hash = os.getenv("API_HASH", "").strip()
        if not token or not api_id or not api_hash:
            raise RuntimeError(
                "BOT_TOKEN / API_ID / API_HASH خالی است. فایل .env را از روی .env.example بساز و پر کن."
            )
        return cls(
            bot_token=token,
            api_id=api_id,
            api_hash=api_hash,
            admin_ids=_csv_int(os.getenv("ADMIN_IDS", "")),
            db_path=os.getenv("DATABASE_PATH", "data/bot.db"),
            timezone=os.getenv("TIMEZONE", "Asia/Tehran"),
            daily_post_limit=int(os.getenv("DAILY_POST_LIMIT", "60") or 60),
            max_sources=int(os.getenv("MAX_SOURCES", "5") or 5),
            max_dests=int(os.getenv("MAX_DESTS", "2") or 2),
            poll_interval_sec=int(os.getenv("POLL_INTERVAL_SEC", "180") or 180),
            queue_tick_sec=int(os.getenv("QUEUE_TICK_SEC", "60") or 60),
            news_tick_min=int(os.getenv("NEWS_TICK_MIN", "20") or 20),
            groq_keys=_csv(os.getenv("GROQ_KEYS", "")),
            gemini_keys=_csv(os.getenv("GEMINI_KEYS", "")),
            openrouter_keys=_csv(os.getenv("OPENROUTER_KEYS", "")),
            mistral_keys=_csv(os.getenv("MISTRAL_KEYS", "")),
            minimax_keys=_csv(os.getenv("MINIMAX_KEYS", "")),
            ai_order=_csv(os.getenv("AI_ORDER", "groq,gemini,openrouter")) or ["groq", "mistral", "minimax", "gemini", "openrouter"],
            parser_session=os.getenv("PARSER_SESSION", "").strip(),
            navasan_key=os.getenv("NAVASAN_KEY", "").strip(),
            tavily_key=os.getenv("TAVILY_KEY", "").strip(),
        )

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids
