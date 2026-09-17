"""Connection & channels: personal login (phone/code/2fa), add/remove source/dest."""
from __future__ import annotations

import aiosqlite
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, ConversationHandler, MessageHandler, filters)

from .. import database as db
from ..keyboards import back_to_menu, cancel_conv, channel_list, conn_menu, login_code_kb
from ..texts import ASK_REF_DEST, ASK_REF_SOURCE

LOGIN_PHONE, LOGIN_CODE, LOGIN_2FA = range(3)
ADD_REF = 10


def _cfg(context):
    return context.application.bot_data["cfg"]


def _tm(context):
    return context.application.bot_data["tm"]


# ---------- callbacks ----------
async def conn_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg, q = _cfg(context), update.callback_query
    assert q and q.data
    await q.answer()
    uid = q.from_user.id
    action = q.data.split(":", 1)[1]
    u = await db.ensure_user(cfg.db_path, uid)
    if action == "src":
        items = await db.list_sources(cfg.db_path, uid)
        await q.edit_message_text(
            f"📡 <b>کانال‌های مبدا</b> ({len(items)}/{cfg.max_sources})\n\n"
            "برای حذف، روی اسم کانال بزن. ترجمه هر کانال رو جدا می‌تونی از همین‌جا مدیریت کنی (با /tr).",
            parse_mode=ParseMode.HTML, reply_markup=channel_list(items, "src"))
    elif action == "dest":
        items = await db.list_dests(cfg.db_path, uid)
        await q.edit_message_text(
            f"🎯 <b>کانال مقصد</b> ({len(items)}/{cfg.max_dests})\n\n"
            "یادت نره ربات (حالت ربات) یا اکانتت (حالت شخصی) باید تو کانال مقصد ادمین باشه!",
            parse_mode=ParseMode.HTML, reply_markup=channel_list(items, "dest"))
    elif action == "tobot":
        await db.set_user(cfg.db_path, uid, mode="bot")
        async with aiosqlite.connect(cfg.db_path) as d:
            await d.execute("DELETE FROM sources WHERE user_id=?", (uid,))
            await d.execute("DELETE FROM dests WHERE user_id=?", (uid,))
            await d.commit()
        await q.edit_message_text("🔀 برگشتی به «حالت ربات». کانال‌های قبلی پاک شدن؛ دوباره اضافه‌شون کن.",
                                  reply_markup=conn_menu("bot", False))
    elif action == "logout":
        await _tm(context).logout(uid)
        async with aiosqlite.connect(cfg.db_path) as d:
            await d.execute("DELETE FROM sources WHERE user_id=?", (uid,))
            await d.execute("DELETE FROM dests WHERE user_id=?", (uid,))
            await d.commit()
        await q.edit_message_text("🚪 از اکانت شخصی خارج شدی و برگشتی به حالت ربات.",
                                  reply_markup=conn_menu("bot", False))


async def chdel_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg, q = _cfg(context), update.callback_query
    assert q and q.data
    await q.answer("حذف شد ✅")
    _, kind, _id = q.data.split(":")
    if kind == "src":
        await db.remove_source(cfg.db_path, q.from_user.id, int(_id))
        items = await db.list_sources(cfg.db_path, q.from_user.id)
        await q.edit_message_text(f"📡 <b>کانال‌های مبدا</b> ({len(items)}/{cfg.max_sources})",
                                  parse_mode=ParseMode.HTML, reply_markup=channel_list(items, "src"))
    else:
        await db.remove_dest(cfg.db_path, q.from_user.id, int(_id))
        items = await db.list_dests(cfg.db_path, q.from_user.id)
        await q.edit_message_text(f"🎯 <b>کانال مقصد</b> ({len(items)}/{cfg.max_dests})",
                                  parse_mode=ParseMode.HTML, reply_markup=channel_list(items, "dest"))


# ---------- login conversation ----------
async def login_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    assert q
    await q.answer()
    await q.edit_message_text(
        "📱 <b>اتصال اکانت شخصی</b>\n\nشماره موبایلت رو با فرمت بین‌المللی بفرست:\n<code>+33612345678</code>",
        parse_mode=ParseMode.HTML, reply_markup=cancel_conv())
    return LOGIN_PHONE


async def login_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message and update.message.text
    tm = _tm(context)
    res = await tm.send_code(update.effective_user.id, update.message.text.strip())  # type: ignore
    if res == "already_sent":
        await update.message.reply_text(
            "📩 کد همین یکی دو دقیقه پیش فرستاده شد! همون رو وارد کن — اگه نیومده «🔄 ارسال مجدد کد» رو بزن.",
            reply_markup=login_code_kb())
        return LOGIN_CODE
    if res != "ok":
        await update.message.reply_text(f"❌ {res}", reply_markup=cancel_conv())
        return LOGIN_PHONE
    await update.message.reply_text("📩 کد تایید تلگرام رو بفرست (همون که به اکانتت اومد):",
                                    reply_markup=login_code_kb())
    return LOGIN_CODE


