"""M7 评估报告生成器。

内置评估样本（问题 + 期望意图 / 是否应命中 / 期望来源 / 是否应兜底），
调用本地 /api/chat 跑系统，逐项比对，计算：
  - 意图分类准确率
  - 来源归因准确率（命中时 sources 是否含期望企业）
  - 命中正确率 / 兜底正确率
  - 平均耗时
并渲染为 data/reports/eval_report_YYYYMMDD.html（指标卡 + 明细表 + 分布图）。

用法：uv run python scripts/evaluate.py
"""

from __future__ import annotations

import html
import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

BASE = "http://127.0.0.1:8720"
HEADERS = {"Content-Type": "application/json"}
OUT_DIR = Path("data/reports")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 评估样本：每种类型覆盖，且跨多企业（含新增的 10 家）
SAMPLES: list[dict] = [
    # 单轮命中（跨企业）
    {"q": "腾讯的主营业务有哪些？", "intent": "企业咨询", "hit": True, "fallback": False, "source": "腾讯控股"},
    {"q": "阿里巴巴的云计算业务叫什么？", "intent": "企业咨询", "hit": True, "fallback": False, "source": "阿里巴巴集团"},
    {"q": "字节跳动旗下有哪些短视频产品？", "intent": "企业咨询", "hit": True, "fallback": False, "source": "字节跳动"},
    {"q": "百度推出了哪款大模型？", "intent": "企业咨询", "hit": True, "fallback": False, "source": "百度"},
    {"q": "美团外卖的市场地位如何？", "intent": "企业咨询", "hit": True, "fallback": False, "source": "美团"},
    {"q": "京东的自建物流有什么特点？", "intent": "企业咨询", "hit": True, "fallback": False, "source": "京东"},
    {"q": "拼多多的跨境出海平台叫什么？", "intent": "企业咨询", "hit": True, "fallback": False, "source": "拼多多"},
    {"q": "网易的核心业务是什么？", "intent": "企业咨询", "hit": True, "fallback": False, "source": "网易"},
    {"q": "小米现在做汽车吗？", "intent": "企业咨询", "hit": True, "fallback": False, "source": "小米集团"},
    {"q": "快手的电商模式有什么特点？", "intent": "企业咨询", "hit": True, "fallback": False, "source": "快手"},
    # 多轮指代
    {"q": "腾讯是哪年成立的？", "intent": "企业咨询", "hit": True, "fallback": False, "source": "腾讯控股", "session": "eval_s1"},
    {"q": "它的游戏业务怎么样？", "intent": "企业咨询", "hit": True, "fallback": False, "source": "腾讯控股", "session": "eval_s1"},
    # 闲聊（不应检索）
    {"q": "你好呀，在吗？", "intent": "闲聊", "hit": False, "fallback": False, "source": None},
    {"q": "今天天气不错", "intent": "闲聊", "hit": False, "fallback": False, "source": None},
    # 库外兜底（应兜底，不命中任何企业）
    # 注：茅台是真实公司、且问「股价」属财务类 -> 按本系统意图定义（财务/历史/产品…均归企业咨询）
    # 应判「企业咨询」；其不在知识库内，故仍走兜底（fallback=True, hit=False），验证「库外企业查询正确兜底」。
    {"q": "茅台股价现在多少？", "intent": "企业咨询", "hit": False, "fallback": True, "source": None},
    {"q": "怎么用 Python 写一个快排？", "intent": "其他", "hit": False, "fallback": True, "source": None},
]


