"""AI Router: a pool of (mostly free) keys with round-robin + fallback.

Providers:
  - groq        OpenAI-compatible  https://api.groq.com/openai/v1
  - openrouter  OpenAI-compatible  https://openrouter.ai/api/v1  (use :free models)
  - deepseek    OpenAI-compatible  https://api.deepseek.com/v1
  - openai      OpenAI-compatible  https://api.openai.com/v1
  - custom      any OpenAI-compatible base URL
  - gemini      native Google API

Users can donate keys: we TEST the key first, then add it to the pool.
"""
from __future__ import annotations

import time

import httpx

from .. import database as db

PROVIDERS: dict[str, dict] = {
    "groq": {
        "label": "Groq",
        "kind": "openai",
        "base": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "key_url": "https://console.groq.com/keys",
        "hint": "از console.groq.com رایگان بگیر (ثبت‌نام با گوگل، بدون کارت).",
    },
    "gemini": {
        "label": "Gemini",
        "kind": "gemini",
        "base": "https://generativelanguage.googleapis.com",
        "model": "gemini-2.0-flash",
        "key_url": "https://aistudio.google.com/apikey",
        "hint": "از aistudio.google.com رایگان بگیر (Get API Key).",
    },
    "openrouter": {
        "label": "OpenRouter",
        "kind": "openai",
        "base": "https://openrouter.ai/api/v1",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "key_url": "https://openrouter.ai/keys",
        "hint": "از openrouter.ai رایگان بگیر؛ مدل باید آخرش :free داشته باشه.",
    },
    "deepseek": {
        "label": "DeepSeek",
        "kind": "openai",
        "base": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "key_url": "https://platform.deepseek.com/api_keys",
        "hint": "از platform.deepseek.com بگیر (ارزون، گاهی کردیت اولیه رایگان).",
    },
    "openai": {
        "label": "OpenAI",
        "kind": "openai",
        "base": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "key_url": "https://platform.openai.com/api-keys",
        "hint": "از platform.openai.com (پولی).",
    },
    "custom": {
        "label": "آدرس دلخواه",
        "kind": "openai",
        "base": "",
        "model": "",
        "key_url": "",
        "hint": "هر سرویسی که با فرمت OpenAI سازگاره (آدرس + کلید + مدل).",
    },
}


async def import_env_keys(db_path: str, groq: list[str], gemini: list[str],
                          openrouter: list[str]) -> int:
    """Seed keys from .env on startup (only new ones)."""
    added = 0
    seeds = [("groq", groq), ("gemini", gemini), ("openrouter", openrouter)]
    for provider, keys in seeds:
        info = PROVIDERS[provider]
        for k in keys:
            k = k.strip()
            if not k or await db.key_exists(db_path, k):
                continue
            await db.add_ai_key(db_path, provider, info["base"], k, info["model"],
                                added_by=0, note="env")
            added += 1
    return added


# ---------- low-level callers ----------
async def _call_openai(base: str, key: str, model: str, messages: list[dict],
                       max_tokens: int, temperature: float, timeout: int) -> str:
    url = base.rstrip("/") + "/chat/completions"
    async with httpx.AsyncClient(timeout=timeout) as cli:
        r = await cli.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                     "HTTP-Referer": "https://localhost", "X-Title": "tcm-free"},
            json={"model": model, "messages": messages,
                  "max_tokens": max_tokens, "temperature": temperature},
        )
        if r.status_code in (401, 403):
            raise PermissionError(f"auth:{r.status_code} {r.text[:200]}")
        if r.status_code == 429:
            raise RuntimeError(f"rate:{r.status_code} {r.text[:200]}")
        if r.status_code >= 400:
            raise RuntimeError(f"http:{r.status_code} {r.text[:200]}")
        data = r.json()
        return data["choices"][0]["message"]["content"] or ""


