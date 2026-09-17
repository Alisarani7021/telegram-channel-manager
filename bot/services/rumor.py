"""Rumor check (beta): free DuckDuckGo search + optional Tavily, judged by AI."""
from __future__ import annotations

import re

import httpx

from . import cleaner


async def ddg_search(query: str, timeout: int = 20) -> str:
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as cli:
            r = await cli.post("https://html.duckduckgo.com/html/",
                               data={"q": query[:200]},
                               headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                return ""
            snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', r.text, re.S)
            clean = [re.sub(r"<[^>]+>", "", s).strip() for s in snippets[:6]]
            return "\n".join(f"• {c[:300]}" for c in clean if c)
    except Exception:
        return ""


async def tavily_search(query: str, api_key: str, timeout: int = 25) -> str:
    try:
        async with httpx.AsyncClient(timeout=timeout) as cli:
            r = await cli.post("https://api.tavily.com/search",
                               headers={"Content-Type": "application/json"},
                               json={"api_key": api_key, "query": query[:300],
                                     "max_results": 5, "search_depth": "basic"})
            if r.status_code != 200:
                return ""
            data = r.json()
            return "\n".join(f"• {(x.get('content') or '')[:300]}"
                             for x in (data.get("results") or [])[:5])
    except Exception:
        return ""


async def check(db_path: str, claim: str, tavily_key: str = "",
                order: list[str] | None = None) -> dict:
    query = re.sub(r"\s+", " ", claim)[:200]
    snippets = ""
    if tavily_key:
        snippets = await tavily_search(query, tavily_key)
    if not snippets:
        snippets = await ddg_search(query)
    if not snippets:
        return {"verdict": "uncertain", "reason": "نتیجه‌ای از وب گرفته نشد."}
    return await cleaner.rumor_verdict(db_path, claim, snippets, order=order)
