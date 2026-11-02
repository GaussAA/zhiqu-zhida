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
from .db import get_company, list_companies

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


def _company_chunks(c: dict[str, Any]) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """把一个企业条目切成（ids, docs, metas）；知识为空时返回三个空容器。"""
    header = f"【{c['name']}】（{c['ticker']}｜{c['industry']}｜主营：{c['business']}）"
    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict[str, Any]] = []
    for i, chunk in enumerate(_chunk_text(str(c["knowledge"]))):
        ids.append(f"c{c['id']}-{i}")
        docs.append(f"{header}{chunk}")
        metas.append({"company": c["name"], "company_id": c["id"], "chunk": i})
    return ids, docs, metas


def _chunk_ids_for(company_id: int) -> list[str]:
    """取某企业当前在库的块 id（按前缀匹配）。"""
    prefix = f"c{company_id}-"
    return [str(i) for i in _get_collection().get()["ids"] if str(i).startswith(prefix)]


def sync_company(company_id: int) -> int:
    """**增量**重建单个企业的向量块，返回块数。

    相比 rebuild_index 的全量重嵌入，这里只嵌入该企业自身的内容——
    写入一条的代价从 O(全库) 降到 O(单条)。
    未发布 / 无知识 / 已删除的条目，其旧块会被清除（保证检索面与治理口径一致）。
    """
    col = _get_collection()
    old_ids = _chunk_ids_for(company_id)

    row = get_company(company_id)
    if not row or row["status"] != "已发布":
        if old_ids:
            col.delete(ids=old_ids)
        return 0

    ids, docs, metas = _company_chunks(row)
    if not ids:
        if old_ids:
            col.delete(ids=old_ids)
        return 0

    vectors = _get_embedder().encode(docs, normalize_embeddings=True).tolist()
    # 先 upsert 新块、再删陈旧块：全程旧索引可用（无空窗）
    col.upsert(ids=ids, documents=docs, embeddings=vectors, metadatas=metas)
    stale = set(old_ids) - set(ids)
    if stale:
        col.delete(ids=list(stale))
    logger.info("企业 %s 索引增量更新：%d 块（清理 %d 块）", company_id, len(ids), len(stale))
    return len(ids)


def remove_company_from_index(company_id: int) -> int:
    """从索引移除某企业的全部块，返回移除块数。"""
    old_ids = _chunk_ids_for(company_id)
    if old_ids:
        _get_collection().delete(ids=old_ids)
    return len(old_ids)


def rebuild_index() -> int:
    """从 SQLite 全量重建向量索引（仅索引「已发布」条目），返回块数。

    用于启动初始化与「索引与库不一致」的兜底修复；日常单条增删走 sync_company。
    """
    col = _get_collection()
    existing_ids = set(col.get()["ids"])

    companies = list_companies(status="已发布")
    if not companies:
        logger.warning("知识库为空，索引未建立")
        return 0

    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict[str, Any]] = []
    for c in companies:
        cids, cdocs, cmetas = _company_chunks(c)
        ids.extend(cids)
        docs.extend(cdocs)
        metas.extend(cmetas)

    if not ids:
        # 全库为空：只能删（此时不存在「先 add 再删」的掩护）
        if existing_ids:
            col.delete(ids=list(existing_ids))
        logger.warning("知识库无已发布条目，索引已清空")
        return 0

    embedder = _get_embedder()
    vectors = embedder.encode(docs, normalize_embeddings=True).tolist()

    # 审计 F2：先 upsert 新块、再删陈旧块 —— 重建期间旧索引始终可用，消除空窗。
    # 原实现「先 delete 全部再 add」会让并发请求在窗口内查到空库，被判「无资料」。
    col.upsert(ids=ids, documents=docs, embeddings=vectors, metadatas=metas)
    stale = existing_ids - set(ids)
    if stale:
        col.delete(ids=list(stale))
    logger.info(
        "向量索引重建完成: %d 家企业 / %d 块（清理陈旧 %d 块）",
        len(companies), len(ids), len(stale),
    )
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
