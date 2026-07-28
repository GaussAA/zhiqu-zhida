"""M6 边界猎 bug：破坏性边界用例。

验证：空/超长输入校验(422)、删不存在(404)、审核中企业不进检索、
多轮堆叠后指代仍命中、指标比率合法。
"""

from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8720"
HEADERS = {"Content-Type": "application/json"}
results: list[tuple[str, bool, str]] = []


def _post(path: str, payload: dict) -> tuple[int, object]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, headers=HEADERS, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _get(path: str) -> tuple[int, object]:
    req = urllib.request.Request(BASE + path, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
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
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def chat(question: str, session_id: str | None = None) -> dict:
    st, body = _post("/api/chat", {"question": question, "session_id": session_id})
    assert st == 200, f"chat HTTP {st}: {body}"
    return body


def main() -> int:
    print("=" * 60)
    print("知企智答 边界猎 bug")
    print("=" * 60)

    # 1. 空问题 -> 422
    st, _ = _post("/api/chat", {"question": ""})
    check("空问题拒绝(422)", st == 422, f"status={st}")

    # 2. 超长问题(>500) -> 422
    st, _ = _post("/api/chat", {"question": "腾讯" * 300})
    check("超长问题拒绝(422)", st == 422, f"status={st}")

    # 3. 删除不存在 -> 404
    st, _ = _delete("/api/companies/999999")
    check("删除不存在(404)", st == 404, f"status={st}")

    # 4. 审核中企业不进检索
    st, b = _post("/api/companies", {
        "name": "边界测试企业",
        "ticker": "TEST.X",
        "business": "测试",
        "industry": "测试行业",
        "status": "审核中",
        "knowledge": "这是一条仅用于验证审核中状态不进入检索索引的测试知识。",
    })
    check("新增审核中企业", st == 200, f"status={st}")
    rid = b.get("id")
    r = chat("边界测试企业的主营业务是什么？")
    check("审核中不检索(兜底)", (not r["hit"]) and r["fallback"],
          f"hit={r['hit']} fallback={r['fallback']}")
    if rid:
        _delete(f"/api/companies/{rid}")

    # 5. 指标比率合法
    st, m = _get("/api/metrics")
    ok = st == 200 and isinstance(m, dict) and 0.0 <= float(m["hit_rate"]) <= 1.0 \
        and 0.0 <= float(m["fallback_rate"]) <= 1.0
    check("指标比率合法[0,1]", ok, f"{m}")

    # 6. 多轮堆叠(>6轮)后指代仍命中
    sid = "edge_session_2"
    for i in range(7):
        chat(f"第{i}轮：腾讯有哪些产品？", session_id=sid)
    r = chat("它的云计算业务怎么样？", session_id=sid)
    check("多轮堆叠仍命中", r["hit"], f"hit={r['hit']} sources={r['sources']}")

    print("\n" + "=" * 60)
    passed = sum(1 for _, c, _ in results if c)
    total = len(results)
    for name, cond, detail in results:
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    print(f"\n{passed}/{total} 通过")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
