"""AI tasks: clean/rewrite posts, translate, dedup, news rewrite, rumor verdict, polls."""
from __future__ import annotations

import json
import re

from . import ai_router
from .lab import PERSONAS, get_lab

ALLOWED_TAGS = "b, i, u, s, code, pre, a, blockquote"


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        # try to fix trailing commas
        fixed = re.sub(r",\s*}", "}", m.group(0))
        try:
            return json.loads(fixed)
        except Exception:
            return {}


def is_mostly_persian(text: str) -> bool:
    fa = len(re.findall(r"[\u0600-\u06FF]", text))
    letters = len(re.findall(r"[A-Za-z\u0600-\u06FF]", text))
    return letters == 0 or (fa / max(letters, 1)) > 0.3


async def clean_post(db_path: str, raw_text: str, has_media: bool, settings: dict,
                     order: list[str] | None = None) -> dict:
    """Returns {action: publish|reject, cleaned_html, reason}."""
    custom_rule = (settings.get("custom_rule") or "").strip()
    topic = (settings.get("channel_topic") or "").strip()
    style = settings.get("content_style", "medium")
    persona_line = PERSONAS.get(get_lab(settings).get("persona") or "none", {}).get("line", "")
    persona_rule = f"8b. {persona_line}" if persona_line else ""
    premium_mode = settings.get("premium_mode", "normal")
    text_filters: list[str] = []
    try:
        text_filters = json.loads(settings.get("text_filters") or "[]")
    except Exception:
        pass
    filter_lines = {"no_harsh": "متن دلخراش/ناراحت‌کننده",
                    "no_profane": "فحش/توهین",
                    "no_political": "سیاست جنجالی"}.items()
    active_filters = [v for k, v in filter_lines if k in text_filters]

    if style == "quantum":
        style_line = ("QUANTUM MODE: compress to the absolute essence — "
                      "one bold headline + max 3 ultra-short bullets. Drop everything else.")
    elif style == "short":
        style_line = "Make it SHORT and punchy (max ~500 chars)."
    else:
        style_line = "Keep it complete and balanced (do not shorten aggressively)."
    emoji_line = {"normal": "Keep normal emojis as-is; drop premium/custom ones.",
                  "premium": "Keep ALL emojis exactly as in the original.",
                  "ai": "Add/replace with fitting STANDARD emojis for the topic."}[premium_mode]

    prompt = f"""You are an expert Persian Telegram channel editor. Clean this post for repost.

ORIGINAL POST (may contain ads, signatures, channel mentions, links):
---
{raw_text[:4000]}
---

Rules:
1. REMOVE: ads, promo lines, source channel signatures/footers, @usernames, t.me links, "join/subscribe" lines, hashtags that are channel branding (keep topical hashtags).
2. KEEP: the real content, facts, numbers, quotes. Preserve meaning 100%.
3. Output language: Persian. If input is not Persian, translate fluently to Persian first.
4. Output format: Telegram HTML using ONLY these tags: {ALLOWED_TAGS}. No markdown.
5. {style_line}
6. Emojis: {emoji_line}
7. Topic of destination channel: {topic or 'general'}. If the post is COMPLETELY unrelated or contradicts it, REJECT.
8. {"Extra custom rule from channel owner (MUST obey): " + custom_rule if custom_rule else "No custom rule."}
{persona_rule}
9. {"Reject if it contains: " + ", ".join(active_filters) if active_filters else "No text filters."}
10. Never invent facts. Never add new claims.

Respond with JSON ONLY, exactly this shape:
{{"action": "publish or reject", "cleaned_html": "HTML here (empty if reject)", "reason": "short Persian reason"}}
"""
    out = await ai_router.chat(db_path, [{"role": "user", "content": prompt}],
                               max_tokens=2500, temperature=0.3, order=order)
    data = _extract_json(out)
    action = data.get("action", "publish")
    if action not in ("publish", "reject"):
        action = "publish"
    cleaned = (data.get("cleaned_html") or "").strip()
    reason = (data.get("reason") or "").strip() or ("تایید شد" if action == "publish" else "رد شد")
    if action == "publish" and not cleaned:
        cleaned = raw_text[:4000]  # fallback: keep original
    return {"action": action, "cleaned_html": cleaned, "reason": reason}


