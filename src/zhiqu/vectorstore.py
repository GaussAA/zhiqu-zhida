"""检索层：bge-small-zh 向量化 + chromadb 持久化检索。

- 文档侧：企业知识文本按段切块后入库。
- 查询侧：bge 指令前缀 + cosine 距离阈值判定命中/兜底。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import chromadb

from .config import (
    BGE_QUERY_INSTRUCTION,
    CHROMA_DIR,
    EMBEDDING_MODEL,
    RETRIEVAL_MAX_DISTANCE,
    RETRIEVAL_TOP_K,
    ensure_dirs,
)
from .db import list_companies

logger = logging.getLogger(__name__)

COLLECTION_NAME = "company_knowledge"
_CHUNK_SIZE = 220
_CHUNK_OVERLAP = 40


@dataclass
class RetrievedChunk:
    """一条检索结果。"""

    text: str
    company: str
    distance: float

    @property
    def hit(self) -> bool:
        return self.distance <= RETRIEVAL_MAX_DISTANCE


@lru_cache(maxsize=1)
def _get_embedder() -> Any:
    """惰性加载 sentence-transformers 模型（首次调用下载权重）。"""
    from sentence_transformers import SentenceTransformer

    logger.info("加载 embedding 模型: %s", EMBEDDING_MODEL)
    try:
        return SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    except OSError:
        logger.exception("embedding 模型加载失败（网络/磁盘问题），请检查 HF 镜像配置")
        raise


@lru_cache(maxsize=1)
def _get_collection() -> Any:
    ensure_dirs()
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(
        COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )


def _chunk_text(text: str) -> list[str]:
    """按句号切分后贪心合并到约 _CHUNK_SIZE 字，带重叠。"""
    import re

    sentences = [s for s in re.split(r"(?<=[。！？])", text) if s.strip()]
    chunks: list[str] = []
    buf = ""
    for s in sentences:
        if len(buf) + len(s) > _CHUNK_SIZE and buf:
            chunks.append(buf)
            buf = buf[-_CHUNK_OVERLAP:] + s
        else:
            buf += s
    if buf.strip():
        chunks.append(buf)
    return chunks


def rebuild_index() -> int:
    """从 SQLite 全量重建向量索引（仅索引「已发布」条目），返回块数。"""
    col = _get_collection()
    existing = col.get()
    if existing["ids"]:
        col.delete(ids=existing["ids"])

    companies = list_companies(status="已发布")
    if not companies:
        logger.warning("知识库为空，索引未建立")
        return 0

    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict[str, Any]] = []
    for c in companies:
        header = f"【{c['name']}】（{c['ticker']}｜{c['industry']}｜主营：{c['business']}）"
        for i, chunk in enumerate(_chunk_text(str(c["knowledge"]))):
            ids.append(f"c{c['id']}-{i}")
            docs.append(f"{header}{chunk}")
            metas.append({"company": c["name"], "company_id": c["id"], "chunk": i})

    embedder = _get_embedder()
    vectors = embedder.encode(docs, normalize_embeddings=True).tolist()
    col.add(ids=ids, documents=docs, embeddings=vectors, metadatas=metas)
    logger.info("向量索引重建完成: %d 家企业 / %d 块", len(companies), len(ids))
    return len(ids)


def search(query: str, top_k: int = RETRIEVAL_TOP_K) -> list[RetrievedChunk]:
    """向量检索，返回带距离的知识块（由调用方判定命中）。"""
    col = _get_collection()
    if col.count() == 0:
        logger.warning("向量库为空，请先执行 rebuild_index()")
        return []

    embedder = _get_embedder()
    qvec = embedder.encode(
        [BGE_QUERY_INSTRUCTION + query], normalize_embeddings=True
    ).tolist()
    res = col.query(query_embeddings=qvec, n_results=min(top_k, col.count()))

    out: list[RetrievedChunk] = []
    for doc, meta, dist in zip(
        res["documents"][0], res["metadatas"][0], res["distances"][0]
    ):
        out.append(RetrievedChunk(text=doc, company=str(meta["company"]), distance=round(float(dist), 4)))
    return out
