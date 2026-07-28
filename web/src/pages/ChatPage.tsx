/** 对话主界面（设计页 01）：多轮对话 + 快捷问题 + 来源引用 + 命中/兜底徽章。 */

import { useEffect, useRef, useState } from "react";
import { api, type ChatResponse } from "../api";
import { Badge, PrimaryButton } from "../ui";

interface Msg {
  role: "user" | "assistant";
  text: string;
  meta?: ChatResponse;
}

const QUICK_QUESTIONS = [
  "腾讯的主营业务是什么？",
  "阿里巴巴的电商平台有哪些？",
  "字节跳动上市了吗？",
  "百度在自动驾驶方面有什么布局？",
];

export default function ChatPage() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function send(q: string) {
    const question = q.trim();
    if (!question || loading) return;
    setError(null);
    setInput("");
    setMessages((m) => [...m, { role: "user", text: question }]);
    setLoading(true);
    try {
      const r = await api.chat(question, sessionId);
      setSessionId(r.session_id);
      setMessages((m) => [...m, { role: "assistant", text: r.answer, meta: r }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "请求失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto px-6 py-6">
        {messages.length === 0 ? (
          <div className="mx-auto mt-16 max-w-lg text-center">
            <div className="text-lg font-semibold text-[#18181B] dark:text-[#FAFAFA]">
              知企智答 · 智能客服
            </div>
            <p className="mt-2 text-sm text-[#71717A] dark:text-[#A1A1AA]">
              基于企业知识库的 RAG 问答，目前支持腾讯、阿里、字节、百度。
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-2">
              {QUICK_QUESTIONS.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => void send(q)}
                  className="rounded-full border border-black/8 bg-[#F4F4F5] px-3 py-1.5 text-xs text-[#71717A] transition-colors hover:text-[#18181B] dark:border-white/7 dark:bg-[#18181B] dark:text-[#A1A1AA] dark:hover:text-[#FAFAFA]"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="flex justify-end">
                <div className="max-w-[70%] rounded-2xl rounded-br-md bg-[#2563EB] px-4 py-2.5 text-sm text-white dark:bg-[#60A5FA] dark:text-[#09090B]">
                  {m.text}
                </div>
              </div>
            ) : (
              <div key={i} className="flex justify-start">
                <div className="max-w-[75%] rounded-2xl rounded-bl-md border border-black/8 bg-white px-4 py-3 dark:border-white/7 dark:bg-[#18181B]">
                  <div className="whitespace-pre-wrap text-sm leading-relaxed text-[#18181B] dark:text-[#FAFAFA]">
                    {m.text}
                  </div>
                  {m.meta ? (
                    <div className="mt-2.5 flex flex-wrap items-center gap-1.5 border-t border-black/8 pt-2 dark:border-white/7">
                      <Badge tone="blue">{m.meta.intent}</Badge>
                      {m.meta.hit ? <Badge tone="green">命中</Badge> : null}
                      {m.meta.fallback ? <Badge tone="amber">兜底</Badge> : null}
                      {m.meta.sources.map((s) => (
                        <Badge key={s} tone="gray">来源：{s}</Badge>
                      ))}
                      <span className="ml-auto text-[11px] text-[#71717A] dark:text-[#A1A1AA]">
                        {m.meta.latency_ms}ms
                      </span>
                    </div>
                  ) : null}
                </div>
              </div>
            ),
          )
        )}
        {loading ? (
          <div className="flex justify-start">
            <div className="rounded-2xl border border-black/8 bg-white px-4 py-3 text-sm text-[#71717A] dark:border-white/7 dark:bg-[#18181B] dark:text-[#A1A1AA]">
              检索知识库中…
            </div>
          </div>
        ) : null}
        {error ? (
          <div className="mx-auto max-w-md rounded-lg bg-[#D97706]/10 px-4 py-2 text-center text-xs text-[#D97706] dark:text-[#FBBF24]">
            {error}
          </div>
        ) : null}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-black/8 px-6 py-4 dark:border-white/7">
        {messages.length > 0 ? (
          <div className="mb-3 flex flex-wrap gap-2">
            {QUICK_QUESTIONS.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => void send(q)}
                className="rounded-full border border-black/8 bg-[#F4F4F5] px-3 py-1 text-xs text-[#71717A] transition-colors hover:text-[#18181B] dark:border-white/7 dark:bg-[#18181B] dark:text-[#A1A1AA] dark:hover:text-[#FAFAFA]"
              >
                {q}
              </button>
            ))}
          </div>
        ) : null}
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void send(input);
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="请输入您想咨询的企业问题…"
            className="flex-1 rounded-lg border border-black/8 bg-white px-4 py-2 text-sm text-[#18181B] outline-none placeholder:text-[#71717A]/60 focus:border-[#2563EB]/40 dark:border-white/7 dark:bg-[#18181B] dark:text-[#FAFAFA] dark:placeholder:text-[#A1A1AA]/60 dark:focus:border-[#60A5FA]/40"
          />
          <PrimaryButton type="submit" disabled={loading || !input.trim()}>
            发送
          </PrimaryButton>
        </form>
      </div>
    </div>
  );
}