async def _call_gemini(key: str, model: str, messages: list[dict],
                       max_tokens: int, temperature: float, timeout: int) -> str:
    # flatten messages into one prompt (simple + reliable for free tier)
    prompt = "\n\n".join(f"{m.get('role','user')}: {m.get('content','')}" for m in messages)
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
           f":generateContent?key={key}")
    async with httpx.AsyncClient(timeout=timeout) as cli:
        r = await cli.post(
            url, headers={"Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"maxOutputTokens": max_tokens,
                                       "temperature": temperature}},
        )
        if r.status_code in (400, 401, 403):
            body = r.text[:200]
            if "API_KEY" in r.text or r.status_code in (401, 403):
                raise PermissionError(f"auth:{r.status_code} {body}")
            raise RuntimeError(f"http:{r.status_code} {body}")
        if r.status_code == 429:
            raise RuntimeError(f"rate:{r.status_code} {r.text[:200]}")
        if r.status_code >= 400:
            raise RuntimeError(f"http:{r.status_code} {r.text[:200]}")
        data = r.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"] or ""
        except (KeyError, IndexError):
            raise RuntimeError(f"bad-response:{str(data)[:200]}")


async def call_with_key(key_row: dict, messages: list[dict], max_tokens: int = 2000,
                        temperature: float = 0.3, timeout: int = 60) -> str:
    provider = key_row["provider"]
    kind = PROVIDERS.get(provider, {}).get("kind", "openai")
    if kind == "gemini" or provider == "gemini":
        return await _call_gemini(key_row["api_key"], key_row["model"] or "gemini-2.0-flash",
                                  messages, max_tokens, temperature, timeout)
    base = key_row["base_url"] or PROVIDERS.get(provider, {}).get("base", "")
    return await _call_openai(base, key_row["api_key"], key_row["model"],
                              messages, max_tokens, temperature, timeout)


# ---------- public API ----------
async def test_key(provider: str, base_url: str, api_key: str, model: str,
                   timeout: int = 30) -> tuple[bool, str, int]:
    """Test a donated key with a tiny ping. Returns (ok, detail, latency_ms)."""
    t0 = time.time()
    try:
        row = {"provider": provider, "base_url": base_url, "api_key": api_key.strip(),
               "model": model.strip()}
        out = await call_with_key(
            row, [{"role": "user", "content": "Reply with exactly: pong"}],
            max_tokens=10, temperature=0.0, timeout=timeout,
        )
        ms = int((time.time() - t0) * 1000)
        if "pong" in out.lower():
            return True, f"پاسخ سالم در {ms}ms ✅", ms
        return True, f"کلید کار کرد ولی پاسخ عجیب بود ({out[:60]}...) در {ms}ms", ms
    except PermissionError as e:
        return False, f"کلید نامعتبره (خطای احراز هویت): {e}", 0
    except Exception as e:
        return False, f"تست ناموفق: {str(e)[:250]}", 0


async def chat(db_path: str, messages: list[dict], max_tokens: int = 2000,
               temperature: float = 0.3, timeout: int = 60,
               order: list[str] | None = None) -> str:
    """Chat via the pool: round-robin + automatic fallback to next key."""
    keys = await db.list_ai_keys(db_path, only_active=True)
    if not keys:
        raise RuntimeError(
            "استخر کلید AI خالیه! ادمین باید در .env کلید بذاره یا کاربرها با «🎁 اهدای کلید» اضافه کنن."
        )
    if order:
        prio = {p: i for i, p in enumerate(order)}
        keys.sort(key=lambda k: (prio.get(k["provider"], 99), k["fail_count"], k["last_used"] or ""))
    errors: list[str] = []
    for k in keys:
        try:
            out = await call_with_key(k, messages, max_tokens, temperature, timeout)
            await db.mark_key_used(db_path, k["id"], ok=True)
            return out
        except PermissionError as e:
            await db.mark_key_used(db_path, k["id"], ok=False, dead=True)
            errors.append(f"{k['provider']}: کلید خراب، غیرفعال شد.")
        except Exception as e:
            await db.mark_key_used(db_path, k["id"], ok=False)
            errors.append(f"{k['provider']}: {str(e)[:120]}")
    raise RuntimeError("همه کلیدها خطا دادن:\n" + "\n".join(errors[:5]))


async def pool_stats(db_path: str) -> dict:
    keys = await db.list_ai_keys(db_path)
    active = [k for k in keys if k["status"] == "active"]
    by_provider: dict[str, dict] = {}
    for k in keys:
        p = by_provider.setdefault(k["provider"], {"active": 0, "dead": 0, "ok": 0, "fail": 0})
        p["active" if k["status"] == "active" else "dead"] += 1
        p["ok"] += k["success_count"]
        p["fail"] += k["fail_count"]
    return {"total": len(keys), "active": len(active), "by_provider": by_provider}
