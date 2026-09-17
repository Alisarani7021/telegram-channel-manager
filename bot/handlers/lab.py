"""Area 51 lab handlers: quantum, personas, trends, ideas, DNA, memories, god console."""
from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, ConversationHandler, MessageHandler, filters)

from .. import database as db
from ..keyboards import (back_to_lab, back_to_menu, cancel_conv, god_menu,
                         lab_menu, mem_kb)
from ..services import lab as lab_svc
from ..services import publisher

LAB_TOPIC, LAB_DNAIN = range(60, 62)


def _cfg(context):
    return context.application.bot_data["cfg"]


def _tm(context):
    return context.application.bot_data["tm"]


async def _show_lab(q, cfg, uid: int) -> None:
    s = await db.get_settings(cfg.db_path, uid)
    lab = lab_svc.get_lab(s)
    await q.edit_message_text(
        lab_svc.LAB_TEXT, parse_mode=ParseMode.HTML,
        reply_markup=lab_menu(s["content_style"], lab_svc.PERSONAS[lab["persona"]]["fa"],
                              bool(lab.get("idea_enabled"))))


async def _show_god(q, cfg, uid: int) -> None:
    s = await db.get_settings(cfg.db_path, uid)
    nc = await db.get_news_cfg(cfg.db_path, uid)
    await q.edit_message_text(
        "🎛️ <b>کنسول خدایی</b>\n\nاسلایدرهای سرنوشت کانال — هر کدوم یه تنظیم واقعی رو می‌چرخونه:",
        parse_mode=ParseMode.HTML,
        reply_markup=god_menu(s["content_style"], int(nc.get("per_cycle") or 2),
                              s["send_interval_min"]))


async def lab_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg, q = _cfg(context), update.callback_query
    assert q and q.data
    await q.answer()
    uid = q.from_user.id
    parts = q.data.split(":")
    act = parts[1] if len(parts) > 1 else ""
    if act == "quantum":
        s = await db.get_settings(cfg.db_path, uid)
        new = "medium" if s["content_style"] == "quantum" else "quantum"
        await db.set_settings(cfg.db_path, uid, content_style=new)
        return await _show_lab(q, cfg, uid)
    if act == "persona":
        s = await db.get_settings(cfg.db_path, uid)
        lab = lab_svc.get_lab(s)
        order = lab_svc.PERSONA_ORDER
        nxt = order[(order.index(lab["persona"]) + 1) % len(order)]
        await lab_svc.set_lab(cfg.db_path, uid, persona=nxt)
        return await _show_lab(q, cfg, uid)
    if act == "trend":
        await q.edit_message_text("⏳ دارم آینده رو می‌دزدم...", reply_markup=back_to_lab())
        try:
            text = await lab_svc.trend_radar()
        except Exception as e:
            text = f"❌ خطا: {e}"
        return await q.edit_message_text(text[:3800], parse_mode=ParseMode.HTML,
                                         reply_markup=back_to_lab())
    if act == "pulse":
        if await db.today_ai_usage(cfg.db_path, uid) >= cfg.daily_post_limit:
            await q.answer("⚡ سقف AI امروز تموم شده! فردا برگرد.", show_alert=True)
            return
        await q.edit_message_text("⏳ چشم سوم داره باز میشه...", reply_markup=back_to_lab())
        try:
            text = await lab_svc.world_pulse(cfg.db_path, cfg.ai_order)
            await db.bump_stat(cfg.db_path, uid, "ai_calls")
        except Exception as e:
            text = f"❌ خطا: {str(e)[:300]}"
        return await q.edit_message_text(text[:3800], parse_mode=ParseMode.HTML,
                                         reply_markup=back_to_lab())
    if act == "idea":
        s = await db.get_settings(cfg.db_path, uid)
        lab = lab_svc.get_lab(s)
        await lab_svc.set_lab(cfg.db_path, uid,
                              idea_enabled=0 if lab.get("idea_enabled") else 1)
        return await _show_lab(q, cfg, uid)
    if act == "memory":
        ex = await db.get_random_excerpt(cfg.db_path, uid)
        if not ex:
            return await q.edit_message_text(
                "♾️ هنوز خاطره‌ای ثبت نشده! بعد از چند انتشار برگرد.",
                reply_markup=back_to_lab())
        context.user_data["lab_mem"] = ex["excerpt"]
        return await q.edit_message_text(
            f"♾️ <b>خاطره ابدی</b>\n\n{ex['excerpt'][:3000]}",
            parse_mode=ParseMode.HTML, reply_markup=mem_kb())
    if act == "resend":
        mem = (context.user_data.get("lab_mem") or "").strip()
        if not mem:
            return await q.edit_message_text("❌ خاطره پیدا نشد؛ دوباره یه خاطره بکش.",
                                             reply_markup=back_to_lab())
        if not await db.list_dests(cfg.db_path, uid):
            return await q.edit_message_text("❌ کانال مقصد نداری! اول مقصد اضافه کن.",
                                             reply_markup=back_to_lab())
        await q.edit_message_text("⏳ دارم بازنشر می‌کنم...", reply_markup=back_to_lab())
        qid = await db.enqueue(cfg.db_path, uid, "memory", [], "text",
                               mem, mem, "queued", kind="memory")
        item = await db.get_queue_item(cfg.db_path, qid)
        ok, detail = await publisher.publish_item(context.bot, _tm(context), cfg.db_path,
                                                  cfg, item, cfg.ai_order)
        return await q.edit_message_text(
            f"{'✅ خاطره بازنشر شد!' if ok else '❌ ' + detail}",
            reply_markup=back_to_lab())
    if act == "dnaout":
        try:
            code = await lab_svc.export_dna(cfg.db_path, uid)
        except ValueError as e:
            await q.answer(str(e)[:180], show_alert=True)
            return
        assert q.message
        await q.message.reply_text(
            f"🧬 <b>DNA کانال تو</b> (نگهش دار!):\n\n<code>{code}</code>",
            parse_mode=ParseMode.HTML, reply_markup=back_to_menu())
        return
    if act == "god":
        return await _show_god(q, cfg, uid)
    if act == "godcur":
        nc = await db.get_news_cfg(cfg.db_path, uid)
        nxt = int(nc.get("per_cycle") or 2) % 5 + 1
        await db.set_news_cfg(cfg.db_path, uid, per_cycle=nxt)
        return await _show_god(q, cfg, uid)
    if act == "godcalm":
        s = await db.get_settings(cfg.db_path, uid)
        opts = [15, 30, 60, 120, 360]
        cur = s["send_interval_min"]
        nxt = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else 30
        await db.set_settings(cfg.db_path, uid, send_interval_min=nxt)
        return await _show_god(q, cfg, uid)
    if act == "godtone":
        s = await db.get_settings(cfg.db_path, uid)
        opts = ["short", "medium", "quantum"]
        cur = s["content_style"]
        nxt = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else "medium"
        await db.set_settings(cfg.db_path, uid, content_style=nxt)
        return await _show_god(q, cfg, uid)


