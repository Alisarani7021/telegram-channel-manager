"""Entry point: Bot API + Telethon + APScheduler in one process."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application

from . import database as db
from .config import Settings
from .handlers import admin as h_admin
from .handlers import connection as h_conn
from .handlers import keys as h_keys
from .handlers import review as h_review
from .handlers import settings as h_settings
from .handlers import start as h_start
from .services import ai_router
from .services.fetcher import TManager
from .services import scheduler as sched_svc

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("tcm")


async def main() -> None:
    cfg = Settings.from_env()
    Path("data").mkdir(exist_ok=True)
    await db.init_db(cfg.db_path)
    added = await ai_router.import_env_keys(cfg.db_path, cfg.groq_keys, cfg.gemini_keys,
                                            cfg.openrouter_keys, cfg.mistral_keys, cfg.minimax_keys)
    log.info("env keys imported: %d", added)

    # parser session from file (saved by /parser_login) if env empty
    parser_sess = cfg.parser_session
    if not parser_sess:
        p = Path("data/parser_session.txt")
        if p.exists():
            parser_sess = p.read_text().strip()

    tm = TManager(cfg.api_id, cfg.api_hash, cfg.db_path, parser_sess)
    await tm.start()
    log.info("telethon ready. parser=%s personal=%d",
             await tm.parser_ready(), len(tm.users))
    if not await tm.parser_ready():
        log.warning("Parser is NOT connected — bot mode needs /parser_login by admin!")

    app = Application.builder().token(cfg.bot_token).build()
    app.bot_data["cfg"] = cfg
    app.bot_data["tm"] = tm

    h_start.register(app)
    h_conn.register(app)
    h_settings.register(app)
    h_keys.register(app)
    h_review.register(app)
    h_admin.register(app)

    sched = AsyncIOScheduler(timezone=cfg.timezone)
    sched_svc.register(sched, app.bot, tm, cfg.db_path, cfg)

    await app.initialize()
    await app.start()
    assert app.updater
    await app.updater.start_polling(drop_pending_updates=True)
    sched.start()
    log.info("Bot is up. Press Ctrl+C to stop.")

    stop = asyncio.Event()
    try:
        await stop.wait()  # runs until cancelled
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        sched.shutdown(wait=False)
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
