"""AI key pool: status, donate-a-key wizard (provider -> url -> key -> model -> test)."""
from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, ConversationHandler, MessageHandler, filters)

from .. import database as db
from ..keyboards import back_to_menu, cancel_conv, keys_menu, provider_pick
from ..services import ai_router

DK_PROVIDER, DK_URL, DK_KEY, DK_MODEL = range(40, 44)


def _cfg(context):
    return context.application.bot_data["cfg"]


async def key_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg, q = _cfg(context), update.callback_query
    assert q and q.data
    await q.answer()
    act = q.data.split(":", 1)[1]
    if act == "pool":
        stats = await ai_router.pool_stats(cfg.db_path)
        lines = [f"📊 <b>وضعیت استخر</b>: {stats['active']} فعال از {stats['total']} کلید\n"]
        for p, v in stats["by_provider"].items():
            lines.append(f"• {p}: {v['active']} فعال / {v['dead']} خراب (✅{v['ok']} ❌{v['fail']})")
        if cfg.is_admin(q.from_user.id):
            keys = await db.list_ai_keys(cfg.db_path)
            lines.append("\n<i>مدیریت (ادمین): برای حذف /delkey &lt;id&gt;</i>")
            for k in keys[-15:]:
                lines.append(f"• <code>{k['id']}</code> {k['provider']}/{k['model'][:30]} [{k['status']}] {k['masked']}")
        await q.edit_message_text("\n".join(lines)[:3500], parse_mode=ParseMode.HTML,
                                  reply_markup=back_to_menu())
    elif act == "mine":
        keys = [k for k in await db.list_ai_keys(cfg.db_path) if k["added_by"] == q.from_user.id]
        if not keys:
            await q.edit_message_text("🗝️ هنوز کلیدی اهدا نکردی! با «🎁 اهدای کلید» شروع کن.",
                                      reply_markup=back_to_menu())
            return
        lines = ["🗝️ <b>کلیدهای تو:</b>\n"]
        for k in keys:
            lines.append(f"• <code>{k['id']}</code> {k['provider']}/{k['model'][:30]} [{k['status']}] ✅{k['success_count']} ❌{k['fail_count']}")
        lines.append("\nبرای حذف: <code>/mykey del &lt;id&gt;</code>")
        await q.edit_message_text("\n".join(lines)[:3500], parse_mode=ParseMode.HTML,
                                  reply_markup=back_to_menu())


