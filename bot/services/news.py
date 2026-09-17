"""Auto-news: RSS feeds + full-article scrape."""
from __future__ import annotations

import feedparser
import httpx
from bs4 import BeautifulSoup

from ..texts import DEFAULT_NEWS_SOURCES


async def fetch_article_text(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as cli:
            r = await cli.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                return ""
            soup = BeautifulSoup(r.text, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
            paras = [p for p in paras if len(p) > 60]
            return "\n".join(paras[:12])[:4000]
    except Exception:
        return ""


async def fetch_candidates(sources: list[tuple[str, str]], per_source: int = 4) -> list[dict]:
    out: list[dict] = []
    for name, rss in sources:
        try:
            feed = feedparser.parse(rss)
            for e in (feed.entries or [])[:per_source]:
                guid = e.get("id") or e.get("link") or e.get("title", "")
                out.append({"guid": guid, "title": e.get("title", ""),
                            "url": e.get("link", ""), "source": name,
                            "summary": BeautifulSoup(e.get("summary", ""), "lxml").get_text(" ", strip=True)[:800]})
        except Exception:
            continue
    return out


def default_sources() -> list[tuple[str, str]]:
    return list(DEFAULT_NEWS_SOURCES)
