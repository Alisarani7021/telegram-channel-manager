"""Daily dollar/gold price (free sources with fallbacks)."""
from __future__ import annotations

import httpx


async def fetch_prices(navasan_key: str = "") -> dict:
    """Returns {dollar: str, gold18: str, source: str}. Raises on total failure."""
    # 1) BRSAPI free key
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
    # 2) Navasan (if admin provided a key)
    if navasan_key:
        try:
            async with httpx.AsyncClient(timeout=20) as cli:
                r = await cli.get(f"https://api.navasan.tech/latest/?api_key={navasan_key}")
                if r.status_code == 200:
                    d = r.json()
                    usd = (d.get("usd_sell") or {}).get("value")
                    sek = (d.get("sekke") or {}).get("value")
                    if usd:
                        return {"dollar": str(usd), "gold18": str(seek or "—"),
                                "source": "Navasan"}
        except Exception:
            pass
    # 3) Bonbast public (best-effort)
    try:
        async with httpx.AsyncClient(timeout=20) as cli:
            r = await cli.get("https://api.bonbast.com/",
                              headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                d = r.json()
                usd = d.get("usd1") or d.get("usd")
                if usd:
                    return {"dollar": str(usd), "gold18": "—", "source": "Bonbast"}
    except Exception:
        pass
    raise RuntimeError("هیچ منبع قیمتی جواب نداد.")


def fa_num(s: str) -> str:
    per = "۰۱۲۳۴۵۶۷۸۹"
    out = ""
    for ch in s:
        out += per[int(ch)] if ch.isdigit() else ch
    return out


def format_price_message(p: dict) -> str:
    return (
        "💰 <b>قیمت امروز دلار و طلا</b>\n\n"
        f"💵 دلار آزاد: <b>{fa_num(p['dollar'])} تومان</b>\n"
        f"🪙 طلای ۱۸ عیار: <b>{fa_num(p['gold18'])} تومان</b>\n\n"
        f"<i>منبع: {p['source']}</i>"
    )