async def cmd_mykey(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = _cfg(context)
    assert update.message and update.effective_user
    parts = (update.message.text or "").split()
    if len(parts) == 3 and parts[1] == "del":
        try:
            kid = int(parts[2])
        except ValueError:
            await update.message.reply_text("آیدی عددی بده.")
            return
        keys = [k for k in await db.list_ai_keys(cfg.db_path)
                if k["id"] == kid and (k["added_by"] == update.effective_user.id or cfg.is_admin(update.effective_user.id))]
        if not keys:
            await update.message.reply_text("این کلید مال تو نیست!")
            return
        await db.delete_ai_key(cfg.db_path, kid)
        await update.message.reply_text("🗑️ کلید حذف شد.")
    else:
        await update.message.reply_text("استفاده: <code>/mykey del &lt;id&gt;</code> — آیدی‌ها رو از «🗝️ کلیدهای من» ببین.",
                                        parse_mode=ParseMode.HTML)


async def cmd_delkey(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = _cfg(context)
    assert update.message and update.effective_user
    if not cfg.is_admin(update.effective_user.id):
        return
    parts = (update.message.text or "").split()
    if len(parts) != 2:
        await update.message.reply_text("استفاده: <code>/delkey &lt;id&gt;</code>", parse_mode=ParseMode.HTML)
        return
    try:
        await db.delete_ai_key(cfg.db_path, int(parts[1]))
        await update.message.reply_text("🗑️ حذف شد.")
    except ValueError:
        await update.message.reply_text("آیدی عددی بده.")


# ---------- donate wizard ----------
async def donate_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    assert q
    await q.answer()
    context.user_data["dk"] = {}
    await q.edit_message_text(
        "🎁 <b>اهدای کلید AI</b>\n\nارائه‌دهنده رو انتخاب کن (راهنمای گرفتن کلید رایگان زیر هرکدومه):\n\n"
        + "\n".join(f"• <b>{v['label']}</b>: {v['hint']}" for k, v in ai_router.PROVIDERS.items() if k != "custom"),
        parse_mode=ParseMode.HTML, reply_markup=provider_pick())
    return DK_PROVIDER


async def dk_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    assert q and q.data
    await q.answer()
    provider = q.data.split(":")[1]
    info = ai_router.PROVIDERS[provider]
    context.user_data["dk"] = {"provider": provider}
    if provider == "custom":
        await q.edit_message_text("🛠️ آدرس پایه (Base URL) رو بفرست:\nمثال: <code>https://api.xxx.com/v1</code>",
                                  parse_mode=ParseMode.HTML, reply_markup=cancel_conv())
        return DK_URL
    context.user_data["dk"]["url"] = info["base"]
    await q.edit_message_text(f"🔑 کلید <b>{info['label']}</b> رو بفرست:\n<i>(ربات اول تستش می‌کنه؛ اگه سالم بود ذخیره میشه)</i>",
                              parse_mode=ParseMode.HTML, reply_markup=cancel_conv())
    return DK_KEY


async def dk_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message and update.message.text
    url = update.message.text.strip().rstrip("/")
    if not url.startswith("http"):
        await update.message.reply_text("❌ آدرس باید با http شروع بشه! دوباره بفرست:")
        return DK_URL
    context.user_data["dk"]["url"] = url
    await update.message.reply_text("🔑 حالا کلید (API Key) رو بفرست:", reply_markup=cancel_conv())
    return DK_KEY


async def dk_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message and update.message.text
    key = update.message.text.strip()
    if len(key) < 8:
        await update.message.reply_text("❌ کلید خیلی کوتاهه! دوباره بفرست:")
        return DK_KEY
    context.user_data["dk"]["key"] = key
    provider = context.user_data["dk"]["provider"]
    default_model = ai_router.PROVIDERS[provider]["model"]
    if provider == "custom":
        await update.message.reply_text("🤖 اسم دقیق مدل رو بفرست:\nمثال: <code>llama-3.3-70b-versatile</code>",
                                        parse_mode=ParseMode.HTML, reply_markup=cancel_conv())
    else:
        await update.message.reply_text(
            f"🤖 مدل رو بفرست یا برای پیش‌فرض (<code>{default_model}</code>) کلمه <code>ok</code> رو بفرست:",
            parse_mode=ParseMode.HTML, reply_markup=cancel_conv())
    try:
        await update.message.delete()  # don't keep the key visible in chat
    except Exception:
        pass
    return DK_MODEL


async def dk_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cfg = _cfg(context)
    assert update.message and update.message.text
    uid = update.effective_user.id  # type: ignore
    dk = context.user_data.get("dk", {})
    provider = dk.get("provider", "custom")
    default_model = ai_router.PROVIDERS[provider]["model"]
    model = update.message.text.strip()
    if model.lower() == "ok":
        model = default_model
    if not model:
        await update.message.reply_text("❌ مدل خالیه! دوباره بفرست:")
        return DK_MODEL
    if await db.key_exists(cfg.db_path, dk["key"]):
        await update.message.reply_text("⚠️ این کلید قبلاً تو استخر هست! مرسی ولی تکراریه 😄",
                                        reply_markup=back_to_menu())
        return ConversationHandler.END
    wait = await update.message.reply_text("⏳ دارم کلید رو تست می‌کنم...")
    ok, detail, ms = await ai_router.test_key(provider, dk.get("url", ""), dk["key"], model)
    if not ok:
        await wait.edit_text(f"❌ کلید قبول نشد!\n\n{detail}\n\nدوباره با /start ← کلیدهای AI تلاش کن.")
        return ConversationHandler.END
    await db.add_ai_key(cfg.db_path, provider, dk.get("url", ""), dk["key"], model,
                        added_by=uid, note="donated")
    stats = await ai_router.pool_stats(cfg.db_path)
    await wait.edit_text(
        f"🎉 <b>مرسی! کلیدت سالم بود و به استخر اضافه شد.</b>\n\n{detail}\nمدل: <code>{model}</code>\n\n"
        f"🧩 استخر الان {stats['active']} کلید فعال داره و ربات از کلید تو هم استفاده می‌کنه. 🙏",
        parse_mode=ParseMode.HTML, reply_markup=back_to_menu())
    return ConversationHandler.END


async def dk_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if q:
        await q.answer()
        await q.edit_message_text("❌ انصراف داده شد.", reply_markup=back_to_menu())
    return ConversationHandler.END


def register(app: Application) -> None:
    app.add_handler(CallbackQueryHandler(key_router, pattern=r"^key:(pool|mine)$"))
    app.add_handler(CommandHandler("mykey", cmd_mykey))
    app.add_handler(CommandHandler("delkey", cmd_delkey))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(donate_start, pattern=r"^key:donate$")],
        states={
            DK_PROVIDER: [CallbackQueryHandler(dk_provider, pattern=r"^dk:")],
            DK_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, dk_url)],
            DK_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, dk_key)],
            DK_MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, dk_model)],
        },
        fallbacks=[CallbackQueryHandler(dk_cancel, pattern=r"^conv:cancel$"),
                   CommandHandler("cancel", dk_cancel)],
        name="donate", persistent=False))
