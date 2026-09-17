"""Publish/content/auto/panel settings + generic text-input conversation."""
from __future__ import annotations

import json

import aiosqlite
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, ConversationHandler, MessageHandler, filters)

from .. import database as db
from ..keyboards import (auto_menu, auto_news_sub, auto_price_sub, back_to_menu,
                         cancel_conv, cycle_prem, cycle_sig, panel_menu, pub_menu,
                         style_menu)
from ..texts import TEXT_FILTER_LABELS, TYPE_LABELS, DEFAULT_NEWS_SOURCES

EDIT_VALUE = 20

EDIT_PROMPTS = {
    "interval": "⏱️ فاصله ارسال (دقیقه) رو بفرست — عدد بین ۵ تا ۱۴۴۰:\nمثال: <code>30</code>",
    "workhours": "📅 ساعت کاری رو بفرست — فرمت: <code>شروع-پایان</code>\nمثال: <code>8-23</code> (یعنی ۸ صبح تا ۱۱ شب) — برای ۲۴ساعته: <code>0-24</code>",
    "rule": "📜 قانون سفارشی AI رو بفرست (حداکثر ۲۵۰ کاراکتر).\nمثال: <code>پست‌های حامی فلان جریان رو نذار</code>\nبرای حذف، کلمه <code>حذف</code> رو بفرست.",
    "topic": "📍 موضوع اصلی کانالت رو بفرست.\nمثال: <code>ورزشی</code> یا <code>اقتصادی</code>\nبرای حذف: <code>حذف</code>",
    "sigtext": "✍️ متن امضای زیر پست رو بفرست (می‌تونی از فرمت HTML تلگرام استفاده کنی):",
    "sigword": "🔗 کلمه‌ای که باید لینک بشه رو بفرست:\nمثال: <code>عضویت در کانال</code>",
    "sigurl": "🔗 آدرس لینک رو بفرست:\nمثال: <code>https://t.me/yourchannel</code>",
    "pricehour": "🕘 ساعت انتشار قیمت روزانه رو بفرست — عدد ۰ تا ۲۳:\nمثال: <code>9</code>",
    "newstopic": "🎯 موضوع اخبار خودکار رو بفرست.\nمثال: <code>تکنولوژی</code> — برای همه موضوعات: <code>حذف</code>",
    "newscount": "🔢 تعداد پست هر دوره اخبار رو بفرست — عدد ۱ تا ۵:",
}


def _cfg(context):
    return context.application.bot_data["cfg"]


