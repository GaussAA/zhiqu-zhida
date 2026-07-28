"""M6 端到端验证：第一轮猎 bug + 第二轮回归复用。

覆盖：健康检查 / 单轮命中 / 闲聊 / 库外兜底 / 多轮指代 / 知识库增删后检索 /
指标字段 / 日志导出。
每步打印详细结果并软断言（不中断），最后汇总 PASS/FAIL。
"""

from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

BASE = "http://127.0.0.1:8720"
HEADERS = {"Content-Type": "application/json"}

results: list[tuple[str, bool, str]] = []


def _post(path: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + path, data=data, headers=HEADERS, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8", "replace"))


def _get(path: str) -> tuple[int, object]:
    req = urllib.request.Request(BASE + path, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            if "application/json" in ctype:
                return resp.status, json.loads(raw.decode("utf-8"))
            return resp.status, raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _delete(path: str) -> tuple[int, object]:
    req = urllib.request.Request(BASE + path, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, cond, detail))
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))


def chat(question: str, session_id: str | None = None) -> dict:
    st, body = _post("/api/chat", {"question": question, "session_id": session_id})
    assert st == 200, f"chat HTTP {st}: {body}"
    return body


def main() -> int:
    print("=" * 60)
    print("知企智答 端到端验证")
    print("=" * 60)

    # 1. 健康检查
    st, m = _get("/api/metrics")
    check("健康检查 /api/metrics", st == 200, f"status={st}")

    # 2. 单轮命中（腾讯）
    r = chat("腾讯的主营业务有哪些？")
    check("单轮命中·腾讯", r["hit"] and "腾讯控股" in r["sources"],
          f"hit={r['hit']} sources={r['sources']} intent={r['intent']}")

    # 3. 闲聊
    r = chat("你好呀")
    check("闲聊直答不检索", r["intent"] == "闲聊" and not r["hit"],
          f"intent={r['intent']} hit={r['hit']}")

    # 4. 库外兜底
    r = chat("茅台股价现在多少？")
    check("库外兜底", r["fallback"] and not r["hit"],
          f"fallback={r['fallback']} hit={r['hit']}")

    # 5. 多轮指代（同一 session）
    sid = "e2e_session_1"
    r1 = chat("腾讯是哪年成立的？", session_id=sid)
    r2 = chat("它的云计算业务呢？", session_id=sid)
    check("多轮指代命中", r2["hit"] and "腾讯控股" in r2["sources"],
          f"q1_hit={r1['hit']} q2_hit={r2['hit']} q2_sources={r2['sources']}")

    # 6. 知识库新增美团
    st, b = _post("/api/companies", {
        "name": "美团",
        "ticker": "3690.HK",
        "business": "本地生活服务",
        "industry": "生活服务电商",
        "status": "已发布",
        "knowledge": "美团是中国领先的生活服务电子商务平台，主营外卖配送、到店餐饮、酒店旅游及美团买菜等业务。",
    })
    check("新增企业·美团", st == 200 and "id" in b, f"status={st} body={b}")

    # 7. 检索新增企业
    r = chat("美团主要做哪些业务？")
    check("新增后可检索·美团", r["hit"] and "美团" in r["sources"],
          f"hit={r['hit']} sources={r['sources']}")

    # 8. 删除美团
    meituan_id = b.get("id")
    st, b = _delete(f"/api/companies/{meituan_id}")
    check("删除企业·美团", st == 200, f"status={st} body={b}")

    # 9. 删除后兜底（索引应已移除美团）
    r = chat("美团市值多少？")
    check("删除后兜底·美团", r["fallback"] and not r["hit"],
          f"fallback={r['fallback']} hit={r['hit']} sources={r['sources']}")

    # 10. 指标字段完整
    st, m = _get("/api/metrics")
    expected = {"total_sessions", "total_turns", "hit_rate", "fallback_rate", "avg_turns"}
    ok = st == 200 and expected.issubset(set(m.keys()))
    check("指标字段完整", ok, f"keys={sorted(m.keys()) if isinstance(m, dict) else m}")

    # 11. 导出 CSV
    st, csv_text = _get("/api/logs/export?fmt=csv")
    ok = st == 200 and isinstance(csv_text, str) and "session_id" in csv_text
    check("导出 CSV", ok, f"status={st} len={len(csv_text) if isinstance(csv_text, str) else 0}")

    # 12. 导出 JSON
    st, js = _get("/api/logs/export?fmt=json")
    ok = st == 200 and isinstance(js, list) and len(js) > 0
    check("导出 JSON", ok, f"status={st} rows={len(js) if isinstance(js, list) else 0}")

    # 汇总
    print("\n" + "=" * 60)
    print("汇总")
    print("=" * 60)
    passed = sum(1 for _, c, _ in results if c)
    total = len(results)
    for name, cond, detail in results:
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    print(f"\n{passed}/{total} 通过")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
