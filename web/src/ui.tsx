/** 通用 UI 原子组件：徽章 / 卡片 / 按钮，对齐设计系统（低饱和柔底徽章 + 发丝线）。 */

import type { ReactNode } from "react";

type BadgeTone = "blue" | "green" | "amber" | "gray";

const TONE_CLASS: Record<BadgeTone, string> = {
  blue: "bg-[#2563EB]/10 text-[#2563EB] dark:bg-[#60A5FA]/10 dark:text-[#60A5FA]",
  green: "bg-[#16A34A]/10 text-[#16A34A] dark:bg-[#23B980]/10 dark:text-[#23B980]",
  amber: "bg-[#D97706]/10 text-[#D97706] dark:bg-[#FBBF24]/10 dark:text-[#FBBF24]",
  gray: "bg-black/5 text-[#71717A] dark:bg-white/10 dark:text-[#A1A1AA]",
};

export function Badge({ tone, children }: { tone: BadgeTone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${TONE_CLASS[tone]}`}
    >
      {children}
    </span>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-xl border border-black/8 bg-white dark:border-white/7 dark:bg-[#18181B] ${className}`}
    >
      {children}
    </div>
  );
}

export function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card className="px-5 py-4">
      <div className="text-xs text-[#71717A] dark:text-[#A1A1AA]">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-[#18181B] dark:text-[#FAFAFA]">{value}</div>
      {sub ? <div className="mt-1 text-xs text-[#71717A] dark:text-[#A1A1AA]">{sub}</div> : null}
    </Card>
  );
}

export function PrimaryButton({
  children,
  onClick,
  disabled = false,
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className="rounded-lg bg-[#2563EB] px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40 dark:bg-[#60A5FA] dark:text-[#09090B]"
    >
      {children}
    </button>
  );
}

export function GhostButton({
  children,
  onClick,
  active = false,
}: {
  children: ReactNode;
  onClick?: () => void;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-lg border px-3 py-1.5 text-sm transition-colors ${
        active
          ? "border-[#2563EB]/30 bg-[#2563EB]/10 text-[#2563EB] dark:border-[#60A5FA]/30 dark:bg-[#60A5FA]/10 dark:text-[#60A5FA]"
          : "border-black/8 bg-white text-[#71717A] hover:text-[#18181B] dark:border-white/7 dark:bg-[#18181B] dark:text-[#A1A1AA] dark:hover:text-[#FAFAFA]"
      }`}
    >
      {children}
    </button>
  );
}
