/** API 客户端：统一 fetch 封装 + 强类型响应。 */

export interface ChatResponse {
  session_id: string;
  answer: string;
  intent: string;
  hit: boolean;
  fallback: boolean;
  sources: string[];
  model: string;
  latency_ms: number;
}

export interface Company {
  id: number;
  name: string;
  ticker: string;
  business: string;
  industry: string;
  status: "已发布" | "审核中";
  knowledge: string;
  created_at: string;
  updated_at: string;
}

export interface CompanyStats {
  total: number;
  published: number;
  pending: number;
  industries: Record<string, number>;
}

export interface ChatLogRow {
  id: number;
  session_id: string;
  turn: number;
  question: string;
  answer: string;
  intent: string;
  hit: number;
  fallback: number;
  sources: string;
  latency_ms: number;
  created_at: string;
}

export interface Metrics {
  total_sessions: number;
  total_turns: number;
  hit_rate: number;
  fallback_rate: number;
  avg_turns: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}

export const api = {
  chat: (question: string, sessionId: string | null) =>
    request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ question, session_id: sessionId }),
    }),
  listCompanies: (industry?: string, status?: string) => {
    const p = new URLSearchParams();
    if (industry) p.set("industry", industry);
    if (status) p.set("status", status);
    const q = p.toString();
    return request<Company[]>(`/api/companies${q ? `?${q}` : ""}`);
  },
  saveCompany: (c: Omit<Company, "id" | "created_at" | "updated_at">) =>
    request<{ id: number; indexed_chunks: number }>("/api/companies", {
      method: "POST",
      body: JSON.stringify(c),
    }),
  deleteCompany: (id: number) =>
    request<{ deleted: number }>(`/api/companies/${id}`, { method: "DELETE" }),
  companyStats: () => request<CompanyStats>("/api/companies/stats"),
  logs: (limit = 200) => request<ChatLogRow[]>(`/api/logs?limit=${limit}`),
  metrics: () => request<Metrics>("/api/metrics"),
  exportUrl: (fmt: "csv" | "json") => `/api/logs/export?fmt=${fmt}`,
};
