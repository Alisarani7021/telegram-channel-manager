"""Publish queue items to destination channels.

Personal mode -> via the user's own Telethon client (preserves formatting/premium).
Bot mode      -> via the Bot API (bot must be admin of the destination).
"""
from __future__ import annotations

import html
import io
import json

from telegram import InputMediaPhoto, InputMediaVideo
from telegram.constants import ParseMode
from telegram.error import TelegramError

from .. import database as db
from . import cleaner


def apply_signature(clean_html: str, s: dict) -> str:
    mode = s.get("signature_mode", "none")
    if mode == "text" and s.get("signature_text"):
        return clean_html + "\n\n" + s["signature_text"]
    if mode == "link" and s.get("signature_url") and s.get("signature_word"):
        url = html.escape(s["signature_url"], quote=True)
        word = html.escape(s["signature_word"])
        return clean_html + f'\n\n<a href="{url}">{word}</a>'
    return clean_html


def _split_caption(text_html: str, limit: int = 1000) -> tuple[str, str]:
    if len(text_html) <= limit:
        return text_html, ""
    cut = text_html.rfind("\n", 0, limit)
    cut = cut if cut > 200 else limit
    return text_html[:cut], text_html[cut:]


async def _publish_personal(tm, user_id: int, dest_ref: str, item: dict,
                            final_html: str, media: list[dict]) -> None:
    cli = tm.users.get(user_id)
    if not cli:
        raise RuntimeError("اکانت شخصی وصل نیست.")
    ent = await tm.get_input_entity(cli, dest_ref)
    if item.get("kind") == "poll":
        extra = json.loads(item.get("extra") or "{}")
        poll = extra.get("poll")
        if poll:
            from telethon.tl.types import InputMediaPoll, Poll, PollAnswer
            answers = [PollAnswer(str(o)[:90], bytes([i])) for i, o in
                       enumerate(poll["options"][:6])]
            await cli.send_message(
                ent, file=InputMediaPoll(
                    poll=Poll(id=hash(poll["question"]) % 10**10,
                              question=poll["question"][:250], answers=answers)))
            return
    if media:
        from telethon.tl.types import DocumentAttributeFilename
        files = []
        for m in media:
            bio = io.BytesIO(m["bytes"])
            bio.name = m.get("name", "file.bin")
            files.append(bio)
        cap, rest = _split_caption(final_html)
        if len(files) == 1:
            await cli.send_file(ent, files[0], caption=cap or "‎", parse_mode="html")
        else:
            await cli.send_file(ent, files, caption=cap or "‎", parse_mode="html")
        if rest.strip():
            await cli.send_message(ent, rest, parse_mode="html")
    else:
        # long text -> split
        for i in range(0, len(final_html), 4000):
            await cli.send_message(ent, final_html[i:i+4000] or "‎", parse_mode="html")


async def _publish_botmode(bot, dest_ref: str, item: dict, final_html: str,
                           media: list[dict]) -> None:
    if item.get("kind") == "poll":
        extra = json.loads(item.get("extra") or "{}")
        poll = extra.get("poll")
        if poll:
            await bot.send_poll(dest_ref, poll["question"][:250], poll["options"][:6])
            return
    if not media:
        for i in range(0, len(final_html), 4000):
            await bot.send_message(dest_ref, final_html[i:i+4000] or "‎",
                                   parse_mode=ParseMode.HTML)
        return
    if len(media) == 1:
        m = media[0]
        cap, rest = _split_caption(final_html)
        bio = io.BytesIO(m["bytes"])
        bio.name = m.get("name", "file.bin")
        try:
            if m["mime"].startswith("image/"):
                await bot.send_photo(dest_ref, photo=bio, caption=cap or None,
                                     parse_mode=ParseMode.HTML)
            elif m["mime"].startswith("video/"):
                await bot.send_video(dest_ref, video=bio, caption=cap or None,
                                     parse_mode=ParseMode.HTML)
            elif m["mime"].startswith("audio/") or m["mime"] == "audio/ogg":
                await bot.send_voice(dest_ref, voice=bio, caption=cap or None,
                                     parse_mode=ParseMode.HTML)
            else:
                await bot.send_document(dest_ref, document=bio, caption=cap or None,
                                        parse_mode=ParseMode.HTML)
        except TelegramError:
            bio.seek(0)
            await bot.send_document(dest_ref, document=bio, caption=cap or None,
                                    parse_mode=ParseMode.HTML)
        if rest.strip():
            for i in range(0, len(rest), 4000):
                await bot.send_message(dest_ref, rest[i:i+4000], parse_mode=ParseMode.HTML)
    else:
        grp: list = []
        cap, rest = _split_caption(final_html)
        for i, m in enumerate(media[:10]):
            bio = io.BytesIO(m["bytes"])
            bio.name = m.get("name", "file.bin")
            c = cap if i == 0 else None
            if m["mime"].startswith("video/"):
                grp.append(InputMediaVideo(bio, caption=c, parse_mode=ParseMode.HTML))
            else:
                grp.append(InputMediaPhoto(bio, caption=c, parse_mode=ParseMode.HTML))
        await bot.send_media_group(dest_ref, grp)
        if rest.strip():
            for i in range(0, len(rest), 4000):
                await bot.send_message(dest_ref, rest[i:i+4000], parse_mode=ParseMode.HTML)


