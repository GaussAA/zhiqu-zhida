"""审计回归护栏：锁定本轮修复的四个安全/正确性不变量。

设计取舍：
- **不依赖 chromadb / sentence-transformers**（用空 module + 可控桩隔离），
  使这些用例能在 CI 里秒级跑完，不必下载模型；
- 断言针对**修复后的期望行为**，用于防「修了又退」。

对应审计发现：
    F1  知识库写入无鉴权 + status 默认已发布
    F2  重建先删后加 → 索引空窗
    F3  日志/导出无鉴权
    F4  模块级 global 跨请求串扰
"""

from __future__ import annotations

import os
import sys
import threading
import time
import types
from pathlib import Path

import pytest

# ---- 必须在 import zhiqu 之前完成 ----
os.environ.setdefault("ADMIN_TOKEN", "test-admin-token")
for _name in ("chromadb", "sentence_transformers"):
    sys.modules.setdefault(_name, types.ModuleType(_name))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zhiqu import agent as A  # noqa: E402
from zhiqu import db  # noqa: E402
from zhiqu.vectorstore import RetrievedChunk  # noqa: E402

TOKEN = os.environ["ADMIN_TOKEN"]


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """每个用例独立 SQLite 文件，避免污染仓库内 data/。"""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    yield
    for row in db.list_companies():
        db.delete_company(int(row["id"]))


@pytest.fixture()
def client(temp_db, monkeypatch):
    import zhiqu.api as api_mod
    from fastapi.testclient import TestClient

    monkeypatch.setattr(api_mod, "rebuild_index", lambda: 0)
    monkeypatch.setattr(api_mod, "sync_company", lambda cid: 0)
    monkeypatch.setattr(api_mod, "remove_company_from_index", lambda cid: 0)
    return TestClient(api_mod.app)


# ---------------------------------------------------------------- F1 / F3
MANAGED = [
    ("GET", "/api/logs", None),
    ("GET", "/api/metrics", None),
    ("GET", "/api/companies", None),
    ("GET", "/api/companies/stats", None),
    ("GET", "/api/logs/export?fmt=json", None),
    ("POST", "/api/companies", {"name": "测试企业", "knowledge": "x"}),
]


@pytest.mark.parametrize("method,path,body", MANAGED)
def test_admin_endpoints_reject_without_token(client, method, path, body):
    """F1/F3：管理接口无凭据必须被拒（fail-closed）。"""
    r = client.request(method, path, json=body)
    assert r.status_code in (401, 403, 503), f"{method} {path} 竟然返回 {r.status_code}"


@pytest.mark.parametrize("method,path,body", MANAGED)
def test_admin_endpoints_allow_with_token(client, method, path, body):
    """F1/F3：带正确凭据应放行（否则修复过度）。"""
    r = client.request(method, path, json=body, headers={"X-Admin-Token": TOKEN})
    assert r.status_code < 400, f"{method} {path} 返回 {r.status_code}"


def test_new_company_defaults_to_pending(client):
    """F1：新建条目默认「审核中」，不得直接进检索。"""
    client.post(
        "/api/companies",
        json={"name": "默认值企业", "knowledge": "资料"},
        headers={"X-Admin-Token": TOKEN},
    )
    rows = [c for c in db.list_companies() if c["name"] == "默认值企业"]
    assert rows, "条目未写入"
    assert rows[0]["status"] == "审核中"


def test_public_chat_needs_no_token(client):
    """回归护栏：/api/chat 是公开接口，不应被鉴权误伤。"""
    import zhiqu.service as service

    client.app  # noqa: B018
    # 直接验证依赖未挂到 chat 上（避免真调模型）
    from zhiqu import api as api_mod

    chat_route = next(r for r in api_mod.app.routes if getattr(r, "path", "") == "/api/chat")
    assert not any(d.dependency is api_mod.require_admin for d in chat_route.dependant.dependencies)
    assert service.chat is not None  # 引用一次，避免 lint 未使用


# ---------------------------------------------------------------- F4
class _FakeAgent:
    def __init__(self, tag: str, delay: float) -> None:
        self.tag, self.delay = tag, delay

    def invoke(self, payload: dict) -> dict:
        time.sleep(self.delay)
        A.search_company_knowledge.invoke({"query": f"问题-{self.tag}"})
        time.sleep(self.delay)
        from langchain_core.messages import AIMessage

        return {"messages": [AIMessage(content=f"答复-{self.tag}")]}


def test_concurrent_answers_do_not_share_trace(monkeypatch):
    """F4：并发请求的检索来源不得互相污染。"""
    monkeypatch.setattr(
        A,
        "search",
        lambda q: [RetrievedChunk(text=f"{'甲' if '甲' in q else '乙'}的资料",
                                  company=("甲" if "甲" in q else "乙"), distance=0.1)],
    )

    results: dict[str, object] = {}

    def run(tag: str) -> None:
        A._build_agent = lambda model_name: _FakeAgent(  # type: ignore[assignment]
            "甲" if threading.current_thread().name == "T-甲" else "乙", 0.03
        )
        results[tag] = A.answer_question(f"问题-{tag}", session_id=f"s-{tag}")

    for _round in range(3):
        results.clear()
        t1 = threading.Thread(target=run, args=("甲",), name="T-甲")
        t2 = threading.Thread(target=run, args=("乙",), name="T-乙")
        t1.start()
        time.sleep(0.005)
        t2.start()
        t1.join()
        t2.join()

        for tag, r in results.items():
            assert set(r.sources) == {tag}, (  # type: ignore[attr-defined]
                f"第 {_round+1} 轮：请求[{tag}] 的来源被污染为 {r.sources}"  # type: ignore[attr-defined]
            )
            assert r.hit, f"第 {_round+1} 轮：请求[{tag}] 明明命中却被判兜底"  # type: ignore[attr-defined]


