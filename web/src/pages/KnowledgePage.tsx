/** 知识库管理后台（设计页 02）：统计概览 + 筛选 + 企业列表 + 录入表单。 */

import { useCallback, useEffect, useState } from "react";
import { api, type Company, type CompanyStats } from "../api";
import { Badge, Card, GhostButton, PrimaryButton, StatCard } from "../ui";

interface CompanyForm {
  name: string;
  ticker: string;
  business: string;
  industry: string;
  status: "已发布" | "审核中";
  knowledge: string;
}

const EMPTY_FORM: CompanyForm = {
  name: "",
  ticker: "",
  business: "",
  industry: "",
  status: "已发布",
  knowledge: "",
};

export default function KnowledgePage() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [stats, setStats] = useState<CompanyStats | null>(null);
  const [industry, setIndustry] = useState("");
  const [status, setStatus] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<CompanyForm>(EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [list, st] = await Promise.all([
        api.listCompanies(industry || undefined, status || undefined),
        api.companyStats(),
      ]);
      setCompanies(list);
      setStats(st);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    }
  }, [industry, status]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function save() {
    if (!form.name.trim()) {
      setError("企业名称不能为空");
      return;
    }
    setBusy(true);
    try {
      await api.saveCompany(form);
      setForm(EMPTY_FORM);
      setShowForm(false);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number, name: string) {
    if (!window.confirm(`确认删除「${name}」？删除后将重建向量索引。`)) return;
    setBusy(true);
    try {
      await api.deleteCompany(id);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败");
    } finally {
      setBusy(false);
    }
  }

  const industries = stats ? Object.keys(stats.industries) : [];

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mb-5 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-[#18181B] dark:text-[#FAFAFA]">知识库管理</h1>
        <PrimaryButton onClick={() => setShowForm((v) => !v)}>
          {showForm ? "收起表单" : "新增企业"}
        </PrimaryButton>
      </div>

      {stats ? (
        <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatCard label="企业总数" value={String(stats.total)} />
          <StatCard label="已发布" value={String(stats.published)} />
          <StatCard label="审核中" value={String(stats.pending)} />
          <StatCard label="行业数" value={String(industries.length)} />
        </div>
      ) : null}

      {showForm ? (
        <Card className="mb-5 p-5">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {(
              [
                ["name", "企业名称 *"],
                ["ticker", "股票代码"],
                ["business", "主营业务"],
                ["industry", "行业"],
              ] as const
            ).map(([key, label]) => (
              <label key={key} className="text-xs text-[#71717A] dark:text-[#A1A1AA]">
                {label}
                <input
                  value={form[key]}
                  onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                  className="mt-1 w-full rounded-lg border border-black/8 bg-white px-3 py-2 text-sm text-[#18181B] outline-none focus:border-[#2563EB]/40 dark:border-white/7 dark:bg-[#09090B] dark:text-[#FAFAFA] dark:focus:border-[#60A5FA]/40"
                />
              </label>
            ))}
            <label className="text-xs text-[#71717A] dark:text-[#A1A1AA]">
              状态
              <select
                value={form.status}
                onChange={(e) =>
                  setForm((f) => ({ ...f, status: e.target.value as "已发布" | "审核中" }))
                }
                className="mt-1 w-full rounded-lg border border-black/8 bg-white px-3 py-2 text-sm text-[#18181B] outline-none dark:border-white/7 dark:bg-[#09090B] dark:text-[#FAFAFA]"
              >
                <option value="已发布">已发布</option>
                <option value="审核中">审核中</option>
              </select>
            </label>
            <label className="text-xs text-[#71717A] dark:text-[#A1A1AA] md:col-span-2">
              知识文本（用于向量检索）
              <textarea
                value={form.knowledge}
                onChange={(e) => setForm((f) => ({ ...f, knowledge: e.target.value }))}
                rows={5}
                className="mt-1 w-full rounded-lg border border-black/8 bg-white px-3 py-2 text-sm text-[#18181B] outline-none focus:border-[#2563EB]/40 dark:border-white/7 dark:bg-[#09090B] dark:text-[#FAFAFA] dark:focus:border-[#60A5FA]/40"
              />
            </label>
          </div>
          <div className="mt-4">
            <PrimaryButton onClick={() => void save()} disabled={busy}>
              {busy ? "保存中…" : "保存并重建索引"}
            </PrimaryButton>
          </div>
        </Card>
      ) : null}

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <span className="text-xs text-[#71717A] dark:text-[#A1A1AA]">行业：</span>
        <GhostButton active={industry === ""} onClick={() => setIndustry("")}>全部</GhostButton>
        {industries.map((ind) => (
          <GhostButton key={ind} active={industry === ind} onClick={() => setIndustry(ind)}>
            {ind}
          </GhostButton>
        ))}
        <span className="ml-4 text-xs text-[#71717A] dark:text-[#A1A1AA]">状态：</span>
        {["", "已发布", "审核中"].map((s) => (
          <GhostButton key={s || "all"} active={status === s} onClick={() => setStatus(s)}>
            {s || "全部"}
          </GhostButton>
        ))}
      </div>

      {error ? (
        <div className="mb-4 rounded-lg bg-[#D97706]/10 px-4 py-2 text-xs text-[#D97706] dark:text-[#FBBF24]">
          {error}
        </div>
      ) : null}

      <div className="space-y-3">
        {companies.map((c) => (
          <Card key={c.id} className="p-4">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-[#18181B] dark:text-[#FAFAFA]">
                    {c.name}
                  </span>
                  <span className="text-xs text-[#71717A] dark:text-[#A1A1AA]">{c.ticker}</span>
                  <Badge tone="blue">{c.industry}</Badge>
                  <Badge tone={c.status === "已发布" ? "green" : "amber"}>{c.status}</Badge>
                </div>
                <div className="mt-1 text-xs text-[#71717A] dark:text-[#A1A1AA]">
                  主营：{c.business}
                </div>
                <div className="mt-2 line-clamp-2 text-xs leading-relaxed text-[#71717A] dark:text-[#A1A1AA]">
                  {c.knowledge}
                </div>
              </div>
              <button
                type="button"
                onClick={() => void remove(c.id, c.name)}
                className="shrink-0 rounded-lg border border-black/8 px-3 py-1.5 text-xs text-[#71717A] transition-colors hover:border-[#D97706]/40 hover:text-[#D97706] dark:border-white/7 dark:text-[#A1A1AA] dark:hover:text-[#FBBF24]"
              >
                删除
              </button>
            </div>
          </Card>
        ))}
        {companies.length === 0 ? (
          <div className="py-12 text-center text-sm text-[#71717A] dark:text-[#A1A1AA]">
            暂无符合条件的企业条目
          </div>
        ) : null}
      </div>
    </div>
  );
}
