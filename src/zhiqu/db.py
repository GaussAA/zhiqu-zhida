"""SQLite 数据层：企业知识条目 + 对话日志。

表结构：
- companies : 企业知识库条目（对应设计页 02）
- chat_logs : 每轮会话日志（对应设计页 03）
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

from .config import DB_PATH, ensure_dirs

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    ticker TEXT NOT NULL DEFAULT '',
    business TEXT NOT NULL DEFAULT '',
    industry TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '已发布' CHECK (status IN ('已发布', '审核中')),
    knowledge TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn INTEGER NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL DEFAULT '',
    intent TEXT NOT NULL DEFAULT '',
    hit INTEGER NOT NULL DEFAULT 0,
    fallback INTEGER NOT NULL DEFAULT 0,
    sources TEXT NOT NULL DEFAULT '',
    latency_ms INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_logs_session ON chat_logs (session_id);
"""


@dataclass
class Company:
    """企业知识条目。"""

    name: str
    ticker: str = ""
    business: str = ""
    industry: str = ""
    status: str = "已发布"
    knowledge: str = ""
    id: int | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class ChatLog:
    """单轮会话日志。"""

    session_id: str
    turn: int
    question: str
    answer: str = ""
    intent: str = ""
    hit: bool = False
    fallback: bool = False
    sources: str = ""
    latency_ms: int = 0
    id: int | None = None
    created_at: str = field(default_factory=lambda: _now())


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """获取 SQLite 连接（自动提交/回滚/关闭）。"""
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        logger.exception("SQLite 事务失败，已回滚 (db=%s)", DB_PATH)
        raise
    finally:
        conn.close()


def init_db() -> None:
    """初始化表结构（幂等）。"""
    with get_conn() as conn:
        conn.executescript(_SCHEMA)
    logger.info("数据库初始化完成: %s", DB_PATH)


# ---------- companies CRUD ----------

def upsert_company(c: Company) -> int:
    """按名称插入或更新企业条目，返回行 id。"""
    now = _now()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO companies (name, ticker, business, industry, status, knowledge, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                ticker=excluded.ticker, business=excluded.business,
                industry=excluded.industry, status=excluded.status,
                knowledge=excluded.knowledge, updated_at=excluded.updated_at
            """,
            (c.name, c.ticker, c.business, c.industry, c.status, c.knowledge, now, now),
        )
        row = conn.execute("SELECT id FROM companies WHERE name = ?", (c.name,)).fetchone()
        _ = cur
        return int(row["id"])


def list_companies(industry: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    """列出企业条目，支持行业/状态筛选。"""
    sql = "SELECT * FROM companies WHERE 1=1"
    args: list[Any] = []
    if industry:
        sql += " AND industry = ?"
        args.append(industry)
    if status:
        sql += " AND status = ?"
        args.append(status)
    sql += " ORDER BY id"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def get_company(company_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
        return dict(row) if row else None


def delete_company(company_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM companies WHERE id = ?", (company_id,))
        return cur.rowcount > 0


# ---------- chat_logs ----------

def insert_chat_log(log: ChatLog) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO chat_logs (session_id, turn, question, answer, intent, hit, fallback, sources, latency_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log.session_id, log.turn, log.question, log.answer, log.intent,
                int(log.hit), int(log.fallback), log.sources, log.latency_ms, log.created_at,
            ),
        )
        return int(cur.lastrowid or 0)


def list_chat_logs(session_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    sql = "SELECT * FROM chat_logs"
    args: list[Any] = []
    if session_id:
        sql += " WHERE session_id = ?"
        args.append(session_id)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def compute_metrics() -> dict[str, Any]:
    """日志指标：总会话数、总轮次、命中率、兜底率、平均轮次。"""
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(DISTINCT session_id) AS sessions,
                COUNT(*) AS turns,
                COALESCE(AVG(hit), 0) AS hit_rate,
                COALESCE(AVG(fallback), 0) AS fallback_rate
            FROM chat_logs
            """
        ).fetchone()
        sessions = int(row["sessions"])
        turns = int(row["turns"])
        return {
            "total_sessions": sessions,
            "total_turns": turns,
            "hit_rate": round(float(row["hit_rate"]), 4),
            "fallback_rate": round(float(row["fallback_rate"]), 4),
            "avg_turns": round(turns / sessions, 2) if sessions else 0.0,
        }
