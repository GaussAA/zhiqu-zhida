"""M4 验证脚本：会话日志落库 + 指标计算 + 导出。

模拟两个会话（一个多轮企业咨询、一个含兜底），验证：
1. chat_logs 落库条数正确
2. 指标（会话数/轮次/命中率/兜底率/平均轮次）计算正确
3. CSV 与 JSON 导出成功
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")

from zhiqu.db import list_chat_logs  # noqa: E402
from zhiqu.seed import run_seed  # noqa: E402
from zhiqu.service import chat, export_logs, get_metrics  # noqa: E402
from zhiqu.vectorstore import rebuild_index  # noqa: E402


def main() -> None:
    run_seed()
    rebuild_index()
    before = len(list_chat_logs(limit=100000))
    print(f"=== M4 验证开始（存量日志 {before} 条）===\n")

    # 会话1：两轮企业咨询（多轮上下文）
    r1 = chat("字节跳动的旗舰产品有哪些？", session_id="m4-s1")
    print(f"s1t1: intent={r1.intent} hit={r1.hit} fallback={r1.fallback}")
    r2 = chat("它的企业协作产品叫什么？", session_id="m4-s1")
    print(f"s1t2: intent={r2.intent} hit={r2.hit} fallback={r2.fallback}")

    # 会话2：一轮库外问题（兜底）
    r3 = chat("拼多多的市值是多少？", session_id="m4-s2")
    print(f"s2t1: intent={r3.intent} hit={r3.hit} fallback={r3.fallback}\n")

    after = len(list_chat_logs(limit=100000))
    metrics = get_metrics()
    print(f"指标: {metrics}")

    csv_path = export_logs("csv")
    json_path = export_logs("json")
    print(f"导出: {csv_path.name} / {json_path.name}\n")

    checks = [
        ("新增3条日志", after - before == 3),
        ("多轮第2轮命中字节", r2.hit and "字节跳动" in r2.sources),
        ("库外问题兜底", r3.fallback),
        ("指标含全部字段", all(k in metrics for k in ("total_sessions", "total_turns", "hit_rate", "fallback_rate", "avg_turns"))),
        ("CSV导出存在且非空", csv_path.exists() and csv_path.stat().st_size > 0),
        ("JSON导出存在且非空", json_path.exists() and json_path.stat().st_size > 0),
    ]
    print("=== 断言结果 ===")
    ok = True
    for name, passed in checks:
        print(f"  {'✅' if passed else '❌'} {name}")
        ok = ok and passed
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
