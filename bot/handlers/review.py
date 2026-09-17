"""Review-mode buttons: approve -> queue, instant -> publish now, reject."""
from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from .. import database as db


def _cfg(context):
    return context.application.bot_data["cfg"]


def _tm(context):
    return context.application.bot_data["tm"]


async def review_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg, tm = _cfg(context), _tm(context)
    q = update.callback_query
    assert q and q.data
    _, action, qid = q.data.split(":")
    qid = int(qid)
    item = await db.get_queue_item(cfg.db_path, qid)
    if not item or item["user_id"] != q.from_user.id:
        await q.answer("این دکمه مال تو نیست!", show_alert=True)
        return
    if item["status"] != "pending_review":
        await q.answer("قبلاً تصمیم گرفته شده!", show_alert=True)
        try:
            await q.edit_message_reply_markup(None)
        except Exception:
            pass
        return
    await q.answer()
    if action == "no":
        await db.set_queue(cfg.db_path, qid, status="rejected", reason="رد دستی")
        await db.bump_stat(cfg.db_path, q.from_user.id, "rejected", "رد دستی")
        try:
            await q.edit_message_text((q.message.text_html if q.message else "رد شد") + "\n\n❌ <b>رد شد.</b>",
                                      parse_mode=ParseMode.HTML)
        except Exception:
            pass
    elif action == "ok":
        await db.set_queue(cfg.db_path, qid, status="queued")
        await db.bump_stat(cfg.db_path, q.from_user.id, "approved")
        try:
            await q.edit_message_text((q.message.text_html if q.message else "") + "\n\n✅ <b>تایید شد؛ میره تو صف انتشار.</b>",
                                      parse_mode=ParseMode.HTML)
        except Exception:
            pass
    elif action == "now":
        await db.set_queue(cfg.db_path, qid, status="queued")
        await db.bump_stat(cfg.db_path, q.from_user.id, "approved")
        from ..services import publisher
        item = await db.get_queue_item(cfg.db_path, qid)
        ok, detail = await publisher.publish_item(context.bot, tm, cfg.db_path, cfg, item,
                                                  cfg.ai_order)
        try:
            await q.edit_message_text(
                (q.message.text_html if q.message else "") + f"\n\n{'✅ منتشر شد!' if ok else '❌ ' + detail}",
                parse_mode=ParseMode.HTML)
        except Exception:
            pass


def register(app: Application) -> None:
    app.add_handler(CallbackQueryHandler(review_router, pattern=r"^rv:(ok|now|no):\d+$"))