# ---------- idea rain conversation ----------
async def rain_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    assert q
    await q.answer()
    await q.edit_message_text("🌪️ موضوع باران ایده رو بفرست:\nمثال: <code>تکنولوژی</code>",
                              parse_mode=ParseMode.HTML, reply_markup=cancel_conv())
    return LAB_TOPIC


async def rain_got(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cfg = _cfg(context)
    assert update.message and update.message.text
    uid = update.effective_user.id  # type: ignore
    if await db.today_ai_usage(cfg.db_path, uid) >= cfg.daily_post_limit:
        await update.message.reply_text("⚡ سقف AI امروز تموم شده! فردا برگرد.",
                                        reply_markup=back_to_menu())
        return ConversationHandler.END
    topic = update.message.text.strip()[:80]
    wait = await update.message.reply_text("⏳ ابرها دارن بارور میشن...")
    try:
        text = await lab_svc.idea_rain(cfg.db_path, topic, cfg.ai_order)
        await db.bump_stat(cfg.db_path, uid, "ai_calls")
        await wait.edit_text(text[:3800], parse_mode=ParseMode.HTML,
                             reply_markup=back_to_menu())
    except Exception as e:
        await wait.edit_text(f"❌ خطا: {str(e)[:300]}", reply_markup=back_to_menu())
    return ConversationHandler.END


# ---------- DNA inject conversation ----------
async def dna_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    assert q
    await q.answer()
    await q.edit_message_text("🧬 کد DNA رو بفرست (با <code>DNA1:</code> شروع میشه):",
                              parse_mode=ParseMode.HTML, reply_markup=cancel_conv())
    return LAB_DNAIN


async def dna_got(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cfg = _cfg(context)
    assert update.message and update.message.text
    uid = update.effective_user.id  # type: ignore
    try:
        a, b = await lab_svc.import_dna(cfg.db_path, uid, update.message.text.strip(),
                                        cfg.max_sources, cfg.max_dests)
        await update.message.reply_text(
            f"🧬 تزریق موفق! {a} مبدا و {b} مقصد اضافه شد + تنظیمات اعمال شد.",
            reply_markup=back_to_menu())
    except ValueError as e:
        await update.message.reply_text(f"❌ {e}", reply_markup=back_to_menu())
    return ConversationHandler.END


async def lab_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if q:
        await q.answer()
        await q.edit_message_text("❌ انصراف داده شد.", reply_markup=back_to_menu())
    elif update.message:
        await update.message.reply_text("❌ انصراف داده شد.", reply_markup=back_to_menu())
    return ConversationHandler.END


def register(app: Application) -> None:
    # NOTE: convs FIRST — PTB runs only the first matching handler per group,
    # so lab_router's broad ^lab: pattern must never swallow rain/dnain entries.
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(rain_start, pattern=r"^lab:rain$")],
        states={LAB_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, rain_got)]},
        fallbacks=[CallbackQueryHandler(lab_cancel, pattern=r"^conv:cancel$"),
                   CommandHandler("cancel", lab_cancel)],
        name="labrain", persistent=False))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(dna_start, pattern=r"^lab:dnain$")],
        states={LAB_DNAIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, dna_got)]},
        fallbacks=[CallbackQueryHandler(lab_cancel, pattern=r"^conv:cancel$"),
                   CommandHandler("cancel", lab_cancel)],
        name="labdna", persistent=False))
    app.add_handler(CallbackQueryHandler(lab_router, pattern=r"^lab:"))