# ---------- publish/style/panel/auto routers ----------
async def st_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg, q = _cfg(context), update.callback_query
    assert q and q.data
    await q.answer()
    uid = q.from_user.id
    act = q.data.split(":", 1)[1]
    s = await db.get_settings(cfg.db_path, uid)
    u = await db.get_user(cfg.db_path, uid)

    if act == "pubmode":
        new = "instant" if u["publish_mode"] == "review" else "review"
        await db.set_user(cfg.db_path, uid, publish_mode=new)
        label = "🔍 بررسی" if new == "review" else "⚡ آنی"
        await q.edit_message_text("مدل انتشار شد: " + label,
                                  parse_mode=ParseMode.HTML,
                                  reply_markup=pub_menu(s, new))
    elif act == "style":
        new = "short" if s["content_style"] != "short" else "medium"
        await db.set_settings(cfg.db_path, uid, content_style=new)
        await q.edit_message_text("🕐 <b>تنظیمات انتشار</b>", parse_mode=ParseMode.HTML,
                                  reply_markup=pub_menu({**s, "content_style": new}, u["publish_mode"]))
    elif act == "clearq":
        async with aiosqlite.connect(cfg.db_path) as d:
            await d.execute("DELETE FROM queue WHERE user_id=? AND status IN ('queued','pending_review')", (uid,))
            await d.commit()
        await q.edit_message_text("🗑️ صف انتشار خالی شد.", reply_markup=pub_menu(s, u["publish_mode"]))
    elif act == "tr":
        await db.set_settings(cfg.db_path, uid, translate_enabled=0 if s["translate_enabled"] else 1)
        s2 = await db.get_settings(cfg.db_path, uid)
        await q.edit_message_text("🎨 <b>استایل و فیلتر محتوا</b>", parse_mode=ParseMode.HTML,
                                  reply_markup=style_menu(s2))
    elif act == "dd":
        await db.set_settings(cfg.db_path, uid, dedup_enabled=0 if s["dedup_enabled"] else 1)
        s2 = await db.get_settings(cfg.db_path, uid)
        await q.edit_message_text("🎨 <b>استایل و فیلتر محتوا</b>", parse_mode=ParseMode.HTML,
                                  reply_markup=style_menu(s2))
    elif act == "rumor":
        if not s["rumor_enabled"]:
            await db.set_settings(cfg.db_path, uid, rumor_enabled=1)
            s2 = await db.get_settings(cfg.db_path, uid)
            await q.edit_message_text(
                "🕵️ بررسی شایعه <b>روشن</b> شد.\n\nاقدام در صورت شایعه بودن:", parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚫 رد کن (پیش‌فرض)" + (" ✅" if s2["rumor_action"] == "reject" else ""),
                                          callback_data="rm:reject")],
                    [InlineKeyboardButton("⚠️ منتشر کن با هشدار" + (" ✅" if s2["rumor_action"] == "warn" else ""),
                                          callback_data="rm:warn")],
                    [InlineKeyboardButton("⬅️ بازگشت", callback_data="m:style")]]))
        else:
            await db.set_settings(cfg.db_path, uid, rumor_enabled=0)
            s2 = await db.get_settings(cfg.db_path, uid)
            await q.edit_message_text("🎨 <b>استایل و فیلتر محتوا</b>", parse_mode=ParseMode.HTML,
                                      reply_markup=style_menu(s2))
    elif act == "sig":
        await q.edit_message_text("📋 <b>امضای زیر پست</b> — یکی رو انتخاب کن:", parse_mode=ParseMode.HTML,
                                  reply_markup=cycle_sig())
    elif act == "prem":
        await q.edit_message_text("💡 <b>حالت اموجی پرمیوم</b> — یکی رو انتخاب کن:", parse_mode=ParseMode.HTML,
                                  reply_markup=cycle_prem())
    elif act == "types":
        await show_type_filters(update, context)
    elif act == "texts":
        await show_text_filters(update, context)


async def rm_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg, q = _cfg(context), update.callback_query
    assert q and q.data
    await q.answer("ذخیره شد ✅")
    await db.set_settings(cfg.db_path, q.from_user.id,
                          rumor_action=q.data.split(":")[1], rumor_enabled=1)
    s = await db.get_settings(cfg.db_path, q.from_user.id)
    await q.edit_message_text("🎨 <b>استایل و فیلتر محتوا</b>", parse_mode=ParseMode.HTML,
                              reply_markup=style_menu(s))


async def sig_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    cfg, q = _cfg(context), update.callback_query
    assert q and q.data
    mode = q.data.split(":")[1]
    if mode == "none":
        await q.answer("ذخیره شد ✅")
        await db.set_settings(cfg.db_path, q.from_user.id, signature_mode="none")
        s = await db.get_settings(cfg.db_path, q.from_user.id)
        await q.edit_message_text("🎨 <b>استایل و فیلتر محتوا</b>", parse_mode=ParseMode.HTML,
                                  reply_markup=style_menu(s))
        return None
    await q.answer()
    context.user_data["edit_field"] = "sigtext" if mode == "text" else "sigword"
    context.user_data["edit_sigmode"] = mode
    await q.edit_message_text(EDIT_PROMPTS[context.user_data["edit_field"]],
                              parse_mode=ParseMode.HTML, reply_markup=cancel_conv())
    from telegram.ext import ConversationHandler
    return EDIT_VALUE


async def prem_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg, q = _cfg(context), update.callback_query
    assert q and q.data
    await q.answer("ذخیره شد ✅")
    await db.set_settings(cfg.db_path, q.from_user.id, premium_mode=q.data.split(":")[1])
    s = await db.get_settings(cfg.db_path, q.from_user.id)
    await q.edit_message_text("🎨 <b>استایل و فیلتر محتوا</b>", parse_mode=ParseMode.HTML,
                              reply_markup=style_menu(s))