async def login_resend(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    assert q
    res = await _tm(context).resend_code(q.from_user.id)
    if res == "ok":
        await q.answer("کد جدید فرستاده شد ✅")
        await q.edit_message_text("📩 کد جدید فرستاده شد! سریع واردش کن:",
                                  reply_markup=login_code_kb())
    elif res.startswith("wait:"):
        await q.answer(f"کمی صبر کن! تلگرام گفته {res[5:]} ثانیه دیگه.", show_alert=True)
    elif res == "expired":
        await q.answer("نشست لاگین پیدا نشد!", show_alert=True)
        await q.edit_message_text("❌ نشست لاگین پیدا نشد (شاید ربات ری‌استارت شده). انصراف بزن و از اول شروع کن.",
                                  reply_markup=cancel_conv())
    else:
        await q.answer("خطا!", show_alert=True)
        await q.edit_message_text(f"❌ {res[4:] if res.startswith('err:') else res}",
                                  reply_markup=login_code_kb())
    return LOGIN_CODE


async def login_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message and update.message.text
    tm = _tm(context)
    res = await tm.submit_code(update.effective_user.id, update.message.text.strip())  # type: ignore
    if res == "ok":
        await update.message.reply_text("✅ اکانت وصل شد! حالتت رفت روی «شخصی». حالا کانال مقصد و مبدا رو اضافه کن.",
                                        reply_markup=conn_menu("personal", True))
        return ConversationHandler.END
    if res == "2fa":
        await update.message.reply_text("🔐 رمز دومرحله‌ای (پسورد ابری) رو بفرست:", reply_markup=cancel_conv())
        return LOGIN_2FA
    await update.message.reply_text(f"❌ {res}", reply_markup=login_code_kb())
    return LOGIN_CODE


async def login_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message and update.message.text
    tm = _tm(context)
    res = await tm.submit_2fa(update.effective_user.id, update.message.text.strip())  # type: ignore
    try:
        await update.message.delete()  # don't keep password in chat
    except Exception:
        pass
    if res == "ok":
        await update.message.reply_text("✅ اکانت وصل شد! حالا کانال مقصد و مبدا رو اضافه کن.",
                                        reply_markup=conn_menu("personal", True))
        return ConversationHandler.END
    await update.message.reply_text(f"❌ {res}", reply_markup=cancel_conv())
    return LOGIN_2FA


# ---------- add channel conversation ----------
async def chadd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cfg = _cfg(context)
    q = update.callback_query
    assert q and q.data
    await q.answer()
    kind = q.data.split(":")[1]
    context.user_data["chadd_kind"] = kind
    if kind == "src" and len(await db.list_sources(cfg.db_path, q.from_user.id)) >= cfg.max_sources:
        await q.edit_message_text(f"⚠️ سقف مبدا ({cfg.max_sources}) پره! اول یکیش رو حذف کن.",
                                      reply_markup=back_to_menu())
        return ConversationHandler.END
    if kind == "dest" and len(await db.list_dests(cfg.db_path, q.from_user.id)) >= cfg.max_dests:
        await q.edit_message_text(f"⚠️ سقف مقصد ({cfg.max_dests}) پره! اول حذفش کن.",
                                      reply_markup=back_to_menu())
        return ConversationHandler.END
    await q.edit_message_text(ASK_REF_SOURCE if kind == "src" else ASK_REF_DEST,
                              parse_mode=ParseMode.HTML, reply_markup=cancel_conv())
    return ADD_REF


async def chadd_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cfg, tm = _cfg(context), _tm(context)
    assert update.message and update.message.text
    uid = update.effective_user.id  # type: ignore
    kind = context.user_data.get("chadd_kind", "src")
    ref = update.message.text.strip()
    u = await db.ensure_user(cfg.db_path, uid)
    cli = tm.client_for(uid, u["mode"])
    if cli is None or not cli.is_connected():
        if u["mode"] == "personal":
            await update.message.reply_text("❌ اکانت شخصی قطع شده؛ دوباره وصل شو.",
                                            reply_markup=back_to_menu())
        else:
            await update.message.reply_text("❌ حالت ربات فعلاً آماده نیست؛ لطفاً کمی بعد دوباره تلاش کن.",
                                            reply_markup=back_to_menu())
        return ConversationHandler.END
    wait = await update.message.reply_text("⏳ دارم چک می‌کنم...")
    ent, title, store_ref, status = await tm.resolve_and_join(cli, ref)
    if not ent:
        await wait.edit_text(f"❌ {status}", reply_markup=cancel_conv())
        return ADD_REF
    if not getattr(ent, "broadcast", False):
        await wait.edit_text("⚠️ این یه کانال نیست! فقط کانال قبول می‌کنم.", reply_markup=cancel_conv())
        return ADD_REF
    # set last_msg_id to current latest so we don't repost history
    try:
        latest = await cli.get_messages(ent, limit=1)
        last_id = latest[0].id if latest else 0
    except Exception:
        last_id = 0
    if kind == "src":
        sid = await db.add_source(cfg.db_path, uid, store_ref, str(title))
        await db.set_source_last(cfg.db_path, sid, last_id)
        extra = ""
        if u["mode"] == "bot":
            extra = "\n\n<blockquote>تو حالت ربات فقط پست‌های جدید خونده میشن (تاریخچه قدیمی نه).</blockquote>"
        await wait.edit_text(f"✅ مبدا اضافه شد: <b>{title}</b>{extra}", parse_mode=ParseMode.HTML,
                             reply_markup=back_to_menu())
    else:
        await db.add_dest(cfg.db_path, uid, store_ref, str(title))
        who = "خودِ ربات" if u["mode"] == "bot" else "اکانت شخصیت"
        await wait.edit_text(
            f"✅ مقصد اضافه شد: <b>{title}</b>\n\n⚠️ حتماً {who} رو تو این کانال <b>ادمین</b> کن (دسترسی ارسال پیام)!",
            parse_mode=ParseMode.HTML, reply_markup=back_to_menu())
    return ConversationHandler.END


async def conv_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if q:
        await q.answer()
        await q.edit_message_text("❌ انصراف داده شد.", reply_markup=back_to_menu())
    elif update.message:
        await update.message.reply_text("❌ انصراف داده شد.", reply_markup=back_to_menu())
    return ConversationHandler.END


async def cmd_tr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle per-source translation: /tr <id> — list ids via /trs"""
    cfg = _cfg(context)
    assert update.message and update.effective_user
    args = (update.message.text or "").split()
    if len(args) < 2 or args[1] == "list":
        items = await db.list_sources(cfg.db_path, update.effective_user.id)
        if not items:
            await update.message.reply_text("مبدایی نداری.", reply_markup=back_to_menu())
            return
        lines = ["📡 برای تغییر ترجمه هر کانال: <code>/tr &lt;id&gt;</code>\n"]
        for it in items:
            ov = it.get("translate_override")
            st = "پیش‌فرض" if ov is None else ("روشن" if ov else "خاموش")
            lines.append(f"• <code>{it['id']}</code> — {it.get('title') or it['channel']} (ترجمه: {st})")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML,
                                        reply_markup=back_to_menu())
        return
    try:
        sid = int(args[1])
    except ValueError:
        await update.message.reply_text("آیدی عددی بده. مثال: <code>/tr 3</code>", parse_mode=ParseMode.HTML,
                                        reply_markup=back_to_menu())
        return
    items = await db.list_sources(cfg.db_path, update.effective_user.id)
    cur = next((x for x in items if x["id"] == sid), None)
    if not cur:
        await update.message.reply_text("این آیدی مال تو نیست!", reply_markup=back_to_menu())
        return
    nxt = 0 if cur.get("translate_override") is None else (1 if not cur.get("translate_override") else None)
    await db.set_source_translate(cfg.db_path, sid, nxt)
    label = "پیش‌فرض" if nxt is None else ("روشن" if nxt else "خاموش")
    await update.message.reply_text(f"ترجمه «{cur.get('title') or cur['channel']}» شد: <b>{label}</b>",
                                    parse_mode=ParseMode.HTML, reply_markup=back_to_menu())


def register(app: Application) -> None:
    # NOTE: login conv FIRST — PTB runs only the first matching handler per
    # group, so conn_router's pattern must never swallow cn:login.
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(login_start, pattern=r"^cn:login$")],
        states={LOGIN_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_phone)],
                LOGIN_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_code),
                             CallbackQueryHandler(login_resend, pattern=r"^login:resend$")],
                LOGIN_2FA: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_2fa)]},
        fallbacks=[CallbackQueryHandler(conv_cancel, pattern=r"^conv:cancel$"),
                   CommandHandler("cancel", conv_cancel)],
        name="login", persistent=False))
    app.add_handler(CallbackQueryHandler(chdel_router, pattern=r"^chdel:"))
    # narrowed on purpose: must never swallow cn:login (see above)
    app.add_handler(CallbackQueryHandler(conn_router, pattern=r"^cn:(src|dest|tobot|logout)$"))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(chadd_start, pattern=r"^chadd:")],
        states={ADD_REF: [MessageHandler(filters.TEXT & ~filters.COMMAND, chadd_received)]},
        fallbacks=[CallbackQueryHandler(conv_cancel, pattern=r"^conv:cancel$"),
                   CommandHandler("cancel", conv_cancel)],
        name="chadd", persistent=False))
    app.add_handler(CommandHandler("tr", cmd_tr))
    app.add_handler(CommandHandler("cancel", conv_cancel))
