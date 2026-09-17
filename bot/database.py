"""SQLite storage (aiosqlite). One file, zero-config — perfect for a small VPS."""
from __future__ import annotations

import aiosqlite
import json
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  user_id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  mode TEXT NOT NULL DEFAULT 'bot',
  phone TEXT DEFAULT '',
  session TEXT DEFAULT '',
  paused INTEGER NOT NULL DEFAULT 0,
  publish_mode TEXT NOT NULL DEFAULT 'review'
);
CREATE TABLE IF NOT EXISTS settings(
  user_id INTEGER PRIMARY KEY,
  send_interval_min INTEGER NOT NULL DEFAULT 30,
  work_start INTEGER NOT NULL DEFAULT 0,
  work_end INTEGER NOT NULL DEFAULT 24,
  content_style TEXT NOT NULL DEFAULT 'medium',
  signature_mode TEXT NOT NULL DEFAULT 'none',
  signature_text TEXT NOT NULL DEFAULT '',
  signature_url TEXT NOT NULL DEFAULT '',
  signature_word TEXT NOT NULL DEFAULT '',
  premium_mode TEXT NOT NULL DEFAULT 'normal',
  translate_enabled INTEGER NOT NULL DEFAULT 1,
  dedup_enabled INTEGER NOT NULL DEFAULT 1,
  custom_rule TEXT NOT NULL DEFAULT '',
  channel_topic TEXT NOT NULL DEFAULT '',
  type_filters TEXT NOT NULL DEFAULT '[]',
  text_filters TEXT NOT NULL DEFAULT '[]',
  rumor_enabled INTEGER NOT NULL DEFAULT 0,
  rumor_action TEXT NOT NULL DEFAULT 'reject',
  survey_mode INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sources(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  channel TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  last_msg_id INTEGER NOT NULL DEFAULT 0,
  translate_override INTEGER,
  added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dests(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  channel TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS queue(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  source TEXT NOT NULL DEFAULT '',
  source_msg_ids TEXT NOT NULL DEFAULT '[]',
  media_type TEXT NOT NULL DEFAULT 'text',
  text_raw TEXT NOT NULL DEFAULT '',
  text_clean TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending_review',
  kind TEXT NOT NULL DEFAULT 'repost',
  extra TEXT NOT NULL DEFAULT '{}',
  reason TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  scheduled_at TEXT NOT NULL DEFAULT '',
  review_msg_id INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS stats_daily(
  user_id INTEGER NOT NULL,
  day TEXT NOT NULL,
  posted INTEGER NOT NULL DEFAULT 0,
  approved INTEGER NOT NULL DEFAULT 0,
  rejected INTEGER NOT NULL DEFAULT 0,
  ai_calls INTEGER NOT NULL DEFAULT 0,
  reasons TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY(user_id, day)
);
CREATE TABLE IF NOT EXISTS ai_keys(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider TEXT NOT NULL,
  base_url TEXT NOT NULL DEFAULT '',
  api_key TEXT NOT NULL,
  model TEXT NOT NULL DEFAULT '',
  added_by INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active',
  fail_count INTEGER NOT NULL DEFAULT 0,
  success_count INTEGER NOT NULL DEFAULT 0,
  last_test TEXT NOT NULL DEFAULT '',
  last_used TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS seen(
  user_id INTEGER NOT NULL,
  h TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(user_id, h)
);
CREATE TABLE IF NOT EXISTS published(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  excerpt TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_cfg(
  user_id INTEGER PRIMARY KEY,
  enabled INTEGER NOT NULL DEFAULT 0,
  hour INTEGER NOT NULL DEFAULT 9
);
CREATE TABLE IF NOT EXISTS news_cfg(
  user_id INTEGER PRIMARY KEY,
  enabled INTEGER NOT NULL DEFAULT 0,
  topic TEXT NOT NULL DEFAULT '',
  per_cycle INTEGER NOT NULL DEFAULT 2,
  sources TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS news_seen(
  user_id INTEGER NOT NULL,
  guid TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(user_id, guid)
);
CREATE TABLE IF NOT EXISTS notif(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  chat_id INTEGER NOT NULL,
  msg_id INTEGER NOT NULL,
  kind TEXT NOT NULL DEFAULT 'auto',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS annc(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  text TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_queue_user_status ON queue(user_id, status);
CREATE INDEX IF NOT EXISTS idx_sources_user ON sources(user_id);
"""


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def today_str() -> str:
    return time.strftime("%Y-%m-%d")


async def init_db(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(SCHEMA)
        await db.commit()


# ---------- users ----------
async def get_user(db_path: str, user_id: int) -> dict | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def ensure_user(db_path: str, user_id: int) -> dict:
    u = await get_user(db_path, user_id)
    if u:
        return u
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO users(user_id, created_at) VALUES(?, ?)", (user_id, now_iso())
        )
        await db.execute("INSERT OR IGNORE INTO settings(user_id) VALUES(?)", (user_id,))
        await db.execute("INSERT OR IGNORE INTO price_cfg(user_id) VALUES(?)", (user_id,))
        await db.execute("INSERT OR IGNORE INTO news_cfg(user_id) VALUES(?)", (user_id,))
        await db.commit()
    return await get_user(db_path, user_id)  # type: ignore


async def set_user(db_path: str, user_id: int, **fields) -> None:
    if not fields:
        return
    keys = ", ".join(f"{k}=?" for k in fields)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(f"UPDATE users SET {keys} WHERE user_id=?", (*fields.values(), user_id))
        await db.commit()


async def all_users(db_path: str) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users")
        return [dict(r) for r in await cur.fetchall()]


# ---------- settings ----------
DEFAULT_SETTINGS = {
    "send_interval_min": 30, "work_start": 0, "work_end": 24, "content_style": "medium",
    "signature_mode": "none", "signature_text": "", "signature_url": "", "signature_word": "",
    "premium_mode": "normal", "translate_enabled": 1, "dedup_enabled": 1, "custom_rule": "",
    "channel_topic": "", "type_filters": "[]", "text_filters": "[]",
    "rumor_enabled": 0, "rumor_action": "reject", "survey_mode": 0,
}


async def get_settings(db_path: str, user_id: int) -> dict:
    await ensure_user(db_path, user_id)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM settings WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        data = dict(DEFAULT_SETTINGS)
        if row:
            data.update({k: row[k] for k in row.keys() if k != "user_id"})
        return data


async def set_settings(db_path: str, user_id: int, **fields) -> None:
    await ensure_user(db_path, user_id)
    keys = ", ".join(f"{k}=?" for k in fields)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(f"UPDATE settings SET {keys} WHERE user_id=?", (*fields.values(), user_id))
        await db.commit()


# ---------- sources / dests ----------
async def add_source(db_path: str, user_id: int, channel: str, title: str = "") -> int:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "INSERT INTO sources(user_id, channel, title, added_at) VALUES(?,?,?,?)",
            (user_id, channel, title, now_iso()),
        )
        await db.commit()
        return int(cur.lastrowid)


async def list_sources(db_path: str, user_id: int) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM sources WHERE user_id=? ORDER BY id", (user_id,))
        return [dict(r) for r in await cur.fetchall()]


async def remove_source(db_path: str, user_id: int, src_id: int) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM sources WHERE id=? AND user_id=?", (src_id, user_id))
        await db.commit()


async def set_source_last(db_path: str, src_id: int, last_id: int) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE sources SET last_msg_id=? WHERE id=?", (last_id, src_id))
        await db.commit()


async def set_source_translate(db_path: str, src_id: int, value: int | None) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE sources SET translate_override=? WHERE id=?", (value, src_id))
        await db.commit()


async def add_dest(db_path: str, user_id: int, channel: str, title: str = "") -> int:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "INSERT INTO dests(user_id, channel, title, added_at) VALUES(?,?,?,?)",
            (user_id, channel, title, now_iso()),
        )
        await db.commit()
        return int(cur.lastrowid)


async def list_dests(db_path: str, user_id: int) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM dests WHERE user_id=? ORDER BY id", (user_id,))
        return [dict(r) for r in await cur.fetchall()]


async def remove_dest(db_path: str, user_id: int, dest_id: int) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM dests WHERE id=? AND user_id=?", (dest_id, user_id))
        await db.commit()


# ---------- queue ----------
async def enqueue(
    db_path: str, user_id: int, source: str, msg_ids: list[int], media_type: str,
    text_raw: str, text_clean: str, status: str, kind: str = "repost", extra: dict | None = None,
) -> int:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            """INSERT INTO queue(user_id, source, source_msg_ids, media_type, text_raw,
               text_clean, status, kind, extra, created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (user_id, source, json.dumps(msg_ids, ensure_ascii=False), media_type,
             text_raw[:8000], text_clean[:8000], status, kind,
             json.dumps(extra or {}, ensure_ascii=False), now_iso()),
        )
        await db.commit()
        return int(cur.lastrowid)


async def get_queue_item(db_path: str, qid: int) -> dict | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM queue WHERE id=?", (qid,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def set_queue(db_path: str, qid: int, **fields) -> None:
    keys = ", ".join(f"{k}=?" for k in fields)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(f"UPDATE queue SET {keys} WHERE id=?", (*fields.values(), qid))
        await db.commit()


async def next_queued(db_path: str, user_id: int) -> dict | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM queue WHERE user_id=? AND status='queued' ORDER BY id LIMIT 1",
            (user_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def count_queued(db_path: str, user_id: int) -> int:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM queue WHERE user_id=? AND status IN ('queued','pending_review')",
            (user_id,),
        )
        row = await cur.fetchone()
        return int(row[0])


async def last_published_at(db_path: str, user_id: int) -> str:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT scheduled_at FROM queue WHERE user_id=? AND status='published' ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        row = await cur.fetchone()
        return row[0] if row and row[0] else ""


# ---------- stats ----------
async def bump_stat(db_path: str, user_id: int, field: str, reason: str = "") -> None:
    day = today_str()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT OR IGNORE INTO stats_daily(user_id, day) VALUES(?, ?)", (user_id, day)
        )
        if field in ("posted", "approved", "rejected", "ai_calls"):
            await db.execute(
                f"UPDATE stats_daily SET {field}={field}+1 WHERE user_id=? AND day=?",
                (user_id, day),
            )
        if reason:
            cur = await db.execute(
                "SELECT reasons FROM stats_daily WHERE user_id=? AND day=?", (user_id, day)
            )
            row = await cur.fetchone()
            try:
                reasons = json.loads(row[0] or "{}")
            except Exception:
                reasons = {}
            reasons[reason] = reasons.get(reason, 0) + 1
            await db.execute(
                "UPDATE stats_daily SET reasons=? WHERE user_id=? AND day=?",
                (json.dumps(reasons, ensure_ascii=False), user_id, day),
            )
        await db.commit()


async def get_stat(db_path: str, user_id: int, day: str = "") -> dict:
    day = day or today_str()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM stats_daily WHERE user_id=? AND day=?", (user_id, day)
        )
        row = await cur.fetchone()
        if row:
            return dict(row)
        return {"user_id": user_id, "day": day, "posted": 0, "approved": 0, "rejected": 0,
                "ai_calls": 0, "reasons": "{}"}


async def today_ai_usage(db_path: str, user_id: int) -> int:
    s = await get_stat(db_path, user_id)
    return int(s.get("ai_calls", 0))


# ---------- ai keys ----------
async def add_ai_key(db_path: str, provider: str, base_url: str, api_key: str,
                     model: str, added_by: int = 0, note: str = "") -> int:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            """INSERT INTO ai_keys(provider, base_url, api_key, model, added_by, status, last_test, note)
               VALUES(?,?,?,?,?,'active',?,?)""",
            (provider, base_url, api_key, model, added_by, now_iso(), note),
        )
        await db.commit()
        return int(cur.lastrowid)


async def list_ai_keys(db_path: str, only_active: bool = False) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        q = "SELECT * FROM ai_keys ORDER BY id"
        if only_active:
            q = "SELECT * FROM ai_keys WHERE status='active' ORDER BY fail_count ASC, last_used ASC"
        cur = await db.execute(q)
        rows = await cur.fetchall()
        out = []
        for r in rows:
            d = dict(r)
            k = d.get("api_key", "")
            d["masked"] = (k[:4] + "…" + k[-4:]) if len(k) > 10 else "****"
            out.append(d)
        return out


async def delete_ai_key(db_path: str, key_id: int) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM ai_keys WHERE id=?", (key_id,))
        await db.commit()


async def mark_key_used(db_path: str, key_id: int, ok: bool, dead: bool = False) -> None:
    async with aiosqlite.connect(db_path) as db:
        if dead:
            await db.execute("UPDATE ai_keys SET status='dead' WHERE id=?", (key_id,))
        elif ok:
            await db.execute(
                "UPDATE ai_keys SET success_count=success_count+1, last_used=? WHERE id=?",
                (now_iso(), key_id),
            )
        else:
            await db.execute(
                "UPDATE ai_keys SET fail_count=fail_count+1 WHERE id=?", (key_id,)
            )
        await db.commit()


async def key_exists(db_path: str, api_key: str) -> bool:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("SELECT COUNT(*) FROM ai_keys WHERE api_key=?", (api_key.strip(),))
        return int((await cur.fetchone())[0]) > 0


# ---------- dedup helpers ----------
async def has_seen(db_path: str, user_id: int, h: str) -> bool:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("SELECT COUNT(*) FROM seen WHERE user_id=? AND h=?", (user_id, h))
        return int((await cur.fetchone())[0]) > 0


async def add_seen(db_path: str, user_id: int, h: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO seen(user_id, h, created_at) VALUES(?,?,?)",
            (user_id, h, now_iso()),
        )
        await db.commit()


async def add_published(db_path: str, user_id: int, excerpt: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO published(user_id, excerpt, created_at) VALUES(?,?,?)",
            (user_id, excerpt[:500], now_iso()),
        )
        # keep last 60 only
        await db.execute(
            """DELETE FROM published WHERE user_id=? AND id NOT IN
               (SELECT id FROM published WHERE user_id=? ORDER BY id DESC LIMIT 60)""",
            (user_id, user_id),
        )
        await db.commit()


async def recent_published(db_path: str, user_id: int, limit: int = 15) -> list[str]:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT excerpt FROM published WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        return [r[0] for r in await cur.fetchall()]


# ---------- price / news cfg ----------
async def get_price_cfg(db_path: str, user_id: int) -> dict:
    await ensure_user(db_path, user_id)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM price_cfg WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else {"user_id": user_id, "enabled": 0, "hour": 9}


async def set_price_cfg(db_path: str, user_id: int, **fields) -> None:
    await ensure_user(db_path, user_id)
    keys = ", ".join(f"{k}=?" for k in fields)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(f"UPDATE price_cfg SET {keys} WHERE user_id=?", (*fields.values(), user_id))
        await db.commit()


async def get_news_cfg(db_path: str, user_id: int) -> dict:
    await ensure_user(db_path, user_id)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM news_cfg WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else {"user_id": user_id, "enabled": 0, "topic": "", "per_cycle": 2, "sources": "[]"}


async def set_news_cfg(db_path: str, user_id: int, **fields) -> None:
    await ensure_user(db_path, user_id)
    keys = ", ".join(f"{k}=?" for k in fields)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(f"UPDATE news_cfg SET {keys} WHERE user_id=?", (*fields.values(), user_id))
        await db.commit()


async def news_seen_has(db_path: str, user_id: int, guid: str) -> bool:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM news_seen WHERE user_id=? AND guid=?", (user_id, guid)
        )
        return int((await cur.fetchone())[0]) > 0


async def news_seen_add(db_path: str, user_id: int, guid: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO news_seen(user_id, guid, created_at) VALUES(?,?,?)",
            (user_id, guid, now_iso()),
        )
        await db.commit()


# ---------- notifications (for nightly cleanup) ----------
async def log_notif(db_path: str, user_id: int, chat_id: int, msg_id: int, kind: str = "auto") -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO notif(user_id, chat_id, msg_id, kind, created_at) VALUES(?,?,?,?,?)",
            (user_id, chat_id, msg_id, kind, now_iso()),
        )
        await db.commit()


async def day_notifs(db_path: str, user_id: int, day_prefix: str) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM notif WHERE user_id=? AND created_at LIKE ?",
            (user_id, day_prefix + "%"),
        )
        return [dict(r) for r in await cur.fetchall()]


async def clear_day_notifs(db_path: str, user_id: int, day_prefix: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "DELETE FROM notif WHERE user_id=? AND created_at LIKE ?", (user_id, day_prefix + "%")
        )
        await db.commit()


# ---------- announcements ----------
async def add_annc(db_path: str, text: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("INSERT INTO annc(text, created_at) VALUES(?,?)", (text, now_iso()))
        await db.commit()


async def list_annc(db_path: str, limit: int = 5) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM annc ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in await cur.fetchall()]
