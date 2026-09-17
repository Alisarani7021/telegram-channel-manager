"""Daily dollar/gold price.

Primary: Navasan (free key from navasan.tech — 1 request/day is far below free quota).
Fallback: BRSAPI free key (sometimes down, kept as best-effort).
"""
from __future__ import annotations

import httpx


def _pick(d: dict, *candidates: str) -> str:
    for key in candidates:
        v = d.get(key)
        if isinstance(v, dict):
            v = v.get("value") or v.get("price")
        if v:
            return str(v)
    # fuzzy: first key containing any candidate substring
    low = {k.lower(): k for k in d}
    for cand in candidates:
        for lk, orig in low.items():
            if cand in lk:
                v = d[orig]
                if isinstance(v, dict):
                    v = v.get("value") or v.get("price")
                if v:
                    return str(v)
    return ""


async def fetch_prices(navasan_key: str = "") -> dict:
    """Returns {dollar: str, gold18: str, source: str}. Raises on total failure."""
    # 1) Navasan (needs free key, most reliable)
    if navasan_key:
        try:
            async with httpx.AsyncClient(timeout=20) as cli:
                r = await cli.get(f"https://api.navasan.tech/latest/?api_key={navasan_key}")
                if r.status_code == 200:
                    d = r.json()
                    dollar = _pick(d, "usd_sell", "usd", "dollar")
                    gold18 = _pick(d, "gold_18", "geram18", "18ayar", "tala", "gold") or _pick(d, "sekke")
                    if dollar:
                        return {"dollar": dollar, "gold18": gold18 or "—", "source": "Navasan"}
        except Exception:
            pass
    # 2) BRSAPI free key (best-effort, often down)
    try:
        async with httpx.AsyncClient(timeout=20) as cli:
            r = await cli.get("https://brsapi.ir/Api/Market/Gold_Currency.php?key=Free")
            if r.status_code == 200:
                data = r.json()
                gold = data.get("gold", [])
                curr = data.get("currency", [])
                dollar = next((c.get("price") for c in curr
                               if "dollar" in str(c.get("symbol", "")).lower()
                               or "دلار" in str(c.get("name", ""))), None)
                gold18 = next((g.get("price") for g in gold
                               if "18" in str(g.get("symbol", "")) or "18" in str(g.get("name", ""))), None)
                if dollar or gold18:
                    return {"dollar": str(dollar or "—"), "gold18": str(gold18 or "—"),
                            "source": "BRSAPI"}
    except Exception:
        pass
    raise RuntimeError(
        "هیچ منبع قیمتی جواب نداد. برای قیمت پایدار یه کلید رایگان از navasan.tech بگیر "
        "و بذار تو .env جلوی NAVASAN_KEY (آموزشش تو README بخش قیمت دلار و طلاست)."
    )


def fa_num(s: str) -> str:
    per = "۰۱۲۳۴۵۶۷۸۹"
    out = ""
    for ch in s:
        out += per[int(ch)] if ch.isdigit() else ch
    return out


def format_price_message(p: dict) -> str:
    gold = f"🪙 طلای ۱۸ عیار: <b>{fa_num(p['gold18'])} تومان</b>\n" if p.get("gold18") not in ("", "—") else ""
    return (
        "💰 <b>قیمت امروز دلار و طلا</b>\n\n"
        f"💵 دلار آزاد: <b>{fa_num(p['dollar'])} تومان</b>\n"
        f"{gold}\n"
        f"<i>منبع: {p['source']}</i>"
    )
