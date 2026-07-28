"""M2 验证脚本：种子建库 -> 向量索引 -> 单轮 RAG 问答。

用法：
    uv run python scripts/demo_cli.py "腾讯的主营业务是什么？"
    uv run python scripts/demo_cli.py            # 跑默认验证问题集
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

from zhiqu.agent import answer_question  # noqa: E402
from zhiqu.seed import run_seed  # noqa: E402
from zhiqu.vectorstore import rebuild_index  # noqa: E402

DEFAULT_QUESTIONS = [
    "腾讯的主营业务是什么？",
    "字节跳动上市了吗？",
]


def main() -> None:
    run_seed()
    n = rebuild_index()
    print(f"\n=== 向量索引就绪：{n} 块 ===\n")

    questions = sys.argv[1:] or DEFAULT_QUESTIONS
    for q in questions:
        print(f"❓ {q}")
        r = answer_question(q)
        print(f"💬 {r.answer}")
        print(
            f"   [意图={r.intent} 命中={r.hit} 兜底={r.fallback} "
            f"来源={r.sources or '-'} 模型={r.model} 耗时={r.latency_ms}ms]\n"
        )


if __name__ == "__main__":
    main()
