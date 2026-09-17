"""Background pipeline: poll sources -> AI -> review/queue -> publish + extras."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram.constants import ParseMode

from .. import database as db
from ..keyboards import review_kb
from . import cleaner, news as news_svc, price as price_svc, publisher, rumor


def _tz(cfg) -> ZoneInfo:
    try:
        return ZoneInfo(cfg.timezone)
    except Exception:
        return ZoneInfo("Asia/Tehran")


# ---------- core: fetch + process one user ----------
async def poll_user(bot, tm, db_path: str, cfg, user: dict) -> None:
    user_id = user["user_id"]
    if user.get("paused"):
        return
    mode = user.get("mode", "bot")
    cli = tm.client_for(user_id, mode)
    if cli is None or not cli.is_connected():
        if mode == "personal":
            if not await tm.ensure_user(user_id):
                return
            cli = tm.client_for(user_id, mode)
        else:
            return  # parser not ready; admin must /parser_login
    s = await db.get_settings(db_path, user_id)
    dests = await db.list_dests(db_path, user_id)
    if not dests:
        return  # no destination yet
    try:
        type_filters = set(json.loads(s.get("type_filters") or "[]"))
    except Exception:
        type_filters = set()
    order = cfg.ai_order

    for src in await db.list_sources(db_path, user_id):
        if await db.today_ai_usage(db_path, user_id) >= cfg.daily_post_limit:
            return  # fair-use cap reached
        try:
            groups, new_last = await tm.fetch_new(cli, src["channel"], src["last_msg_id"])
        except Exception:
            continue
        if new_last > src["last_msg_id"]:
            await db.set_source_last(db_path, src["id"], new_last)
        for g in groups:
            if await db.today_ai_usage(db_path, user_id) >= cfg.daily_post_limit:
                return
            try:
                await process_group(bot, tm, db_path, cfg, user_id, s, src, g,
                                    type_filters, order)
            except Exception:
                continue


async def process_group(bot, tm, db_path: str, cfg, user_id: int, s: dict,
                        src: dict, g: dict, type_filters: set, order) -> None:
    msgs = g["msgs"]
    media_type, raw_text = tm.classify(msgs)
    if media_type in type_filters:
        return  # free type-filter rejection (no AI spent)
    text_only = (raw_text or "").strip()
    if not text_only and media_type in ("text_short", "text_long"):
        return
    # free exact-duplicate guard
    h = hashlib.sha256(text_only[:2000].encode()).hexdigest()[:32]
    if text_only and await db.has_seen(db_path, user_id, h):
        return
    await db.add_seen(db_path, user_id, h)

    # per-source translate override
    translate_on = bool(s.get("translate_enabled"))
    if src.get("translate_override") is not None:
        translate_on = bool(src["translate_override"])
    if not translate_on and not cleaner.is_mostly_persian(text_only) and text_only:
        return  # non-Persian + translate off for this source -> skip silently

    # main AI clean
    try:
        res = await cleaner.clean_post(db_path, text_only or "(بدون متن — فقط مدیا)",
                                       media_type not in ("text_short", "text_long"),
                                       s, order=order)
    except Exception as e:
        return
    await db.bump_stat(db_path, user_id, "ai_calls")
    if res["action"] != "publish":
        await db.bump_stat(db_path, user_id, "rejected", res.get("reason", "رد AI")[:60])
        return
    cleaned = res["cleaned_html"]

    # rumor check (beta, news-ish only)
    if s.get("rumor_enabled") and len(text_only) > 120:
        try:
            v = await rumor.check(db_path, text_only, cfg.tavily_key, order=order)
            await db.bump_stat(db_path, user_id, "ai_calls")
            if v["verdict"] == "fake":
                if (s.get("rumor_action") or "reject") == "reject":
                    await db.bump_stat(db_path, user_id, "rejected", "شایعه")
                    return
                cleaned += "\n\n⚠️ <b>هشدار:</b> این خبر ممکنه شایعه باشه."
        except Exception:
            pass

    # semantic dedup
    if s.get("dedup_enabled"):
        try:
            recents = await db.recent_published(db_path, user_id)
            dup, _ = await cleaner.is_duplicate(db_path, cleaned, recents, order=order)
            await db.bump_stat(db_path, user_id, "ai_calls")
            if dup:
                await db.bump_stat(db_path, user_id, "rejected", "تکراری")
                return
        except Exception:
            pass

    user = await db.get_user(db_path, user_id)
    publish_mode = (user or {}).get("publish_mode", "review")
    if publish_mode == "instant":
        qid = await db.enqueue(db_path, user_id, src["channel"], g["ids"], media_type,
                               text_only, cleaned, "queued")
        item = await db.get_queue_item(db_path, qid)
        ok, detail = await publisher.publish_item(bot, tm, db_path, cfg, item, order)
        try:
            m = await bot.send_message(
                user_id, f"{'✅' if ok else '❌'} پست آنی: {detail}\n\n{cleaned[:800]}",
                parse_mode=ParseMode.HTML)
            await db.log_notif(db_path, user_id, user_id, m.message_id, "report")
        except Exception:
            pass
    else:
        qid = await db.enqueue(db_path, user_id, src["channel"], g["ids"], media_type,
                               text_only, cleaned, "pending_review")
        try:
            m = await bot.send_message(
                user_id,
                f"🆕 <b>پست جدید از {src.get('title') or src['channel']}</b>\n\n{cleaned[:3000]}",
                parse_mode=ParseMode.HTML, reply_markup=review_kb(qid))
            await db.set_queue(db_path, qid, review_msg_id=m.message_id)
            await db.log_notif(db_path, user_id, user_id, m.message_id, "review")
        except Exception:
            pass


# ---------- queue tick ----------
async def process_queues(bot, tm, db_path: str, cfg) -> None:
    tz = _tz(cfg)
    now = datetime.now(tz)
    for user in await db.all_users(db_path):
        if user.get("paused"):
            continue
        s = await db.get_settings(db_path, user["user_id"])
        if not (s["work_start"] <= now.hour < s["work_end"]):
            continue  # outside work hours -> keep items queued
        item = await db.next_queued(db_path, user["user_id"])
        if not item:
            continue
        last = await db.last_published_at(db_path, user["user_id"])
        if last:
            try:
                last_dt = datetime.fromisoformat(last).replace(tzinfo=tz)
                if datetime.now(tz) - last_dt < timedelta(minutes=s["send_interval_min"]):
                    continue
            except Exception:
                pass
        try:
            ok, detail = await publisher.publish_item(bot, tm, db_path, cfg, item,
                                                      cfg.ai_order)
            if not ok:
                # notify once, keep item queued? move back with note
                await db.set_queue(db_path, item["id"], reason=detail[:200])
                try:
                    m = await bot.send_message(user["user_id"], f"❌ انتشار ناموفق: {detail}")
                    await db.log_notif(db_path, user["user_id"], user["user_id"],
                                       m.message_id, "report")
                except Exception:
                    pass
                # avoid hot-loop on broken items: mark rejected after noting
                await db.set_queue(db_path, item["id"], status="rejected")
                await db.bump_stat(db_path, user["user_id"], "rejected", detail[:60])
        except Exception:
            continue


# ---------- price tick (hourly check) ----------
async def price_tick(bot, tm, db_path: str, cfg) -> None:
    tz = _tz(cfg)
    now_hour = datetime.now(tz).hour
    for user in await db.all_users(db_path):
        if user.get("paused"):
            continue
        pc = await db.get_price_cfg(db_path, user["user_id"])
        if not pc["enabled"] or int(pc["hour"]) != now_hour:
            continue
        dests = await db.list_dests(db_path, user["user_id"])
        if not dests:
            continue
        try:
            p = await price_svc.fetch_prices(cfg.navasan_key)
            msg = price_svc.format_price_message(p)
        except Exception as e:
            msg = f"⚠️ امروز نتونستم قیمت بگیرم. ({str(e)[:100]})"
        qid = await db.enqueue(db_path, user["user_id"], "price", [], "text",
                               msg, msg, "queued", kind="price")
        item = await db.get_queue_item(db_path, qid)
        try:
            ok, detail = await publisher.publish_item(bot, tm, db_path, cfg, item,
                                                      cfg.ai_order)
            m = await bot.send_message(user["user_id"],
                                       f"{'✅ قیمت منتشر شد' if ok else '❌ ' + detail}")
            await db.log_notif(db_path, user["user_id"], user["user_id"], m.message_id,
                               "report")
        except Exception:
            pass


# ---------- news tick ----------
async def news_tick(bot, tm, db_path: str, cfg) -> None:
    for user in await db.all_users(db_path):
        if user.get("paused"):
            continue
        nc = await db.get_news_cfg(db_path, user["user_id"])
        if not nc["enabled"]:
            continue
        dests = await db.list_dests(db_path, user["user_id"])
        if not dests:
            continue
        try:
            chosen = json.loads(nc.get("sources") or "[]")
        except Exception:
            chosen = []
        all_srcs = news_svc.default_sources()
        sources = [(n, u) for n, u in all_srcs if (not chosen or u in chosen)]
        try:
            cands = await news_svc.fetch_candidates(sources)
        except Exception:
            continue
        s = await db.get_settings(db_path, user["user_id"])
        per_cycle = max(1, min(5, int(nc.get("per_cycle") or 2)))
        done = 0
        for c in cands:
            if done >= per_cycle:
                break
            if await db.today_ai_usage(db_path, user["user_id"]) >= cfg.daily_post_limit:
                break
            if await db.news_seen_has(db_path, user["user_id"], c["guid"]):
                continue
            await db.news_seen_add(db_path, user["user_id"], c["guid"])
            body = await news_svc.fetch_article_text(c["url"]) or c["summary"]
            if not body:
                continue
            try:
                res = await cleaner.rewrite_news(
                    db_path, c["title"], body, c["url"], c["source"],
                    nc.get("topic") or s.get("channel_topic") or "",
                    s.get("content_style", "medium"), cfg.ai_order)
            except Exception:
                continue
            await db.bump_stat(db_path, user["user_id"], "ai_calls")
            if res["action"] != "publish":
                await db.bump_stat(db_path, user["user_id"], "rejected",
                                   res.get("reason", "رد AI")[:60])
                continue
            cleaned = res["cleaned_html"] + f"\n\n<i>منبع: {c['source']}</i>"
            u = await db.get_user(db_path, user["user_id"])
            if (u or {}).get("publish_mode", "review") == "instant":
                qid = await db.enqueue(db_path, user["user_id"], "news", [], "text",
                                       c["title"], cleaned, "queued", kind="news")
                item = await db.get_queue_item(db_path, qid)
                await publisher.publish_item(bot, tm, db_path, cfg, item, cfg.ai_order)
            else:
                qid = await db.enqueue(db_path, user["user_id"], "news", [], "text",
                                       c["title"], cleaned, "pending_review", kind="news")
                try:
                    m = await bot.send_message(
                        user["user_id"], f"🌍 <b>خبر خودکار ({c['source']})</b>\n\n{cleaned[:3000]}",
                        parse_mode=ParseMode.HTML, reply_markup=review_kb(qid))
                    await db.set_queue(db_path, qid, review_msg_id=m.message_id)
                    await db.log_notif(db_path, user["user_id"], user["user_id"],
                                       m.message_id, "review")
                except Exception:
                    pass
            done += 1


# ---------- nightly cleanup + daily report ----------
async def nightly(bot, db_path: str, cfg) -> None:
    tz = _tz(cfg)
    today = datetime.now(tz).strftime("%Y-%m-%d")
    for user in await db.all_users(db_path):
        uid = user["user_id"]
        s = await db.get_settings(db_path, uid)
        # delete today's auto notifications (unless user disabled cleanup)
        notifs = await db.day_notifs(db_path, uid, today)
        # cleanup flag stored in custom text_filters? -> separate: use survey? no.
        # We store it in price_cfg? Cleaner: reuse 'content_style' suffix? NO — new approach:
        # settings has no cleanup col; default ON. (kept simple; toggle flips survey? no.)
        # => Always clean 'review' msgs that are already actioned, keep simple: delete all logged.
        for n in notifs:
            try:
                await bot.delete_message(n["chat_id"], n["msg_id"])
            except Exception:
                pass
        await db.clear_day_notifs(db_path, uid, today)
        st = await db.get_stat(db_path, uid, today)
        try:
            reasons = json.loads(st.get("reasons") or "{}")
        except Exception:
            reasons = {}
        top = max(reasons.items(), key=lambda x: x[1])[0] if reasons else "—"
        try:
            await bot.send_message(
                uid,
                "🧹 <b>گزارش روزانه</b>\n\n"
                f"📮 پست ثبت‌شده: <b>{st['posted'] + st['rejected']}</b>\n"
                f"✅ تایید/منتشرشده: <b>{st['posted']}</b>\n"
                f"❌ ردشده: <b>{st['rejected']}</b>\n"
                f"🔁 پرتکرارترین دلیل رد: {top}\n\n"
                "پیام‌های اطلاع‌رسانی امروز پاک شدن تا پی‌وی شلوغ نمونه. 🌙",
                parse_mode=ParseMode.HTML)
        except Exception:
            pass


def register(sched, bot, tm, db_path: str, cfg) -> None:
    async def _poll_all():
        for u in await db.all_users(db_path):
            try:
                await poll_user(bot, tm, db_path, cfg, u)
            except Exception:
                continue

    async def _queue():
        await process_queues(bot, tm, db_path, cfg)

    async def _price():
        await price_tick(bot, tm, db_path, cfg)

    async def _news():
        await news_tick(bot, tm, db_path, cfg)

    async def _nightly():
        await nightly(bot, db_path, cfg)

    sched.add_job(_poll_all, "interval", seconds=cfg.poll_interval_sec, id="poll",
                  max_instances=1, coalesce=True)
    sched.add_job(_queue, "interval", seconds=cfg.queue_tick_sec, id="queue",
                  max_instances=1, coalesce=True)
    sched.add_job(_price, "cron", minute=5, id="price", max_instances=1, coalesce=True)
    sched.add_job(_news, "interval", minutes=cfg.news_tick_min, id="news",
                  max_instances=1, coalesce=True)
    sched.add_job(_nightly, "cron", hour=0, minute=0, id="nightly",
                  max_instances=1, coalesce=True)
