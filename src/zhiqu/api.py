"""API 层：FastAPI 暴露对话 / 知识库 / 日志三组接口，并托管前端静态资源。

启动：uv run uvicorn zhiqu.api:app --app-dir src --port 8720
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from .config import ROOT_DIR
from .seed import run_seed
from .service import chat, export_logs, get_metrics, reset_session
from .vectorstore import rebuild_index

logger = logging.getLogger(__name__)

app = FastAPI(title="知企智答 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    """启动时确保种子数据与向量索引就绪。"""
    try:
        run_seed()
        if not db.list_chat_logs(limit=1):
            logger.info("首次启动：无历史日志")
        rebuild_index()
    except Exception:
        logger.exception("启动初始化失败（种子/索引）")
        raise


# ---------- 对话 ----------

class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    intent: str
    hit: bool
    fallback: bool
    sources: list[str]
    model: str
    latency_ms: int


@app.post("/api/chat", response_model=ChatResponse)
def api_chat(req: ChatRequest) -> ChatResponse:
    try:
        r = chat(req.question, session_id=req.session_id)
    except Exception as e:
        logger.exception("对话处理失败: %s", req.question[:50])
        raise HTTPException(status_code=500, detail=f"对话处理失败: {e}") from e
    return ChatResponse(
        session_id=r.session_id,
        answer=r.answer,
        intent=r.intent,
        hit=r.hit,
        fallback=r.fallback,
        sources=r.sources,
        model=r.model,
        latency_ms=r.latency_ms,
    )


@app.post("/api/chat/{session_id}/reset")
def api_reset(session_id: str) -> dict[str, str]:
    reset_session(session_id)
    return {"status": "ok"}


# ---------- 知识库 ----------

class CompanyIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    ticker: str = ""
    business: str = ""
    industry: str = ""
    status: Literal["已发布", "审核中"] = "已发布"
    knowledge: str = ""


@app.get("/api/companies")
def api_list_companies(industry: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    return db.list_companies(industry=industry, status=status)


@app.post("/api/companies")
def api_upsert_company(c: CompanyIn) -> dict[str, Any]:
    try:
        cid = db.upsert_company(db.Company(**c.model_dump()))
        n = rebuild_index()
    except Exception as e:
        logger.exception("企业条目保存失败: %s", c.name)
        raise HTTPException(status_code=500, detail=f"保存失败: {e}") from e
    return {"id": cid, "indexed_chunks": n}


@app.delete("/api/companies/{company_id}")
def api_delete_company(company_id: int) -> dict[str, Any]:
    if not db.get_company(company_id):
        raise HTTPException(status_code=404, detail="企业不存在")
    db.delete_company(company_id)
    n = rebuild_index()
    return {"deleted": company_id, "indexed_chunks": n}


@app.get("/api/companies/stats")
def api_company_stats() -> dict[str, Any]:
    rows = db.list_companies()
    industries: dict[str, int] = {}
    published = 0
    for r in rows:
        industries[str(r["industry"])] = industries.get(str(r["industry"]), 0) + 1
        if r["status"] == "已发布":
            published += 1
    return {
        "total": len(rows),
        "published": published,
        "pending": len(rows) - published,
        "industries": industries,
    }


# ---------- 日志 ----------

@app.get("/api/logs")
def api_logs(session_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    return db.list_chat_logs(session_id=session_id, limit=limit)


@app.get("/api/metrics")
def api_metrics() -> dict[str, Any]:
    return get_metrics()


@app.get("/api/logs/export")
def api_export(fmt: Literal["csv", "json"] = "csv") -> FileResponse:
    try:
        path = export_logs(fmt)
    except Exception as e:
        logger.exception("日志导出失败 fmt=%s", fmt)
        raise HTTPException(status_code=500, detail=f"导出失败: {e}") from e
    media = "text/csv" if fmt == "csv" else "application/json"
    return FileResponse(path, media_type=media, filename=path.name)


# ---------- 前端静态托管（构建产物存在时） ----------

_UI_DIST = ROOT_DIR / "web" / "dist"
if _UI_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_UI_DIST), html=True), name="ui")