# ---------------------------------------------------------------- F2
class _FakeCol:
    def __init__(self) -> None:
        self.ids: list[str] = []
        self.docs: list[str] = []
        self.count_at_upsert: int | None = None

    def get(self):
        return {"ids": list(self.ids)}

    def delete(self, ids):
        self.ids, self.docs = [], []

    def upsert(self, ids, documents, embeddings, metadatas):
        # 关键断言点：执行 upsert 时，旧索引必须还在（不得为 0）
        self.count_at_upsert = self.count()
        self.ids, self.docs = list(ids), list(documents)

    def count(self) -> int:
        return len(self.ids)

    def query(self, query_embeddings, n_results):
        k = min(n_results, len(self.ids))
        return {
            "documents": [self.docs[:k]],
            "metadatas": [[{"company": "桩"} for _ in range(k)]],
            "distances": [[0.1] * k],
        }


class _FakeEmbedder:
    def encode(self, docs, normalize_embeddings=True):
        n = len(docs)

        class _R:
            def tolist(self_inner):
                return [[0.0] * 4 for _ in range(n)]

        return _R()


def test_rebuild_keeps_index_available(temp_db, monkeypatch):
    """F2：重建期间旧索引不得清空（消除空窗）。"""
    import zhiqu.vectorstore as V

    col = _FakeCol()
    monkeypatch.setattr(V, "_get_collection", lambda: col)
    monkeypatch.setattr(V, "_get_embedder", lambda: _FakeEmbedder())

    for i in range(5):
        db.upsert_company(db.Company(name=f"企业{i}", status="已发布", knowledge="资料。" * 10))

    V.rebuild_index()
    assert col.count() > 0, "首轮建库失败"

    db.upsert_company(db.Company(name="新增企业", status="已发布", knowledge="新资料。" * 5))
    V.rebuild_index()

    assert col.count_at_upsert and col.count_at_upsert > 0, (
        "upsert 时旧索引为 0 —— 空窗回归了（应先 upsert 再删陈旧）"
    )


# ---------------------------------------------------------------- 增量索引
class _CountingEmbedder:
    """记录累计编码块数，用于证明增量只嵌入该企业。"""

    def __init__(self) -> None:
        self.total = 0

    def encode(self, docs, normalize_embeddings=True):
        n = len(docs)
        self.total += n

        class _R:
            def tolist(self_inner):
                return [[0.0] * 4 for _ in range(n)]

        return _R()


def test_sync_company_embeds_only_that_company(temp_db, monkeypatch):
    """写入一条的代价应为 O(单条)，而非 O(全库)。"""
    import zhiqu.vectorstore as V

    col = _FakeCol()
    emb = _CountingEmbedder()
    monkeypatch.setattr(V, "_get_collection", lambda: col)
    monkeypatch.setattr(V, "_get_embedder", lambda: emb)

    for i in range(6):
        db.upsert_company(
            db.Company(name=f"企业{i}", status="已发布", knowledge="资料。" * 30)
        )
    V.rebuild_index()
    full_cost = emb.total
    assert full_cost >= 6, "全量建库应编码全部企业的块"

    target = int(db.list_companies()[0]["id"])
    emb.total = 0
    V.sync_company(target)

    assert emb.total < full_cost, (
        f"增量应远小于全量（本次 {emb.total} vs 全量 {full_cost}）"
    )


def test_sync_company_clears_chunks_when_unpublished(temp_db, monkeypatch):
    """改为「审核中」后，其块应被摘出检索面。"""
    import zhiqu.vectorstore as V

    col = _FakeCol()
    monkeypatch.setattr(V, "_get_collection", lambda: col)
    monkeypatch.setattr(V, "_get_embedder", lambda: _FakeEmbedder())

    db.upsert_company(db.Company(name="待审企业", status="已发布", knowledge="资料。" * 10))
    target = int(db.list_companies()[0]["id"])
    V.sync_company(target)
    assert col.count() > 0, "应先有块"

    db.upsert_company(db.Company(name="待审企业", status="审核中", knowledge="资料。" * 10))
    V.sync_company(target)
    assert col.count() == 0, "转审核中后旧块未被清除"


def test_remove_company_from_index(temp_db, monkeypatch):
    """删除企业时，其块应被整体移除。"""
    import zhiqu.vectorstore as V

    col = _FakeCol()
    monkeypatch.setattr(V, "_get_collection", lambda: col)
    monkeypatch.setattr(V, "_get_embedder", lambda: _FakeEmbedder())

    db.upsert_company(db.Company(name="待删企业", status="已发布", knowledge="资料。" * 10))
    target = int(db.list_companies()[0]["id"])
    V.sync_company(target)
    before = col.count()
    assert before > 0

    removed = V.remove_company_from_index(target)
    assert removed == before
    assert col.count() == 0