def _post(path: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run() -> dict:
    rows: list[dict] = []
    for s in SAMPLES:
        try:
            r = _post("/api/chat", {"question": s["q"], "session_id": s.get("session")})
        except urllib.error.HTTPError as e:
            r = {"answer": f"HTTP {e.code}", "intent": "", "hit": False,
                 "fallback": False, "sources": [], "model": "err", "latency_ms": 0}
        intent_ok = (r.get("intent") == s["intent"])
        hit_ok = (bool(r.get("hit")) == s["hit"])
        fallback_ok = (bool(r.get("fallback")) == s["fallback"])
        src_ok = True
        if s["source"]:
            src_ok = s["source"] in (r.get("sources") or [])
        # 综合正确：意图 + 命中 + 兜底 + (来源若期望)
        overall = intent_ok and hit_ok and fallback_ok and src_ok
        rows.append({
            "q": s["q"], "exp_intent": s["intent"], "intent": r.get("intent"),
            "intent_ok": intent_ok, "exp_hit": s["hit"], "hit": r.get("hit"),
            "hit_ok": hit_ok, "exp_fallback": s["fallback"], "fallback": r.get("fallback"),
            "fallback_ok": fallback_ok, "exp_source": s["source"], "sources": r.get("sources"),
            "src_ok": src_ok, "overall": overall, "model": r.get("model"),
            "latency_ms": r.get("latency_ms"),
        })
    n = len(rows)
    def rate(key: str) -> float:
        return round(sum(1 for x in rows if x[key]) / n, 4) if n else 0.0
    return {
        "rows": rows,
        "n": n,
        "intent_acc": rate("intent_ok"),
        "hit_acc": rate("hit_ok"),
        "fallback_acc": rate("fallback_ok"),
        "source_acc": rate("src_ok"),
        "overall_acc": rate("overall"),
        "avg_latency": round(sum(x["latency_ms"] for x in rows) / n, 1) if n else 0,
        "hit_n": sum(1 for x in rows if x["hit"]),
        "fallback_n": sum(1 for x in rows if x["fallback"]),
        "chitchat_n": sum(1 for x in rows if x["intent"] == "闲聊"),
    }


def _bar(ratio: float, color: str) -> str:
    pct = int(ratio * 100)
    return (f'<div style="background:#E5E7EB;border-radius:6px;height:10px;width:120px;display:inline-block;vertical-align:middle">'
            f'<div style="background:{color};height:10px;border-radius:6px;width:{pct}%"></div></div>'
            f'<span style="margin-left:8px;font-variant-numeric:tabular-nums">{pct}%</span>')


def render(m: dict) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cards = [
        ("评估样本", str(m["n"]), "#2563EB"),
        ("综合准确率", f'{int(m["overall_acc"]*100)}%', "#16A34A"),
        ("意图准确率", f'{int(m["intent_acc"]*100)}%', "#2563EB"),
        ("来源归因准确率", f'{int(m["source_acc"]*100)}%', "#D97706"),
        ("命中/兜底正确率", f'{int(m["hit_acc"]*100)}% / {int(m["fallback_acc"]*100)}%', "#7C3AED"),
        ("平均耗时", f'{m["avg_latency"]} ms', "#0EA5E9"),
    ]
    card_html = "".join(
        f'<div style="background:#fff;border:1px solid #E5E7EB;border-radius:12px;padding:16px;min-width:160px">'
        f'<div style="font-size:12px;color:#6B7280">{label}</div>'
        f'<div style="font-size:22px;font-weight:700;color:{color};margin-top:6px">{val}</div></div>'
        for label, val, color in cards
    )
    rows_html = ""
    for x in m["rows"]:
        status = "✅" if x["overall"] else "❌"
        src_disp = ", ".join(x["sources"]) if x["sources"] else "—"
        cls = "background:#F0FDF4" if x["overall"] else "background:#FEF2F2"
        rows_html += (
            f'<tr style="{cls}">'
            f'<td style="padding:8px 10px;border-bottom:1px solid #F1F5F9">{html.escape(x["q"])}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid #F1F5F9">{status}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid #F1F5F9">{x["exp_intent"]}→{x["intent"]}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid #F1F5F9">{"命中" if x["exp_hit"] else "不命中"}→{"命中" if x["hit"] else "未命中"}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid #F1F5F9">{x["exp_source"] or "—"}→{html.escape(src_disp)}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid #F1F5F9">{x["model"]}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid #F1F5F9;text-align:right">{x["latency_ms"]}</td>'
            f'</tr>'
        )
    total = m["n"]
    hit_pct = int(m["hit_n"] / total * 100) if total else 0
    fb_pct = int(m["fallback_n"] / total * 100) if total else 0
    chit_pct = 100 - hit_pct - fb_pct
    dist_chart = (
        f'<div style="display:flex;height:24px;border-radius:6px;overflow:hidden;margin-top:8px">'
        f'<div style="width:{chit_pct}%;background:#2563EB" title="企业咨询命中之外"></div>'
        f'<div style="width:{hit_pct}%;background:#16A34A" title="命中"></div>'
        f'<div style="width:{fb_pct}%;background:#D97706" title="兜底"></div></div>'
        f'<div style="font-size:12px;color:#6B7280;margin-top:6px">命中 {m["hit_n"]} · 兜底 {m["fallback_n"]} · 闲聊 {m["chitchat_n"]}</div>'
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>知企智答 · 评估报告</title>
<style>
  body{{font-family:-apple-system,'Segoe UI',Roboto,'PingFang SC','Microsoft YaHei',sans-serif;
        background:#F8FAFC;color:#0F172A;margin:0;padding:32px}}
  .wrap{{max-width:1080px;margin:0 auto}}
  h1{{font-size:24px;margin:0 0 4px}}
  .sub{{color:#64748B;font-size:13px;margin-bottom:24px}}
  .cards{{display:flex;flex-wrap:wrap;gap:14px;margin-bottom:28px}}
  .sec{{background:#fff;border:1px solid #E5E7EB;border-radius:12px;padding:20px;margin-bottom:20px}}
  h2{{font-size:16px;margin:0 0 14px}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{text-align:left;color:#64748B;font-weight:600;padding:8px 10px;border-bottom:2px solid #E5E7EB}}
</style></head>
<body><div class="wrap">
  <h1>知企智答 · RAG 系统评估报告</h1>
  <div class="sub">生成时间 {now} · 评估样本 {total} 条 · 端点 {BASE}/api/chat</div>
  <div class="cards">{card_html}</div>
  <div class="sec">
    <h2>整体分布（命中 / 兜底 / 闲聊）</h2>
    {dist_chart}
  </div>
  <div class="sec">
    <h2>逐条明细</h2>
    <table>
      <tr><th>问题</th><th>结果</th><th>意图(期望→实际)</th><th>命中(期望→实际)</th>
          <th>来源(期望→实际)</th><th>模型</th><th style="text-align:right">耗时(ms)</th></tr>
      {rows_html}
    </table>
  </div>
  <div class="sub" style="text-align:center">知企智答 Agent 系统 · 评估报告（自动化生成）</div>
</div></body></html>"""


def main() -> int:
    print("运行评估中（调用本地 /api/chat）...")
    m = run()
    html_out = render(m)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUT_DIR / f"eval_report_{stamp}.html"
    path.write_text(html_out, encoding="utf-8")
    print(f"样本数={m['n']} 综合准确率={m['overall_acc']*100:.1f}% "
          f"意图={m['intent_acc']*100:.1f}% 来源={m['source_acc']*100:.1f}% "
          f"命中正确={m['hit_acc']*100:.1f}% 兜底正确={m['fallback_acc']*100:.1f}% "
          f"平均耗时={m['avg_latency']}ms")
    print(f"报告已生成: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
