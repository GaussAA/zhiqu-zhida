/** 对话日志审查页（设计页 03）：指标概览 + 日志表格 + 导出。 */

import { useCallback, useEffect, useState } from "react";
import { api, type ChatLogRow, type Metrics } from "../api";
import { Badge, Card, GhostButton, StatCard } from "../ui";

function pct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

export default function LogsPage() {
  const [logs, setLogs] = useState<ChatLogRow[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [ls, ms] = await Promise.all([api.logs(200), api.metrics()]);
      setLogs(ls);
      setMetrics(ms);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mb-5 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-[#18181B] dark:text-[#FAFAFA]">对话日志审查</h1>
        <div className="flex gap-2">
          <GhostButton onClick={() => void reload()}>刷新</GhostButton>
          <a href={api.exportUrl("csv")} download>
            <GhostButton>导出 CSV</GhostButton>
          </a>
          <a href={api.exportUrl("json")} download>
            <GhostButton>导出 JSON</GhostButton>
          </a>
        </div>
      </div>

      {metrics ? (
        <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-5">
          <StatCard label="总会话数" value={String(metrics.total_sessions)} />
          <StatCard label="总轮次" value={String(metrics.total_turns)} />
          <StatCard label="命中率" value={pct(metrics.hit_rate)} />
          <StatCard label="兜底率" value={pct(metrics.fallback_rate)} />
          <StatCard label="平均轮次" value={String(metrics.avg_turns)} />
        </div>
      ) : null}

      {error ? (
        <div className="mb-4 rounded-lg bg-[#D97706]/10 px-4 py-2 text-xs text-[#D97706] dark:text-[#FBBF24]">
          {error}
        </div>
      ) : null}

      <Card className="overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-black/8 text-xs text-[#71717A] dark:border-white/7 dark:text-[#A1A1AA]">
              <th className="px-4 py-3 font-medium">时间</th>
              <th className="px-4 py-3 font-medium">会话</th>
              <th className="px-4 py-3 font-medium">用户问题</th>
              <th className="px-4 py-3 font-medium">意图</th>
              <th className="px-4 py-3 font-medium">结果</th>
              <th className="px-4 py-3 font-medium">来源</th>
              <th className="px-4 py-3 font-medium text-right">耗时</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((l) => (
              <tr
                key={l.id}
                className="border-b border-black/8 last:border-0 dark:border-white/7"
              >
                <td className="whitespace-nowrap px-4 py-3 text-xs text-[#71717A] dark:text-[#A1A1AA]">
                  {l.created_at.replace("T", " ").slice(5, 19)}
                </td>
                <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-[#71717A] dark:text-[#A1A1AA]">
                  {l.session_id.slice(0, 8)}#{l.turn}
                </td>
                <td className="max-w-[280px] truncate px-4 py-3 text-[#18181B] dark:text-[#FAFAFA]">
                  {l.question}
                </td>
                <td className="px-4 py-3">
                  <Badge tone="blue">{l.intent}</Badge>
                </td>
                <td className="px-4 py-3">
                  {l.hit ? <Badge tone="green">命中</Badge> : null}
                  {l.fallback ? <Badge tone="amber">兜底</Badge> : null}
                  {!l.hit && !l.fallback ? <Badge tone="gray">直答</Badge> : null}
                </td>
                <td className="max-w-[140px] truncate px-4 py-3 text-xs text-[#71717A] dark:text-[#A1A1AA]">
                  {l.sources || "—"}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-right text-xs text-[#71717A] dark:text-[#A1A1AA]">
                  {l.latency_ms}ms
                </td>
              </tr>
            ))}
            {logs.length === 0 ? (
              <tr>
                <td
                  colSpan={7}
                  className="px-4 py-12 text-center text-sm text-[#71717A] dark:text-[#A1A1AA]"
                >
                  暂无会话日志，先去对话页试试吧
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
