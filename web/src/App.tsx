/** 应用外壳：侧栏导航 + 顶栏（主题切换） + 三页路由。 */

import { useState, type ReactNode } from "react";
import ChatPage from "./pages/ChatPage";
import KnowledgePage from "./pages/KnowledgePage";
import LogsPage from "./pages/LogsPage";
import { useTheme } from "./theme";

type PageKey = "chat" | "kb" | "logs";

const PAGES: { key: PageKey; label: string; render: () => ReactNode }[] = [
  { key: "chat", label: "智能对话", render: () => <ChatPage /> },
  { key: "kb", label: "知识库管理", render: () => <KnowledgePage /> },
  { key: "logs", label: "日志审查", render: () => <LogsPage /> },
];

const PAGE_TITLES: Record<PageKey, string> = {
  chat: "智能对话",
  kb: "知识库管理",
  logs: "对话日志审查",
};

export default function App() {
  const [page, setPage] = useState<PageKey>("chat");
  const { dark, toggle } = useTheme();

  const active = PAGES.find((p) => p.key === page) ?? PAGES[0];

  return (
    <div className="flex h-full bg-[#FAFAFA] text-[#18181B] dark:bg-[#09090B] dark:text-[#FAFAFA]">
      <aside className="flex w-52 shrink-0 flex-col border-r border-black/8 dark:border-white/7">
        <div className="flex items-center gap-2 px-5 py-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#2563EB] text-sm font-semibold text-white dark:bg-[#60A5FA] dark:text-[#09090B]">
            知
          </div>
          <div>
            <div className="text-sm font-semibold">知企智答</div>
            <div className="text-[11px] text-[#71717A] dark:text-[#A1A1AA]">智能客服系统</div>
          </div>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {PAGES.map((p) => (
            <button
              key={p.key}
              type="button"
              onClick={() => setPage(p.key)}
              className={`w-full rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                page === p.key
                  ? "bg-[#F4F4F5] font-medium text-[#18181B] dark:bg-[#18181B] dark:text-[#FAFAFA]"
                  : "text-[#71717A] hover:text-[#18181B] dark:text-[#A1A1AA] dark:hover:text-[#FAFAFA]"
              }`}
            >
              {p.label}
            </button>
          ))}
        </nav>
        <div className="px-5 py-4 text-[11px] text-[#71717A] dark:text-[#A1A1AA]">
          RAG · deepagents · bge
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-black/8 px-6 py-3.5 dark:border-white/7">
          <h2 className="text-sm font-medium">{PAGE_TITLES[page]}</h2>
          <button
            type="button"
            onClick={toggle}
            aria-label="切换主题"
            className={`relative h-6 w-11 rounded-full border transition-colors ${
              dark ? "border-white/7 bg-[#18181B]" : "border-black/8 bg-[#F4F4F5]"
            }`}
          >
            <span
              className={`absolute top-0.5 h-4.5 w-4.5 rounded-full transition-all ${
                dark ? "left-5.5 bg-[#60A5FA]" : "left-0.5 bg-white shadow-sm"
              }`}
            />
          </button>
        </header>
        <main className="min-h-0 flex-1">{active.render()}</main>
      </div>
    </div>
  );
}
