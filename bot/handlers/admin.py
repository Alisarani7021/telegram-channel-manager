"""Admin tools (hidden entry via /admin): parser login, broadcast, global stats."""
from __future__ import annotations

from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, ConversationHandler, MessageHandler, filters)

from .. import database as db
from ..keyboards import admin_menu, back_to_menu, cancel_conv

P_PHONE, P_CODE, P_2FA = range(50, 53)


def _cfg(context):
    return context.application.bot_data["cfg"]


def _tm(context):
    return context.application.bot_data["tm"]


# ---------- parser login (shared reader for public channels in bot mode) ----------
async def parser_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cfg = _cfg(context)
    assert update.message and update.effective_user
    if not cfg.is_admin(update.effective_user.id):
        return ConversationHandler.END  # silent: admin entry is invisible
    await update.message.reply_text(
        "🔧 <b>اتصال پارسر عمومی</b>\n\nاین اکانت فقط برای <i>خواندن کانال‌های عمومی</i> در حالت ربات استفاده میشه.\n"
        "شماره رو با فرمت بین‌المللی بفرست: <code>+33612345678</code>",
        parse_mode=ParseMode.HTML, reply_markup=cancel_conv())
    return P_PHONE


async def parser_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cfg = _cfg(context)
    assert update.message and update.message.text
    phone = update.message.text.strip()
    cli = TelegramClient(StringSession(), cfg.api_id, cfg.api_hash)
    await cli.connect()
    try:
        sent = await cli.send_code_request(phone)
    except Exception as e:
        await update.message.reply_text(f"❌ خطا: {e}")
        return P_PHONE
    context.user_data["pcli"] = cli
    context.user_data["pphone"] = phone
    context.user_data["phash"] = sent.phone_code_hash
    await update.message.reply_text("📩 کد تایید رو بفرست:", reply_markup=cancel_conv())
    return P_CODE


async def parser_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message and update.message.text
    cli = context.user_data.get("pcli")
    try:
        await cli.sign_in(phone=context.user_data["pphone"], code=update.message.text.strip(),
                          phone_code_hash=context.user_data["phash"])
    except errors.SessionPasswordNeededError:
        await update.message.reply_text("🔐 رمز دومرحله‌ای رو بفرست:", reply_markup=cancel_conv())
        return P_2FA
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")
        return P_CODE
    return await _parser_done(update, context)


async def parser_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message and update.message.text
    cli = context.user_data.get("pcli")
    try:
        await cli.sign_in(password=update.message.text.strip())
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")
        return P_2FA
    try:
        await update.message.delete()
    except Exception:
        pass
    return await _parser_done(update, context)


async def _parser_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cfg, tm = _cfg(context), _tm(context)
    cli = context.user_data.get("pcli")
    sess = cli.session.save()
    if tm.parser:
        try:
            await tm.parser.disconnect()
        except Exception:
            pass
    tm.parser = cli
    with open("data/parser_session.txt", "w") as f:
        f.write(sess)
    assert update.message
    await update.message.reply_text(
        "✅ پارسر وصل شد! حالت ربات فعاله.\n\n<i>سشن در data/parser_session.txt ذخیره شد؛ می‌تونی بذاریش تو .env به اسم PARSER_SESSION.</i>",
        parse_mode=ParseMode.HTML)
    return ConversationHandler.END


async def parser_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cli = context.user_data.get("pcli") if context else None
    if cli:
        try:
            await cli.disconnect()
        except Exception:
            pass
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ انصراف.")
    elif update.message:
        await update.message.reply_text("❌ انصراف.")
    return ConversationHandler.END


# ---------- broadcast ----------
async def ad_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = _cfg(context)
    q = update.callback_query
    assert q and q.data
    if not cfg.is_admin(q.from_user.id):
        await q.answer("فقط ادمین!", show_alert=True)
        return
    await q.answer()
    act = q.data.split(":", 1)[1]
    if act == "stats":
        users = await db.all_users(cfg.db_path)
        await q.edit_message_text(f"📈 <b>آمار کلی</b>\n\n👥 کاربران: <b>{len(users)}</b>",
                                  parse_mode=ParseMode.HTML, reply_markup=back_to_menu())
    elif act == "annc":
        await q.edit_message_text("📣 متن اعلان رو با دستور زیر بفرست:\n<code>/announce متن...</code>",
                                  parse_mode=ParseMode.HTML, reply_markup=back_to_menu())


async def cmd_announce(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = _cfg(context)
    assert update.message and update.effective_user
    if not cfg.is_admin(update.effective_user.id):
        return
    text = (update.message.text or "").partition(" ")[2].strip()
    if not text:
        await update.message.reply_text("متن رو هم بفرست: <code>/announce سلام!</code>", parse_mode=ParseMode.HTML)
        return
    await db.add_annc(cfg.db_path, text)
    sent = 0
    for u in await db.all_users(cfg.db_path):
        try:
            await context.bot.send_message(u["user_id"], f"🔔 <b>اعلان</b>\n\n{text}", parse_mode=ParseMode.HTML)
            sent += 1
        except Exception:
            continue
    await update.message.reply_text(f"📣 به {sent} نفر ارسال شد.")


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Hidden admin entry (no button anywhere)."""
    cfg = _cfg(context)
    assert update.message and update.effective_user
    if not cfg.is_admin(update.effective_user.id):
        return  # silent
    await update.message.reply_text("🛠️ <b>مدیریت</b>", parse_mode=ParseMode.HTML,
                                    reply_markup=admin_menu())


def register(app: Application) -> None:
    app.add_handler(CallbackQueryHandler(ad_router, pattern=r"^ad:"))
    app.add_handler(CommandHandler("announce", cmd_announce))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("parser_login", parser_start)],
        states={P_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, parser_phone)],
                P_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, parser_code)],
                P_2FA: [MessageHandler(filters.TEXT & ~filters.COMMAND, parser_2fa)]},
        fallbacks=[CallbackQueryHandler(parser_cancel, pattern=r"^conv:cancel$"),
                   CommandHandler("cancel", parser_cancel)],
        name="parser", persistent=False))
