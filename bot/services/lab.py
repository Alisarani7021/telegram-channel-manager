"""Area 51 lab: personas, DNA codec, trend radar, world pulse, idea engine."""
from __future__ import annotations

import json
import re
import zlib

from . import ai_router
from . import news as news_svc
from .. import database as db

LAB_TEXT = """🌌 <b>آزمایشگاه ۵۱</b> 👽

جایی که فیزیک احترام خودش رو از دست میده:
🕳️ <b>فشرده‌ساز کوانتومی</b> — هر پست رو به ذات خالصش فشرده می‌کنه (تیتر + ۳ گلوله)
💀 <b>نویسنده مهمان</b> — حافظ، مولوی، اینشتین یا فردوسی پست‌هات رو بازنویسی می‌کنن
🔮 <b>دزد آینده</b> — داغ‌ترین موضوعات همین حالا رو از دل خبرها می‌دزده
👁️ <b>نبض جهان</b> — کل جهان در ۵ خط، از ترکیب همه منابع خبری
🌪️ <b>باران ایده</b> — موضوع بده، ۱۰ ایده پست بگیر
✨ <b>ماشین ایده‌ساز</b> — هر روز ساعت ۱۲ یه ایده خودکار تو کانالت (هر روز وحشی‌تر!)
♾️ <b>خاطره ابدی</b> — یه خاطره تصادفی از آرشیو کانالت + بازنشر
🧬 <b>DNA کانال</b> — کل کانالت فشرده تو یه رشته ژنتیکی ACGT (بکاپ/انتقال)
🎛️ <b>کنسول خدایی</b> — اسلایدرهای سرنوشت: کنجکاوی، آرامش، لحن
"""

PERSONAS = {
    "none": {"fa": "خاموش", "line": ""},
    "hafez": {"fa": "حافظ 🍷",
              "line": "Voice: rewrite in the lyrical, metaphor-rich voice of Hafez (classical Persian ghazal spirit) while keeping ALL facts intact."},
    "mowlavi": {"fa": "مولوی 🌀",
                "line": "Voice: rewrite in the mystical, ecstatic voice of Rumi/Mowlavi (short wisdom bursts) while keeping ALL facts intact."},
    "einstein": {"fa": "اینشتین 🔬",
                 "line": "Voice: rewrite with Einstein-like clarity — explain simply with one vivid analogy, keep ALL facts intact."},
    "ferdowsi": {"fa": "فردوسی ⚔️",
                 "line": "Voice: rewrite in a heroic epic tone inspired by Ferdowsi's Shahnameh (grand, rhythmic) while keeping ALL facts intact."},
}
PERSONA_ORDER = ["none", "hafez", "mowlavi", "einstein", "ferdowsi"]
DEFAULT_LAB = {"persona": "none", "idea_enabled": 0, "idea_hour": 12, "idea_n": 0}


def get_lab(settings: dict) -> dict:
    lab = dict(DEFAULT_LAB)
    try:
        lab.update(json.loads(settings.get("lab") or "{}"))
    except Exception:
        pass
    if lab.get("persona") not in PERSONAS:
        lab["persona"] = "none"
    return lab


async def set_lab(db_path: str, user_id: int, **fields) -> None:
    s = await db.get_settings(db_path, user_id)
    lab = get_lab(s)
    lab.update(fields)
    await db.set_settings(db_path, user_id, lab=json.dumps(lab, ensure_ascii=False))


# ---------- DNA codec (real quaternary ACGT encoding) ----------
_DNA_FW = {"00": "A", "01": "C", "10": "G", "11": "T"}
_DNA_BW = {v: k for k, v in _DNA_FW.items()}


def dna_encode_dict(data: dict) -> str:
    raw = zlib.compress(json.dumps(data, ensure_ascii=False).encode(), 9)
    bits = "".join(f"{b:08b}" for b in raw)
    return "DNA1:" + "".join(_DNA_FW[bits[i:i + 2]] for i in range(0, len(bits), 2))