async def publish_item(bot, tm, db_path: str, settings_cfg, item: dict,
                       order: list[str] | None = None) -> tuple[bool, str]:
    """Publish one queue item. Returns (ok, detail)."""
    user_id = item["user_id"]
    user = await db.get_user(db_path, user_id)
    s = await db.get_settings(db_path, user_id)
    dests = await db.list_dests(db_path, user_id)
    if not dests:
        return False, "کانال مقصد نداری."
    dest_ref = dests[0]["channel"]
    mode = (user or {}).get("mode", "bot")
    if mode == "personal" and user_id not in tm.users:
        if not await tm.ensure_user(user_id):
            return False, "اکانت شخصی قطع شده؛ دوباره وصل شو."

    # survey mode: build poll from cleaned text (reposts only)
    if s.get("survey_mode") and item.get("kind") == "repost":
        try:
            poll = await cleaner.make_poll(db_path, item.get("text_clean") or
                                           item.get("text_raw") or "", order=order)
            if poll:
                extra = json.loads(item.get("extra") or "{}")
                extra["poll"] = poll
                item["extra"] = json.dumps(extra, ensure_ascii=False)
                item["kind"] = "poll"
        except Exception:
            pass  # fall back to normal post

    final_html = apply_signature(item.get("text_clean") or "", s)

    # download media from source (except pure generated kinds)
    media: list[dict] = []
    if item.get("kind") == "repost":
        cli = tm.client_for(user_id, mode)
        if cli is None:
            return False, "کلاینت تلگرام آماده نیست."
        try:
            ids = json.loads(item.get("source_msg_ids") or "[]")
            msgs = await cli.get_messages(item["source"], ids=ids) if ids else []
            if msgs:
                msgs = msgs if isinstance(msgs, list) else [msgs]
                msgs = [m for m in msgs if m]
                if msgs:
                    media = await tm.download_group(cli, msgs)
        except Exception as e:
            return False, f"دانلود مدیا ناموفق بود: {str(e)[:120]}"

    try:
        if mode == "personal":
            await _publish_personal(tm, user_id, dest_ref, item, final_html, media)
        else:
            await _publish_botmode(bot, dest_ref, item, final_html, media)
    except Exception as e:
        msg = str(e)[:200]
        if "admin" in msg.lower() or "CHAT_ADMIN_REQUIRED" in msg or "not enough rights" in msg.lower():
            return False, "دسترسی ادمین در کانال مقصد کافی نیست! ربات/اکانت رو ادمین کن."
        return False, f"خطای انتشار: {msg}"

    await db.set_queue(db_path, item["id"], status="published",
                       scheduled_at=db.now_iso())
    excerpt = (item.get("text_clean") or item.get("text_raw") or "")[:300]
    await db.add_published(db_path, user_id, excerpt)
    await db.bump_stat(db_path, user_id, "posted")
    return True, "منتشر شد ✅"