async def show_type_filters(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg, q = _cfg(context), update.callback_query
    assert q
    await q.answer()
    s = await db.get_settings(cfg.db_path, q.from_user.id)
    try:
        disabled = set(json.loads(s.get("type_filters") or "[]"))
    except Exception:
        disabled = set()
    rows = []
    for key, label in TYPE_LABELS.items():
        mark = "❌" if key in disabled else "✅"
        rows.append([InlineKeyboardButton(f"{mark} {label}", callback_data=f"tf:{key}")])
    rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="m:style")])
    await q.edit_message_text("🚦 <b>فیلتر نوع محتوا</b>\n\nنوع‌های ❌شده اصلاً به AI نمی‌رسن (رایگان رد میشن).",
                              parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(rows))


async def tf_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg, q = _cfg(context), update.callback_query
    assert q and q.data
    await q.answer()
    key = q.data.split(":")[1]
    s = await db.get_settings(cfg.db_path, q.from_user.id)
    try:
        disabled = set(json.loads(s.get("type_filters") or "[]"))
    except Exception:
        disabled = set()
    disabled.discard(key) if key in disabled else disabled.add(key)
    await db.set_settings(cfg.db_path, q.from_user.id, type_filters=json.dumps(sorted(disabled)))
    await show_type_filters(update, context)


async def show_text_filters(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg, q = _cfg(context), update.callback_query
    assert q
    await q.answer()
    s = await db.get_settings(cfg.db_path, q.from_user.id)
    try:
        enabled = set(json.loads(s.get("text_filters") or "[]"))
    except Exception:
        enabled = set()
    rows = []
    for key, label in TEXT_FILTER_LABELS.items():
        mark = "✅" if key in enabled else "❌"
        rows.append([InlineKeyboardButton(f"{mark} {label}", callback_data=f"xf:{key}")])
    rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="m:style")])
    await q.edit_message_text("⛔ <b>فیلتر محتوای متنی</b>\n\nموارد ✅شده باعث رد پست میشن.",
                              parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(rows))


async def xf_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg, q = _cfg(context), update.callback_query
    assert q and q.data
    await q.answer()
    key = q.data.split(":")[1]
    s = await db.get_settings(cfg.db_path, q.from_user.id)
    try:
        enabled = set(json.loads(s.get("text_filters") or "[]"))
    except Exception:
        enabled = set()
    enabled.discard(key) if key in enabled else enabled.add(key)
    await db.set_settings(cfg.db_path, q.from_user.id, text_filters=json.dumps(sorted(enabled)))
    await show_text_filters(update, context)


async def pn_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg, q = _cfg(context), update.callback_query
    assert q and q.data
    await q.answer()
    act = q.data.split(":", 1)[1]
    uid = q.from_user.id
    u = await db.get_user(cfg.db_path, uid)
    s = await db.get_settings(cfg.db_path, uid)
    if act == "pause":
        await db.set_user(cfg.db_path, uid, paused=0 if u["paused"] else 1)
        u = await db.get_user(cfg.db_path, uid)
    elif act == "survey":
        await db.set_settings(cfg.db_path, uid, survey_mode=0 if s["survey_mode"] else 1)
        s = await db.get_settings(cfg.db_path, uid)
    elif act == "clean":
        await q.edit_message_text("🧹 پاکسازی خودکار پی‌وی هر شب ساعت ۱۲ انجام میشه و قابل خاموش‌کردن نیست (برای جلوگیری از شلوغی در نسخه رایگان).",
                                  reply_markup=panel_menu(bool(u["paused"]), bool(s["survey_mode"])))
        return
    await q.edit_message_text("🎛️ <b>کنترل پنل</b>", parse_mode=ParseMode.HTML,
                              reply_markup=panel_menu(bool(u["paused"]), bool(s["survey_mode"])))


