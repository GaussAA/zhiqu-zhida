"""M3 验证脚本：意图识别 + 兜底标记 + 多轮上下文。

用例：
1. 闲聊       -> intent=闲聊，不检索，无兜底
2. 企业咨询   -> intent=企业咨询，命中 + 来源
3. 库外问题   -> 检索不命中 -> 兜底标记
4. 多轮追问   -> 第二轮用代词「它」，靠上下文解析
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")

from zhiqu.agent import answer_question  # noqa: E402
from zhiqu.seed import run_seed  # noqa: E402
from zhiqu.vectorstore import rebuild_index  # noqa: E402


def show(tag: str, r: object) -> None:
    from zhiqu.agent import AgentAnswer

    assert isinstance(r, AgentAnswer)
    print(f"[{tag}] {r.question}")
    print(f"  💬 {r.answer[:120]}{'…' if len(r.answer) > 120 else ''}")
    print(
        f"  意图={r.intent} 命中={r.hit} 兜底={r.fallback} "
        f"来源={r.sources or '-'} 模型={r.model} 耗时={r.latency_ms}ms\n"
    )


def main() -> None:
    run_seed()
    rebuild_index()
    print("=== M3 验证开始 ===\n")

    r1 = answer_question("你好呀")
    show("闲聊", r1)

    r2 = answer_question("百度在自动驾驶方面有什么布局？")
    show("企业咨询", r2)

    r3 = answer_question("今天上海天气怎么样？")
    show("库外/其他", r3)

    sid = "multi-turn-demo"
    ra = answer_question("阿里巴巴的电商平台有哪些？", session_id=sid)
    show("多轮-第1轮", ra)
    history = [
        {"role": "user", "content": ra.question},
        {"role": "assistant", "content": ra.answer},
    ]
    rb = answer_question("它的云计算业务呢？", session_id=sid, history=history)
    show("多轮-第2轮(代词)", rb)

    checks = [
        ("闲聊意图正确", r1.intent == "闲聊" and not r1.fallback),
        ("企业咨询命中", r2.hit and "百度" in r2.sources),
        ("库外问题兜底", r3.fallback and not r3.hit),
        ("多轮第2轮命中阿里", rb.hit and "阿里巴巴集团" in rb.sources),
    ]
    print("=== 断言结果 ===")
    ok = True
    for name, passed in checks:
        print(f"  {'✅' if passed else '❌'} {name}")
        ok = ok and passed
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