def dna_decode_dict(code: str) -> dict:
    code = code.strip().replace(" ", "").replace("\n", "")
    if not code.startswith("DNA1:"):
        raise ValueError("کد DNA معتبر نیست (باید با DNA1: شروع بشه).")
    seq = code[5:].upper()
    if not seq or any(ch not in _DNA_BW for ch in seq) or len(seq) % 4:
        raise ValueError("کد DNA خرابه.")
    bits = "".join(_DNA_BW[ch] for ch in seq)
    raw = int(bits, 2).to_bytes(len(bits) // 8, "big")
    try:
        return json.loads(zlib.decompress(raw).decode())
    except Exception:
        raise ValueError("کد DNA خرابه (باز نشد).")


async def export_dna(db_path: str, user_id: int) -> str:
    s = await db.get_settings(db_path, user_id)
    srcs = await db.list_sources(db_path, user_id)
    dsts = await db.list_dests(db_path, user_id)
    data = {"v": 1,
            "src": [{"c": x["channel"], "t": (x.get("title") or "")[:100]} for x in srcs],
            "dst": [{"c": x["channel"], "t": (x.get("title") or "")[:100]} for x in dsts],
            "s": {"interval": s["send_interval_min"], "ws": s["work_start"],
                  "we": s["work_end"], "style": s["content_style"],
                  "topic": (s.get("channel_topic") or "")[:100],
                  "rule": (s.get("custom_rule") or "")[:250]}}
    code = dna_encode_dict(data)
    if len(code) > 3500:
        raise ValueError("DNA کانالت خیلی بزرگه (بالای ۳۵۰۰ حرف)!")
    return code


async def import_dna(db_path: str, user_id: int, code: str,
                     max_src: int, max_dst: int) -> tuple[int, int]:
    data = dna_decode_dict(code)
    if not isinstance(data, dict) or data.get("v") != 1:
        raise ValueError("این DNA مال یه موجود دیگه‌ست! 🛸")
    added_src = added_dst = 0
    have_src = {x["channel"] for x in await db.list_sources(db_path, user_id)}
    for it in (data.get("src") or [])[:max(0, max_src)]:
        ch = str((it or {}).get("c") or "").strip()
        if ch and ch not in have_src and len(have_src) < max_src:
            await db.add_source(db_path, user_id, ch, str(it.get("t") or "")[:100])
            have_src.add(ch)
            added_src += 1
    have_dst = {x["channel"] for x in await db.list_dests(db_path, user_id)}
    for it in (data.get("dst") or [])[:max(0, max_dst)]:
        ch = str((it or {}).get("c") or "").strip()
        if ch and ch not in have_dst and len(have_dst) < max_dst:
            await db.add_dest(db_path, user_id, ch, str(it.get("t") or "")[:100])
            have_dst.add(ch)
            added_dst += 1
    s = data.get("s") or {}
    fields: dict = {}
    try:
        iv = int(s.get("interval", 0))
        if 5 <= iv <= 1440:
            fields["send_interval_min"] = iv
        ws, we = int(s.get("ws", -1)), int(s.get("we", -1))
        if 0 <= ws < 24 and 0 < we <= 24 and ws < we:
            fields["work_start"], fields["work_end"] = ws, we
    except (ValueError, TypeError):
        pass
    if s.get("style") in ("short", "medium", "quantum"):
        fields["content_style"] = s["style"]
    if isinstance(s.get("topic"), str):
        fields["channel_topic"] = s["topic"][:100]
    if isinstance(s.get("rule"), str):
        fields["custom_rule"] = s["rule"][:250]
    if fields:
        await db.set_settings(db_path, user_id, **fields)
    return added_src, added_dst


# ---------- trend radar (steal the future) ----------
_FA_STOP = frozenset("از به در با که و یا را این آن های برای بر روی هم نیز شد شده است بود کند کرد می شود شوند بین چون اگر اما ولی تا هر چه نه بیش پس طی علیه درباره خیلی یک دو سه".split())


def top_words(titles: list[str], n: int = 7) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for t in titles:
        for w in re.findall(r"[\u0600-\u06FF]{3,}", t):
            if w in _FA_STOP:
                continue
            counts[w] = counts.get(w, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n]


async def trend_radar() -> str:
    try:
        cands = await news_svc.fetch_candidates(news_svc.default_sources(), per_source=5)
    except Exception:
        cands = []
    titles = [c.get("title", "") for c in cands if c.get("title")]
    if not titles:
        return "🔮 نتونستم به خبرها وصل بشم؛ بعداً دوباره تلاش کن."
    tops = top_words(titles)
    if not tops:
        return "🔮 چیزی پیدا نکردم؛ بعداً دوباره تلاش کن."
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣"]
    lines = ["🔮 <b>دزد آینده</b>\n\n📈 داغ‌ترین موضوعات همین حالا (از دل خبرها):\n"]
    for i, (w, c) in enumerate(tops):
        lines.append(f"{medals[i]} {w} <i>×{c}</i>")
    lines.append("\n<i>این‌ها رو الان پوشش بده، قبل از اینکه همه بفهمن 😉</i>")
    return "\n".join(lines)


# ---------- world pulse / idea rain / idea machine ----------
async def world_pulse(db_path: str, order: list[str] | None) -> str:
    cands = await news_svc.fetch_candidates(news_svc.default_sources(), per_source=2)
    titles = [f"• [{c['source']}] {c['title']}" for c in cands if c.get("title")][:14]
    if not titles:
        raise RuntimeError("نتونستم خبرها رو بخونم.")
    prompt = ("تو «چشم سوم» یک کانال تلگرامی هستی. از تیترهای زیر «نبض جهان در ۵ خط» بساز: "
              "مهم‌ترین‌ها، بدون حاشیه، فارسی روان، با اموجی مناسب، فرمت HTML تلگرام (فقط b i code).\n\n"
              + "\n".join(titles))
    out = await ai_router.chat(db_path, [{"role": "user", "content": prompt}],
                               max_tokens=700, temperature=0.5, order=order)
    return "👁️ <b>نبض جهان</b>\n\n" + out.strip()


async def idea_rain(db_path: str, topic: str, order: list[str] | None) -> str:
    prompt = (f"برای یه کانال تلگرامی با موضوع «{topic[:80]}»، دقیقاً ۱۰ ایده پست کوتاه، جذاب و متنوع بده "
              "(شماره‌دار ۱ تا ۱۰، هر ایده یه خط، فارسی). فقط لیست، بدون مقدمه. فرمت HTML ساده تلگرام.")
    out = await ai_router.chat(db_path, [{"role": "user", "content": prompt}],
                               max_tokens=1200, temperature=0.9, order=order)
    return f"🌪️ <b>باران ایده: {topic[:60]}</b>\n\n{out.strip()}"


async def daily_idea(db_path: str, user_id: int, order: list[str] | None) -> str:
    s = await db.get_settings(db_path, user_id)
    lab = get_lab(s)
    n = int(lab.get("idea_n") or 0) + 1
    temp = min(0.7 + n * 0.05, 1.3)
    topic = (s.get("channel_topic") or "عمومی").strip() or "عمومی"
    prompt = (f"تو «ماشین ایده‌ساز» هستی (روز {n}). برای کانالی با موضوع «{topic[:60]}» یه ایده/پست خلاقانه و قابل انتشار بنویس — "
              "هر روز باید جسورانه‌تر و غیرمنتظره‌تر از دیروز باشه ولی هنوز بامزه و خواندنی. "
              "فارسی روان، HTML تلگرام (b i code)، حداکثر ~۶۰۰ کاراکتر، با یه تیتر بولد.")
    out = await ai_router.chat(db_path, [{"role": "user", "content": prompt}],
                               max_tokens=800, temperature=temp, order=order)
    await set_lab(db_path, user_id, idea_n=n)
    return f"✨ <b>ایده روز #{n} (از ماشین ایده‌ساز)</b>\n\n{out.strip()}"
