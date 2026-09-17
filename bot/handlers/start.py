""" /start, main menu, help carousel, stats, announcements. """
from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from .. import database as db
from ..keyboards import (auto_menu, back_to_menu, conn_menu, help_list, help_nav,
                         keys_menu, main_menu, onboarding_nav, panel_menu, pub_menu,
                         style_menu)
from ..texts import HELP_TOPICS, MENU_STATUS, ONBOARDING, START_TEXT
from ..services import ai_router


def _cfg(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["cfg"]


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = _cfg(context)
    user = update.effective_user
    assert user and update.message
    await db.ensure_user(cfg.db_path, user.id)
    await update.message.reply_text(START_TEXT, parse_mode=ParseMode.HTML,
                                    reply_markup=main_menu())


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = _cfg(context)
    q = update.callback_query
    assert q
    await q.answer()
    u = await db.ensure_user(cfg.db_path, q.from_user.id)
    s = await db.get_settings(cfg.db_path, q.from_user.id)
    used = await db.today_ai_usage(cfg.db_path, q.from_user.id)
    srcs = await db.list_sources(cfg.db_path, q.from_user.id)
    dsts = await db.list_dests(cfg.db_path, q.from_user.id)
    mode = "🤖 حالت ربات" if u["mode"] == "bot" else "👤 اکانت شخصی"
    text = MENU_STATUS.format(used=used, limit=cfg.daily_post_limit, mode=mode,
                              nsrc=len(srcs), ndst=len(dsts),
                              paused="⏸️ متوقف" if u["paused"] else "▶️ فعال")
    await q.edit_message_text(text, parse_mode=ParseMode.HTML,
                              reply_markup=main_menu())


async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = _cfg(context)
    q = update.callback_query
    assert q and q.data
    await q.answer()
    uid = q.from_user.id
    action = q.data.split(":", 1)[1] if ":" in q.data else "menu"
    u = await db.ensure_user(cfg.db_path, uid)
    s = await db.get_settings(cfg.db_path, uid)

    if action == "menu":
        return await show_menu(update, context)
    if action == "conn":
        connected = bool((u.get("session") or "").strip())
        srcs = await db.list_sources(cfg.db_path, uid)
        dsts = await db.list_dests(cfg.db_path, uid)
        mode = "حالت ربات (پیش‌فرض رایگان)" if u["mode"] == "bot" else "اکانت شخصی"
        await q.edit_message_text(
            f"🔗 <b>اتصال و کانال‌ها</b>\n\nوضعیت اتصال: <b>{mode}</b>\n"
            f"کانال‌های مبدا: {len(srcs)}/{cfg.max_sources}\nکانال‌های مقصد: {len(dsts)}/{cfg.max_dests}",
            parse_mode=ParseMode.HTML, reply_markup=conn_menu(u["mode"], connected))
    elif action == "pub":
        await q.edit_message_text(
            "🕐 <b>تنظیمات انتشار</b>\n\nفاصله‌ی ارسال، ساعت کاری، طول متن، و مدیریت زمان‌بندی در صف.",
            parse_mode=ParseMode.HTML, reply_markup=pub_menu(s, u["publish_mode"]))
    elif action == "style":
        await q.edit_message_text(
            "🎨 <b>استایل و فیلتر محتوا</b>\n\nامضا، اموجی، ترجمه، تکراری، شایعه و فیلترها.",
            parse_mode=ParseMode.HTML, reply_markup=style_menu(s))
    elif action == "panel":
        await q.edit_message_text(
            "🎛️ <b>کنترل پنل</b>\n\nتوقف/شروع کل پردازش و مود نظرسنجی.",
            parse_mode=ParseMode.HTML,
            reply_markup=panel_menu(bool(u["paused"]), bool(s["survey_mode"])))
    elif action == "stats":
        st = await db.get_stat(cfg.db_path, uid)
        qn = await db.count_queued(cfg.db_path, uid)
        await q.edit_message_text(
            "📊 <b>محدودیت و آمار</b>\n\n"
            f"⚡ مصرف AI امروز: <b>{st['ai_calls']}/{cfg.daily_post_limit}</b> (هر شب ۱۲ ریست میشه)\n"
            f"📮 منتشرشده امروز: <b>{st['posted']}</b>\n❌ ردشده امروز: <b>{st['rejected']}</b>\n"
            f"⏳ تو صف/در انتظار بررسی: <b>{qn}</b>\n\n"
            "🆓 اینجا کردیتی در کار نیست؛ فقط سقف منصفانه روزانه برای محافظت از سهمیه رایگان AI.",
            parse_mode=ParseMode.HTML, reply_markup=back_to_menu())
    elif action == "auto":
        price = await db.get_price_cfg(cfg.db_path, uid)
        news = await db.get_news_cfg(cfg.db_path, uid)
        await q.edit_message_text("🌍 <b>محتوای خودکار</b>\n\nقیمت دلار/طلا و اخبار خودکار.",
                                  parse_mode=ParseMode.HTML, reply_markup=auto_menu(price, news))
    elif action == "keys":
        stats = await ai_router.pool_stats(cfg.db_path)
        lines = [f"🔑 <b>کلیدهای AI (روتر)</b>\n\n🧩 استخر مشترک: <b>{stats['active']}</b> کلید فعال"]
        for p, v in stats["by_provider"].items():
            lines.append(f"• {p}: {v['active']} فعال / {v['dead']} خراب (✅{v['ok']} ❌{v['fail']})")
        lines.append("\nبا «🎁 اهدای کلید» کلید رایگانت رو اضافه کن؛ ربات اول تستش می‌کنه بعد استفاده می‌کنه.")
        await q.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML,
                                  reply_markup=keys_menu(stats["active"]))
    elif action == "annc":
        items = await db.list_annc(cfg.db_path)
        text = "🔔 <b>اعلان‌ها</b>\n\n" + ("\n\n---\n\n".join(x["text"] for x in items) if items else "فعلاً اعلانی نیست.")
        await q.edit_message_text(text[:3500], parse_mode=ParseMode.HTML,
                                  reply_markup=back_to_menu())
    elif action == "help":
        await show_help(update, context, 0)


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE, idx: int = 0) -> None:
    q = update.callback_query
    assert q
    await q.answer()
    _, title, body = HELP_TOPICS[idx]
    await q.edit_message_text(f"{body}\n\n<i>{idx+1} از {len(HELP_TOPICS)}</i>",
                              parse_mode=ParseMode.HTML, reply_markup=help_nav(idx))


async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert q and q.data
    idx = int(q.data.split(":")[1])
    await show_help(update, context, idx)


async def help_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert q
    await q.answer()
    await q.edit_message_text("📚 <b>لیست موضوعات راهنما</b>\n\nیکی رو انتخاب کن:",
                              parse_mode=ParseMode.HTML, reply_markup=help_list())


async def onboarding_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    assert q and q.data
    await q.answer()
    idx = max(0, min(len(ONBOARDING) - 1, int(q.data.split(":")[1])))
    title, body = ONBOARDING[idx]
    await q.edit_message_text(body, parse_mode=ParseMode.HTML,
                              reply_markup=onboarding_nav(idx))


async def noop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if q:
        await q.answer()


def register(app: Application) -> None:
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(menu_router, pattern=r"^m:"))
    app.add_handler(CallbackQueryHandler(help_callback, pattern=r"^h:\d+$"))
    app.add_handler(CallbackQueryHandler(help_list_callback, pattern=r"^hl$"))
    app.add_handler(CallbackQueryHandler(onboarding_callback, pattern=r"^ob:\d+$"))
    app.add_handler(CallbackQueryHandler(noop, pattern=r"^noop$"))