async def is_duplicate(db_path: str, new_text: str, recents: list[str],
                       order: list[str] | None = None) -> tuple[bool, str]:
    if not recents:
        return False, ""
    joined = "\n---\n".join(f"[{i+1}] {t[:300]}" for i, t in enumerate(recents[:12]))
    prompt = f"""Is the NEW post about the SAME news/content as any RECENT post (even with different words)?

RECENT POSTS:
{joined}

NEW POST:
{new_text[:1200]}

Respond JSON only: {{"duplicate": true/false, "reason": "short Persian reason"}}"""
    out = await ai_router.chat(db_path, [{"role": "user", "content": prompt}],
                               max_tokens=200, temperature=0.0, order=order)
    data = _extract_json(out)
    return bool(data.get("duplicate")), str(data.get("reason", ""))


async def rewrite_news(db_path: str, title: str, body: str, url: str, source_name: str,
                       topic: str, style: str = "medium",
                       order: list[str] | None = None) -> dict:
    prompt = f"""You are a Persian news editor. Rewrite this article as a clean, complete Telegram post.

TITLE: {title[:300]}
SOURCE: {source_name}
ARTICLE BODY:
{body[:3500]}

Rules:
- Language: fluent Persian. Keep facts/numbers/quotes accurate, never invent.
- Destination topic: {topic or 'general'} — if completely unrelated, REJECT.
- Telegram HTML only ({ALLOWED_TAGS}). Start with a bold headline.
- Length: {'QUANTUM essence: bold headline + max 3 bullets' if style == 'quantum' else ('short (~500 chars)' if style == 'short' else 'complete but tight')}.
Respond JSON only: {{"action": "publish or reject", "cleaned_html": "HTML", "reason": "short Persian reason"}}"""
    out = await ai_router.chat(db_path, [{"role": "user", "content": prompt}],
                               max_tokens=2500, temperature=0.4, order=order)
    data = _extract_json(out)
    action = data.get("action", "publish")
    if action not in ("publish", "reject"):
        action = "publish"
    return {"action": action, "cleaned_html": (data.get("cleaned_html") or "").strip(),
            "reason": (data.get("reason") or "").strip()}


async def rumor_verdict(db_path: str, claim: str, snippets: str,
                        order: list[str] | None = None) -> dict:
    prompt = f"""You are a fact-checker. Given the CLAIM and live web snippets, judge it.

CLAIM:
{claim[:1000]}

WEB SNIPPETS:
{snippets[:3000]}

Respond JSON only: {{"verdict": "real or fake or uncertain", "reason": "short Persian reason"}}"""
    out = await ai_router.chat(db_path, [{"role": "user", "content": prompt}],
                               max_tokens=300, temperature=0.0, order=order)
    data = _extract_json(out)
    v = data.get("verdict", "uncertain")
    if v not in ("real", "fake", "uncertain"):
        v = "uncertain"
    return {"verdict": v, "reason": str(data.get("reason", ""))}


async def make_poll(db_path: str, post_text: str,
                    order: list[str] | None = None) -> dict:
    prompt = f"""Turn this post into an engaging Telegram poll (Persian).

POST:
{post_text[:1500]}

Respond JSON only: {{"question": "...(max 250 chars)", "options": ["opt1", "opt2", ...]}} (2-6 options, each max 90 chars)"""
    out = await ai_router.chat(db_path, [{"role": "user", "content": prompt}],
                               max_tokens=400, temperature=0.6, order=order)
    data = _extract_json(out)
    q = str(data.get("question", ""))[:250]
    opts = [str(o)[:90] for o in (data.get("options") or [])][:6]
    if not q or len(opts) < 2:
        return {}
    return {"question": q, "options": opts}