async def au_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg, q = _cfg(context), update.callback_query
    assert q and q.data
    await q.answer()
    uid = q.from_user.id
    act = q.data.split(":", 1)[1]
    price = await db.get_price_cfg(cfg.db_path, uid)
    news = await db.get_news_cfg(cfg.db_path, uid)
    if act == "price":
        await q.edit_message_text("💲 <b>قیمت دلار و طلا</b>\n\nهر روز سر ساعت مشخص یه پیام کوتاه تو کانالت منتشر میشه.",
                                  parse_mode=ParseMode.HTML, reply_markup=auto_price_sub(price))
    elif act == "price_t":
        await db.set_price_cfg(cfg.db_path, uid, enabled=0 if price["enabled"] else 1)
        price = await db.get_price_cfg(cfg.db_path, uid)
        await q.edit_message_text("💲 <b>قیمت دلار و طلا</b>", parse_mode=ParseMode.HTML,
                                  reply_markup=auto_price_sub(price))
    elif act == "news":
        await q.edit_message_text("🌍 <b>اخبار خودکار</b>", parse_mode=ParseMode.HTML,
                                  reply_markup=auto_news_sub(news))
    elif act == "news_t":
        await db.set_news_cfg(cfg.db_path, uid, enabled=0 if news["enabled"] else 1)
        news = await db.get_news_cfg(cfg.db_path, uid)
        await q.edit_message_text("🌍 <b>اخبار خودکار</b>", parse_mode=ParseMode.HTML,
                                  reply_markup=auto_news_sub(news))
    elif act == "newssrc":
        try:
            chosen = set(json.loads(news.get("sources") or "[]"))
        except Exception:
            chosen = set()
        rows = []
        for name, url in DEFAULT_NEWS_SOURCES:
            on = (not chosen) or (url in chosen)
            rows.append([InlineKeyboardButton(f"{'✅' if on else '❌'} {name}", callback_data=f"ns:{url}")])
        rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="au:news")])
        await q.edit_message_text("📰 <b>منابع خبری</b>\n\nاگه همه خاموش باشن = همه منابع فعالن.", parse_mode=ParseMode.HTML,
                                  reply_markup=InlineKeyboardMarkup(rows))


async def ns_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg, q = _cfg(context), update.callback_query
    assert q and q.data
    await q.answer()
    url = q.data.split(":", 1)[1]
    news = await db.get_news_cfg(cfg.db_path, q.from_user.id)
    try:
        chosen = set(json.loads(news.get("sources") or "[]"))
    except Exception:
        chosen = set()
    all_urls = {u for _, u in DEFAULT_NEWS_SOURCES}
    if not chosen:
        chosen = set(all_urls)
    chosen.discard(url) if url in chosen else chosen.add(url)
    if chosen == all_urls:
        chosen = set()  # all = default
    await db.set_news_cfg(cfg.db_path, q.from_user.id, sources=json.dumps(sorted(chosen)))
    # redraw
    news = await db.get_news_cfg(cfg.db_path, q.from_user.id)
    try:
        chosen2 = set(json.loads(news.get("sources") or "[]"))
    except Exception:
        chosen2 = set()
    rows = []
    for name, u2 in DEFAULT_NEWS_SOURCES:
        on = (not chosen2) or (u2 in chosen2)
        rows.append([InlineKeyboardButton(f"{'✅' if on else '❌'} {name}", callback_data=f"ns:{u2}")])
    rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="au:news")])
    await q.edit_message_text("📰 <b>منابع خبری</b>", parse_mode=ParseMode.HTML,
                              reply_markup=InlineKeyboardMarkup(rows))


# ---------- generic text edit conversation ----------
async def edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    assert q and q.data
    await q.answer()
    field = q.data.split(":", 1)[1]
    context.user_data["edit_field"] = field
    await q.edit_message_text(EDIT_PROMPTS[field], parse_mode=ParseMode.HTML,
                              reply_markup=cancel_conv())
    return EDIT_VALUE


