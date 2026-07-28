"""服务层：会话管理 + 自动日志落库 + 指标 + 导出。

- chat(): 多轮会话统一入口（内存维护 history，每轮写 chat_logs）。
- export_logs(): 导出会话日志为 CSV 或 JSON。
"""

from __future__ import annotations

import csv
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .agent import AgentAnswer, answer_question
from .config import DATA_DIR
from .db import ChatLog, insert_chat_log

logger = logging.getLogger(__name__)

# 内存会话存储：session_id -> messages（重启即清，日志已持久化在 SQLite）
_SESSIONS: dict[str, list[dict[str, str]]] = {}
_MAX_HISTORY_TURNS = 6  # 只保留最近 N 轮，防上下文膨胀


def chat(question: str, session_id: str | None = None) -> AgentAnswer:
    """多轮会话入口：自动维护上下文、每轮落库。"""
    sid = session_id or uuid.uuid4().hex[:12]
    history = _SESSIONS.get(sid, [])

    result = answer_question(question, session_id=sid, history=list(history))

    # 更新会话上下文（裁剪到最近 N 轮）
    history = history + [
        {"role": "user", "content": question},
        {"role": "assistant", "content": result.answer},
    ]
    _SESSIONS[sid] = history[-_MAX_HISTORY_TURNS * 2 :]

    turn = len(_SESSIONS[sid]) // 2
    try:
        insert_chat_log(
            ChatLog(
                session_id=sid,
                turn=turn,
                question=question,
                answer=result.answer,
                intent=result.intent,
                hit=result.hit,
                fallback=result.fallback,
                sources=",".join(result.sources),
                latency_ms=result.latency_ms,
            )
        )
    except Exception:
        logger.exception("会话日志落库失败 (session=%s turn=%d)，不影响回答返回", sid, turn)

    logger.info(
        "chat 完成: session=%s turn=%d intent=%s hit=%s fallback=%s latency=%dms",
        sid, turn, result.intent, result.hit, result.fallback, result.latency_ms,
    )
    return result


def reset_session(session_id: str) -> None:
    """清除内存中的会话上下文。"""
    _SESSIONS.pop(session_id, None)


def export_logs(fmt: str = "csv", out_dir: Path | None = None) -> Path:
    """导出全部会话日志，返回导出文件路径。

    Args:
        fmt: "csv" 或 "json"
    """
    from .db import list_chat_logs

    if fmt not in ("csv", "json"):
        raise ValueError(f"不支持的导出格式: {fmt}（仅支持 csv/json）")

    rows = list_chat_logs(limit=100000)
    target_dir = out_dir or (DATA_DIR / "exports")
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = target_dir / f"chat_logs_{stamp}.{fmt}"

    try:
        if fmt == "json":
            path.write_text(
                json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        else:
            with path.open("w", newline="", encoding="utf-8-sig") as f:
                if rows:
                    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                    writer.writeheader()
                    writer.writerows(rows)
    except OSError:
        logger.exception("日志导出写文件失败: %s", path)
        raise

    logger.info("日志导出完成: %s (%d 条)", path, len(rows))
    return path


def get_metrics() -> dict[str, Any]:
    """日志指标透传（总会话/总轮次/命中率/兜底率/平均轮次）。"""
    from .db import compute_metrics

    return compute_metrics()
