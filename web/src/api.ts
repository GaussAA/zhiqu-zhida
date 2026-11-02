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

/** 管理口令：仅存 sessionStorage（关标签即失效），不落构建产物。 */
const TOKEN_KEY = "zhiqu.adminToken";

export function getAdminToken(): string {
  try {
    return sessionStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setAdminToken(value: string): void {
  try {
    if (value) sessionStorage.setItem(TOKEN_KEY, value);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // 隐私模式下 sessionStorage 可能不可用：忽略，请求将得到 403
  }
}

/** 带状态码的错误，便于页面区分「未授权」与其他失败。 */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function authHeaders(): Record<string, string> {
  const token = getAdminToken();
  return token ? { "X-Admin-Token": token } : {};
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, `API ${res.status}: ${body.slice(0, 200)}`);
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
  /** 导出走 fetch + Blob：<a href> 导航无法携带 X-Admin-Token。 */
  exportLogs: async (fmt: "csv" | "json"): Promise<Blob> => {
    const res = await fetch(`/api/logs/export?fmt=${fmt}`, { headers: authHeaders() });
    if (!res.ok) throw new ApiError(res.status, `导出失败：HTTP ${res.status}`);
    return await res.blob();
  },
};
