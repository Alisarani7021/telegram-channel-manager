"""Inline keyboard builders."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .texts import HELP_TOPICS, ONBOARDING


def main_menu() -> InlineKeyboardMarkup:
    # NOTE: no admin entry here on purpose — admin panel is hidden, entry via /admin
    rows = [
        [InlineKeyboardButton("🔗 اتصال و کانال‌ها", callback_data="m:conn")],
        [InlineKeyboardButton("🎛️ کنترل پنل", callback_data="m:panel")],
        [InlineKeyboardButton("🎨 استایل و فیلتر محتوا", callback_data="m:style"),
         InlineKeyboardButton("🕐 تنظیمات انتشار", callback_data="m:pub")],
        [InlineKeyboardButton("🌍 محتوای خودکار", callback_data="m:auto"),
         InlineKeyboardButton("📊 محدودیت و آمار", callback_data="m:stats")],
        [InlineKeyboardButton("🔑 کلیدهای AI", callback_data="m:keys"),
         InlineKeyboardButton("🔔 اعلان‌ها", callback_data="m:annc")],
        [InlineKeyboardButton("🌌 آزمایشگاه ۵۱", callback_data="m:lab")],
        [InlineKeyboardButton("❓ بلد نیستم چیکار کنم؟", callback_data="ob:0")],
    ]
    return InlineKeyboardMarkup(rows)


def back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ بازگشت", callback_data="m:menu")]])


# ---- help carousel ----
def help_nav(idx: int) -> InlineKeyboardMarkup:
    n = len(HELP_TOPICS)
    row = []
    if idx > 0:
        row.append(InlineKeyboardButton("➡️ قبلی", callback_data=f"h:{idx-1}"))
    if idx < n - 1:
        row.append(InlineKeyboardButton("⬅️ بعدی", callback_data=f"h:{idx+1}"))
    return InlineKeyboardMarkup([
        row or [InlineKeyboardButton("—", callback_data="noop")],
        [InlineKeyboardButton("📚 لیست موضوعات", callback_data="hl")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="m:menu")],
    ])


def help_list() -> InlineKeyboardMarkup:
    rows = []
    for i, (_, title, _) in enumerate(HELP_TOPICS):
        rows.append([InlineKeyboardButton(title, callback_data=f"h:{i}")])
    rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="m:menu")])
    return InlineKeyboardMarkup(rows)


def onboarding_nav(idx: int) -> InlineKeyboardMarkup:
    n = len(ONBOARDING)
    row = []
    if idx > 0:
        row.append(InlineKeyboardButton("➡️ قبلی", callback_data=f"ob:{idx-1}"))
    if idx < n - 1:
        row.append(InlineKeyboardButton("⬅️ بعدی", callback_data=f"ob:{idx+1}"))
    kb = [row] if row else []
    kb.append([InlineKeyboardButton("⬅️ بازگشت به مدیریت", callback_data="m:menu")])
    return InlineKeyboardMarkup(kb)


# ---- connection ----
def conn_menu(mode: str, connected: bool) -> InlineKeyboardMarkup:
    rows = []
    if mode == "bot":
        rows.append([InlineKeyboardButton("🔗 وصل کردن اکانت شخصی", callback_data="cn:login")])
    else:
        rows.append([InlineKeyboardButton("🔀 برگشت به حالت ربات", callback_data="cn:tobot")])
        rows.append([InlineKeyboardButton("🚪 خروج از اکانت شخصی", callback_data="cn:logout")])
    rows += [
        [InlineKeyboardButton("🎯 کانال مقصد", callback_data="cn:dest"),
         InlineKeyboardButton("📡 کانال‌های مبدا", callback_data="cn:src")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="m:menu")],
    ]
    return InlineKeyboardMarkup(rows)


def channel_list(items: list[dict], kind: str) -> InlineKeyboardMarkup:
    rows = []
    for it in items:
        title = it.get("title") or it.get("channel")
        rows.append([InlineKeyboardButton(f"❌ {title}", callback_data=f"chdel:{kind}:{it['id']}")])
    rows.append([InlineKeyboardButton("➕ افزودن", callback_data=f"chadd:{kind}")])
    rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="m:conn")])
    return InlineKeyboardMarkup(rows)


# ---- review ----
def review_kb(qid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ تایید", callback_data=f"rv:ok:{qid}"),
        InlineKeyboardButton("⏩ ارسال فوری", callback_data=f"rv:now:{qid}"),
        InlineKeyboardButton("❌ رد", callback_data=f"rv:no:{qid}"),
    ],
        [InlineKeyboardButton("⏭️ بعداً تصمیم می‌گیرم", callback_data=f"rv:later:{qid}")],
    ])


# ---- publish settings ----
def pub_menu(s: dict, publish_mode: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⏱️ فاصله ارسال: {s['send_interval_min']} دقیقه", callback_data="edit:interval")],
        [InlineKeyboardButton(f"📅 ساعت کاری: {s['work_start']}:00 تا {s['work_end']}:00", callback_data="edit:workhours")],
        [InlineKeyboardButton(f"📝 نوع محتوا: {'کوتاه ⚡' if s['content_style']=='short' else ('کوانتومی 🕳️' if s['content_style']=='quantum' else 'متعادل 📝')}", callback_data="st:style")],
        [InlineKeyboardButton(f"🔀 مدل انتشار: {'🔍 بررسی' if publish_mode=='review' else '⚡ آنی'}", callback_data="st:pubmode")],
        [InlineKeyboardButton("🗑️ ریست زمان‌بندی (خالی‌کردن صف)", callback_data="st:clearq")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="m:menu")],
    ])


# ---- style settings ----
def style_menu(s: dict) -> InlineKeyboardMarkup:
    sig = {"none": "بدون امضا", "text": "متن ساده", "link": "لینک زیرخط‌دار"}[s["signature_mode"]]
    prem = {"normal": "عادی", "premium": "پرمیوم", "ai": "انتخاب AI"}[s["premium_mode"]]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📋 امضای زیر پست: {sig}", callback_data="st:sig")],
        [InlineKeyboardButton(f"💡 اموجی پرمیوم: {prem}", callback_data="st:prem")],
        [InlineKeyboardButton(f"🌐 ترجمه خودکار: {'✅' if s['translate_enabled'] else '❌'}", callback_data="st:tr")],
        [InlineKeyboardButton(f"🌀 تشخیص تکراری: {'✅' if s['dedup_enabled'] else '❌'}", callback_data="st:dd")],
        [InlineKeyboardButton(f"🕵️ بررسی شایعه: {'✅' if s['rumor_enabled'] else '❌'}", callback_data="st:rumor")],
        [InlineKeyboardButton("📜 قانون سفارشی AI", callback_data="edit:rule")],
        [InlineKeyboardButton("📍 موضوع کانال", callback_data="edit:topic")],
        [InlineKeyboardButton("🚦 فیلتر نوع محتوا", callback_data="st:types")],
        [InlineKeyboardButton("⛔ فیلتر محتوای متنی", callback_data="st:texts")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="m:menu")],
    ])


def cycle_sig() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("بدون امضا", callback_data="sig:none")],
        [InlineKeyboardButton("متن ساده", callback_data="sig:text")],
        [InlineKeyboardButton("لینک زیرخط‌دار", callback_data="sig:link")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="m:style")],
    ])


def cycle_prem() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("عادی", callback_data="prem:normal")],
        [InlineKeyboardButton("پرمیوم", callback_data="prem:premium")],
        [InlineKeyboardButton("انتخاب AI", callback_data="prem:ai")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="m:style")],
    ])


# ---- auto content ----
def auto_menu(price: dict, news: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💲 قیمت دلار/طلا: {'✅' if price['enabled'] else '❌'} (ساعت {price['hour']})", callback_data="au:price")],
        [InlineKeyboardButton(f"🌍 اخبار خودکار: {'✅' if news['enabled'] else '❌'}", callback_data="au:news")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="m:menu")],
    ])


def auto_price_sub(price: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ روشن" if not price["enabled"] else "❌ خاموش", callback_data="au:price_t")],
        [InlineKeyboardButton(f"🕘 تغییر ساعت (فعلی: {price['hour']})", callback_data="edit:pricehour")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="m:auto")],
    ])


def auto_news_sub(news: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ روشن" if not news["enabled"] else "❌ خاموش", callback_data="au:news_t")],
        [InlineKeyboardButton("🎯 موضوع", callback_data="edit:newstopic")],
        [InlineKeyboardButton(f"🔢 تعداد هر دوره: {news['per_cycle']}", callback_data="edit:newscount")],
        [InlineKeyboardButton("📰 منابع خبری", callback_data="au:newssrc")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="m:auto")],
    ])


# ---- panel ----
def panel_menu(paused: bool, survey: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ ازسرگیری پردازش" if paused else "⏸️ توقف پردازش", callback_data="pn:pause")],
        [InlineKeyboardButton(f"📊 مود نظرسنجی: {'✅' if survey else '❌'}", callback_data="pn:survey")],
        [InlineKeyboardButton("🧹 پاکسازی خودکار پی‌وی: تنظیم", callback_data="pn:clean")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="m:menu")],
    ])


# ---- AI keys ----
def keys_menu(n_active: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎁 اهدای کلید", callback_data="key:donate")],
        [InlineKeyboardButton(f"🗝️ کلیدهای من", callback_data="key:mine")],
        [InlineKeyboardButton(f"📊 وضعیت استخر ({n_active} فعال)", callback_data="key:pool")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="m:menu")],
    ])


def provider_pick() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Groq (رایگان)", callback_data="dk:groq"),
         InlineKeyboardButton("✨ Gemini (رایگان)", callback_data="dk:gemini")],
        [InlineKeyboardButton("🌐 OpenRouter (رایگان)", callback_data="dk:openrouter"),
         InlineKeyboardButton("🟧 Mistral", callback_data="dk:mistral")],
        [InlineKeyboardButton("🔷 DeepSeek", callback_data="dk:deepseek"),
         InlineKeyboardButton("⬛ OpenAI", callback_data="dk:openai")],
        [InlineKeyboardButton("🟣 MiniMax", callback_data="dk:minimax")],
        [InlineKeyboardButton("🛠️ آدرس دلخواه (OpenAI-Compatible)", callback_data="dk:custom")],
        [InlineKeyboardButton("❌ انصراف", callback_data="conv:cancel")],
    ])


def login_code_kb(rid: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 ارسال مجدد کد", callback_data=f"login:resend:{rid}")],
        [InlineKeyboardButton("❌ انصراف", callback_data="conv:cancel")],
    ])


def cancel_conv() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="conv:cancel")]])


# ---- admin ----
def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📣 ارسال اعلان", callback_data="ad:annc")],
        [InlineKeyboardButton("🗝️ مدیریت استخر کلیدها", callback_data="key:pool")],
        [InlineKeyboardButton("📈 آمار کلی", callback_data="ad:stats")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="m:menu")],
    ])


# ---- area 51 lab ----
def lab_menu(style: str, persona_fa: str, idea_on: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🕳️ فشرده‌ساز کوانتومی: {'✅' if style == 'quantum' else '❌'}",
                              callback_data="lab:quantum")],
        [InlineKeyboardButton(f"💀 نویسنده مهمان: {persona_fa}", callback_data="lab:persona")],
        [InlineKeyboardButton("🔮 دزد آینده", callback_data="lab:trend"),
         InlineKeyboardButton("👁️ نبض جهان", callback_data="lab:pulse")],
        [InlineKeyboardButton("🌪️ باران ایده", callback_data="lab:rain"),
         InlineKeyboardButton(f"✨ ماشین ایده‌ساز: {'✅' if idea_on else '❌'}",
                              callback_data="lab:idea")],
        [InlineKeyboardButton("♾️ خاطره ابدی", callback_data="lab:memory")],
        [InlineKeyboardButton("🧬 استخراج DNA", callback_data="lab:dnaout"),
         InlineKeyboardButton("🧬 تزریق DNA", callback_data="lab:dnain")],
        [InlineKeyboardButton("🎛️ کنسول خدایی", callback_data="lab:god")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="m:menu")],
    ])


def god_menu(style: str, per_cycle: int, interval: int) -> InlineKeyboardMarkup:
    tones = {"short": "کوتاه ⚡", "medium": "متعادل 📝", "quantum": "کوانتومی 🕳️"}
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔥 کنجکاوی (خبر در هر دوره): {per_cycle}",
                              callback_data="lab:godcur")],
        [InlineKeyboardButton(f"😴 آرامش (فاصله ارسال): هر {interval} دقیقه",
                              callback_data="lab:godcalm")],
        [InlineKeyboardButton(f"🎭 لحن کانال: {tones.get(style, style)}",
                              callback_data="lab:godtone")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="m:lab")],
    ])


def back_to_lab() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ بازگشت به آزمایشگاه",
                                                       callback_data="m:lab")]])


def mem_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 بازنشر در کانال", callback_data="lab:resend")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="m:lab")],
    ])