async def edit_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cfg = _cfg(context)
    assert update.message and update.message.text
    uid = update.effective_user.id  # type: ignore
    field = context.user_data.get("edit_field", "")
    val = update.message.text.strip()
    try:
        if field == "interval":
            n = int(val)
            assert 5 <= n <= 1440
            await db.set_settings(cfg.db_path, uid, send_interval_min=n)
            ok = f"⏱️ فاصله ارسال شد: <b>{n} دقیقه</b>"
        elif field == "workhours":
            a, b = val.replace(" ", "").split("-")
            a, b = int(a), int(b)
            assert 0 <= a < 24 and 0 < b <= 24 and a < b
            await db.set_settings(cfg.db_path, uid, work_start=a, work_end=b)
            ok = f"📅 ساعت کاری شد: <b>{a}:00 تا {b}:00</b>"
        elif field == "rule":
            await db.set_settings(cfg.db_path, uid, custom_rule="" if val == "حذف" else val[:250])
            ok = "📜 قانون سفارشی " + ("حذف شد." if val == "حذف" else "ذخیره شد ✅")
        elif field == "topic":
            await db.set_settings(cfg.db_path, uid, channel_topic="" if val == "حذف" else val[:100])
            ok = "📍 موضوع کانال " + ("حذف شد." if val == "حذف" else f"شد: <b>{val[:100]}</b>")
        elif field == "sigtext":
            await db.set_settings(cfg.db_path, uid, signature_mode="text", signature_text=val[:500])
            ok = "📋 امضای متنی ذخیره شد ✅"
        elif field == "sigword":
            context.user_data["sig_word"] = val[:100]
            await update.message.reply_text(EDIT_PROMPTS["sigurl"], parse_mode=ParseMode.HTML,
                                            reply_markup=cancel_conv())
            context.user_data["edit_field"] = "sigurl"
            return EDIT_VALUE
        elif field == "sigurl":
            word = context.user_data.get("sig_word", "لینک")
            assert val.startswith("http")
            await db.set_settings(cfg.db_path, uid, signature_mode="link",
                                  signature_word=word, signature_url=val[:300])
            ok = "🔗 امضای لینک‌دار ذخیره شد ✅"
        elif field == "pricehour":
            n = int(val)
            assert 0 <= n <= 23
            await db.set_price_cfg(cfg.db_path, uid, hour=n)
            ok = f"🕘 ساعت انتشار قیمت شد: <b>{n}</b>"
        elif field == "newstopic":
            await db.set_news_cfg(cfg.db_path, uid, topic="" if val == "حذف" else val[:100])
            ok = "🎯 موضوع اخبار " + ("حذف شد (همه موضوعات)." if val == "حذف" else "ذخیره شد ✅")
        elif field == "newscount":
            n = int(val)
            assert 1 <= n <= 5
            await db.set_news_cfg(cfg.db_path, uid, per_cycle=n)
            ok = f"🔢 تعداد هر دوره شد: <b>{n}</b>"
        else:
            ok = "؟"
    except (ValueError, AssertionError):
        await update.message.reply_text("❌ ورودی نامعتبره! دوباره بفرست:", reply_markup=cancel_conv())
        return EDIT_VALUE
    await update.message.reply_text(ok, parse_mode=ParseMode.HTML,
                                    reply_markup=back_to_menu())
    return ConversationHandler.END


async def edit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    if q:
        await q.answer()
        await q.edit_message_text("❌ انصراف داده شد.", reply_markup=back_to_menu())
    return ConversationHandler.END


def register(app: Application) -> None:
    app.add_handler(CallbackQueryHandler(st_router, pattern=r"^st:"))
    app.add_handler(CallbackQueryHandler(rm_router, pattern=r"^rm:"))
    app.add_handler(CallbackQueryHandler(prem_router, pattern=r"^prem:"))
    app.add_handler(CallbackQueryHandler(tf_router, pattern=r"^tf:"))
    app.add_handler(CallbackQueryHandler(xf_router, pattern=r"^xf:"))
    app.add_handler(CallbackQueryHandler(pn_router, pattern=r"^pn:"))
    app.add_handler(CallbackQueryHandler(au_router, pattern=r"^au:"))
    app.add_handler(CallbackQueryHandler(ns_router, pattern=r"^ns:"))
    # signature choices join the edit conversation (they ask for text input)
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_start, pattern=r"^edit:"),
                      CallbackQueryHandler(sig_router, pattern=r"^sig:")],
        states={EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_received)]},
        fallbacks=[CallbackQueryHandler(edit_cancel, pattern=r"^conv:cancel$"),
                   CommandHandler("cancel", edit_cancel)],
        name="edit", persistent=False))
