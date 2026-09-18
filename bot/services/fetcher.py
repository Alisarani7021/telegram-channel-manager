"""Telethon manager: shared parser client (bot mode) + per-user clients (personal mode)."""
from __future__ import annotations

import asyncio
import re
import time

from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest

from .. import database as db


def normalize_ref(ref: str) -> str:
    ref = ref.strip()
    m = re.search(r"t\.me/(?:\+|joinchat/)?([A-Za-z0-9_+-]+)", ref)
    if m and "joinchat" not in ref and "/+" not in ref:
        return "@" + m.group(1)
    return ref


_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_login_code(raw: str) -> str:
    """Normalize a login code: Persian/Arabic digits -> ASCII, drop spaces etc."""
    return "".join(ch for ch in raw.translate(_FA_DIGITS) if ch.isdigit())


class TManager:
    def __init__(self, api_id: int, api_hash: str, db_path: str, parser_session: str = ""):
        self.api_id = api_id
        self.api_hash = api_hash
        self.db_path = db_path
        self.parser_session_str = parser_session
        self.parser: TelegramClient | None = None
        self.users: dict[int, TelegramClient] = {}
        self.login_state: dict[int, dict] = {}  # user_id -> {client, phone, hash, ts, rid}
        self._rid = 0

    # ---------- startup ----------
    async def start(self) -> None:
        # shared parser for public channels (bot mode)
        try:
            if self.parser_session_str:
                self.parser = TelegramClient(StringSession(self.parser_session_str),
                                             self.api_id, self.api_hash)
            else:
                self.parser = TelegramClient("data/parser", self.api_id, self.api_hash)
            await self.parser.connect()
        except Exception:
            self.parser = None
        # reconnect personal sessions
        for u in await db.all_users(self.db_path):
            sess = (u.get("session") or "").strip()
            if u.get("mode") == "personal" and sess:
                try:
                    cli = TelegramClient(StringSession(sess), self.api_id, self.api_hash)
                    await cli.connect()
                    if await cli.is_user_authorized():
                        self.users[u["user_id"]] = cli
                    else:
                        await db.set_user(self.db_path, u["user_id"], session="", mode="bot")
                except Exception:
                    continue

    async def parser_ready(self) -> bool:
        return bool(self.parser and self.parser.is_connected())

    async def ensure_user(self, user_id: int) -> TelegramClient | None:
        cli = self.users.get(user_id)
        if cli and cli.is_connected():
            return cli
        u = await db.get_user(self.db_path, user_id)
        sess = (u.get("session") or "") if u else ""
        if not sess:
            return None
        try:
            cli = TelegramClient(StringSession(sess), self.api_id, self.api_hash)
            await cli.connect()
            if await cli.is_user_authorized():
                self.users[user_id] = cli
                return cli
        except Exception:
            pass
        return None

    def client_for(self, user_id: int, mode: str) -> TelegramClient | None:
        if mode == "personal":
            return self.users.get(user_id)
        return self.parser

    # ---------- personal login flow ----------
    async def send_code(self, user_id: int, phone: str) -> str:
        # don't burn the previous code with an accidental double request
        cur = self.login_state.get(user_id)
        if cur and cur.get("phone") == phone.strip() and time.time() - cur.get("ts", 0) < 90:
            return "already_sent"
        old = self.login_state.pop(user_id, None)
        if old:
            try:
                await old["client"].disconnect()
            except Exception:
                pass
        cli = TelegramClient(StringSession(), self.api_id, self.api_hash)
        await cli.connect()
        try:
            sent = await cli.send_code_request(phone.strip())
        except errors.PhoneNumberInvalidError:
            return "شماره نامعتبره! با فرمت بین‌المللی بفرست (مثل +33612345678)."
        except errors.FloodWaitError as e:
            return f"تلگرام محدودت کرده، {e.seconds} ثانیه بعد دوباره تلاش کن."
        except Exception as e:
            return f"خطا: {e}"
        self._rid += 1
        self.login_state[user_id] = {"client": cli, "phone": phone.strip(),
                                     "hash": sent.phone_code_hash, "ts": time.time(),
                                     "rid": self._rid}
        return "ok"

    async def submit_code(self, user_id: int, code: str) -> str:
        st = self.login_state.get(user_id)
        if not st:
            return "اول شماره رو بفرست."
        cli, phone, h = st["client"], st["phone"], st["hash"]
        code = normalize_login_code(code)
        if not code:
            return "کد رو پیدا نکردم! همون عددی که تلگرام فرستاد رو بفرست."
        try:
            await cli.sign_in(phone=phone, code=code, phone_code_hash=h)
        except errors.SessionPasswordNeededError:
            return "2fa"
        except errors.PhoneCodeInvalidError:
            return "کد اشتباهه! دقیقاً همون ۵ رقمی که تلگرام فرستاد رو بفرست."
        except errors.PhoneCodeExpiredError:
            return ("⏰ تلگرام این کد را باطل کرد!\n"
                    "علت: اگر کد را مستقیم در چت تایپ کنی، سیستم ضد فیشینگ تلگرام فوراً آن را می‌سوزاند (پیام تلگرام: «کد قبلاً توسط حسابتان به اشتراک گذاشته شده بود»).\n"
                    "👉 لطفاً دکمه «🔄 ارسال مجدد کد» را بزن و این بار با دکمه‌های ماشین‌حسابی بالا وارد کن یا بین ارقام خط تیره بگذار (مثلاً ۵-۲-۹-۷-۵).")
        except errors.FloodWaitError as e:
            return f"تلگرام محدودت کرده، {e.seconds} ثانیه بعد دوباره تلاش کن."
        except Exception as e:
            return f"خطا: {e}"
        await self._save_session(user_id, cli)
        return "ok"

    def login_rid(self, user_id: int) -> int:
        st = self.login_state.get(user_id)
        return int(st.get("rid", 0)) if st else 0

    async def resend_code(self, user_id: int) -> str:
        st = self.login_state.get(user_id)
        if not st:
            return "expired"
        # throttle: mashing resend burns the code the user is about to enter
        age = time.time() - st.get("ts", 0)
        if age < 60:
            return f"fast:{int(60 - age)}"
        cli = st["client"]
        try:
            if not cli.is_connected():
                await cli.connect()
            sent = await cli.send_code_request(st["phone"])
        except errors.FloodWaitError as e:
            return f"wait:{e.seconds}"
        except Exception as e:
            return f"err:{e}"
        st["hash"] = sent.phone_code_hash
        st["ts"] = time.time()
        self._rid += 1
        st["rid"] = self._rid
        return "ok"

    async def submit_2fa(self, user_id: int, password: str) -> str:
        st = self.login_state.get(user_id)
        if not st:
            return "اول شماره رو بفرست."
        try:
            await st["client"].sign_in(password=password)
        except errors.PasswordHashInvalidError:
            return "رمز دومرحله‌ای اشتباهه!"
        except Exception as e:
            return f"خطا: {e}"
        await self._save_session(user_id, st["client"])
        return "ok"

    async def _save_session(self, user_id: int, cli: TelegramClient) -> None:
        sess = cli.session.save()
        self.users[user_id] = cli
        self.login_state.pop(user_id, None)
        await db.set_user(self.db_path, user_id, session=sess, mode="personal")
        # clear old channels on mode switch (like the original bot)
        async with __import__("aiosqlite").connect(self.db_path) as d:
            await d.execute("DELETE FROM sources WHERE user_id=?", (user_id,))
            await d.execute("DELETE FROM dests WHERE user_id=?", (user_id,))
            await d.commit()

    async def logout(self, user_id: int) -> None:
        cli = self.users.pop(user_id, None)
        if cli:
            try:
                await cli.log_out()
            except Exception:
                try:
                    await cli.disconnect()
                except Exception:
                    pass
        await db.set_user(self.db_path, user_id, session="", phone="", mode="bot")

    # ---------- channels ----------
    async def resolve(self, cli: TelegramClient, ref: str):
        ref = normalize_ref(ref)
        try:
            ent = await cli.get_entity(ref)
            title = getattr(ent, "title", None) or getattr(ent, "username", None) or ref
            return ent, title, "ok"
        except (ValueError, errors.UsernameInvalidError):
            return None, "", "پیدا نشد! آیدی/لینک رو چک کن."
        except errors.UsernameNotOccupiedError:
            return None, "", "این یوزرنیم وجود نداره."
        except errors.ChannelPrivateError:
            return None, "", "کانال خصوصیه و عضو نیستی."
        except errors.InviteHashExpiredError:
            return None, "", "لینک دعوت منقضی شده."
        except errors.FloodWaitError as e:
            return None, "", f"محدودیت تلگرام: {e.seconds} ثانیه صبر کن."
        except Exception as e:
            return None, "", f"خطا: {str(e)[:150]}"

    async def join_if_needed(self, cli: TelegramClient, ref: str) -> None:
        ref = ref.strip()
        try:
            if "joinchat/" in ref or "/+" in ref:
                h = ref.split("joinchat/")[-1].split("/+")[-1].split("?")[0]
                await cli(ImportChatInviteRequest(h))
            elif ref.startswith("@") or "t.me/" in ref:
                try:
                    await cli(JoinChannelRequest(normalize_ref(ref)))
                except errors.UserAlreadyParticipantError:
                    pass
        except errors.UserAlreadyParticipantError:
            pass
        except Exception:
            pass  # join is best-effort; reading may still work

    async def get_input_entity(self, cli: TelegramClient, ref: str):
        """Resolve entity with a dialogs-cache refresh fallback (numeric ids)."""
        ref = ref.strip()
        arg = int(ref) if ref.lstrip("-").isdigit() else normalize_ref(ref)
        try:
            return await cli.get_entity(arg)
        except Exception:
            try:
                await cli.get_dialogs(limit=100)  # refresh entity cache
                return await cli.get_entity(arg)
            except Exception:
                raise

    async def resolve_and_join(self, cli: TelegramClient, ref: str):
        """Resolve + join any channel ref. Returns (entity, title, store_ref, status)."""
        ref = ref.strip()
        if "joinchat/" in ref or "/+" in ref:
            h = ref.split("joinchat/")[-1].split("/+")[-1].split("?")[0].strip()
            try:
                upd = await cli(ImportChatInviteRequest(h))
                chats = getattr(upd, "chats", []) or []
                if chats:
                    ent = chats[0]
                    title = getattr(ent, "title", "") or "کانال خصوصی"
                    return ent, title, str(ent.id), "ok"
            except errors.UserAlreadyParticipantError:
                pass
            except errors.InviteHashExpiredError:
                return None, "", "", "لینک دعوت منقضی شده."
            except errors.InviteHashEmptyError:
                return None, "", "", "لینک دعوت ناقصه."
            except errors.FloodWaitError as e:
                return None, "", "", f"محدودیت تلگرام: {e.seconds} ثانیه صبر کن."
            except Exception as e:
                return None, "", "", f"خطا: {str(e)[:150]}"
            # Already a member: ask for numeric id / username instead.
            return (None, "", "",
                    "تو این کانال عضوی ولی با لینک دعوت نتونستم پیداش کنم. "
                    "آیدی عددی کانال (مثل 1234567890-) یا یوزرنیمش (اگه داره) رو بفرست. "
                    "آیدی عددی رو می‌تونی با فوروارد یه پست کانال به @userinfobot پیدا کنی.")
        ent, title, status = await self.resolve(cli, ref)
        if not ent:
            return None, "", "", status
        await self.join_if_needed(cli, ref)
        return ent, title, normalize_ref(ref), "ok"

    async def fetch_new(self, cli: TelegramClient, channel_ref: str, last_id: int,
                        limit: int = 10) -> tuple[list[dict], int]:
        """Returns (groups, new_last_id). Each group = {ids:[...], msgs:[...]} (album-aware)."""
        ent = await self.get_input_entity(cli, channel_ref)
        msgs = await cli.get_messages(ent, min_id=last_id, limit=limit)
        if not msgs:
            return [], last_id
        msgs = sorted(msgs, key=lambda m: m.id)
        new_last = max(m.id for m in msgs)
        groups: dict[str, dict] = {}
        order: list[str] = []
        for m in msgs:
            if getattr(m, "grouped_id", None):
                key = f"g{m.grouped_id}"
            else:
                key = f"s{m.id}"
            if key not in groups:
                groups[key] = {"ids": [], "msgs": []}
                order.append(key)
            groups[key]["ids"].append(m.id)
            groups[key]["msgs"].append(m)
        return [groups[k] for k in order], new_last

    @staticmethod
    def classify(msgs: list) -> tuple[str, str]:
        """(media_type, text)."""
        first = msgs[0]
        text = first.message or first.text or ""
        if len(msgs) > 1:
            return "album", text
        m = first
        if m.voice:
            return "voice", text
        if m.video_note:
            return "video_note", text
        if m.gif:
            return "gif", text
        if m.photo:
            return "photo", text
        if m.video:
            return "video", text
        if m.document:
            return "other", text
        if text:
            return ("text_short", text) if len(text) < 400 else ("text_long", text)
        if m.poll:
            return "other", text
        return "other", text

    async def download_group(self, cli: TelegramClient, msgs: list) -> list[dict]:
        out = []
        for m in msgs:
            if not m.media:
                continue
            try:
                data = await cli.download_media(m, file=bytes)
                if not data:
                    continue
                mime = "image/jpeg"
                name = "file.bin"
                if m.photo:
                    mime, name = "image/jpeg", "photo.jpg"
                elif m.document:
                    mime = m.document.mime_type or "application/octet-stream"
                    for a in m.document.attributes:
                        if hasattr(a, "file_name") and a.file_name:
                            name = a.file_name
                            break
                    else:
                        ext = {"video/mp4": "mp4", "image/gif": "gif",
                               "audio/ogg": "ogg", "audio/mpeg": "mp3"}.get(mime, "bin")
                        name = f"file.{ext}"
                out.append({"bytes": bytes(data), "mime": mime, "name": name})
            except Exception:
                continue
        return out
