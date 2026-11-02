/** 管理口令条：知识库页与日志页共用的鉴权入口。
 *
 * 设计取舍：
 * - 口令存 sessionStorage（关标签即失效），**不打进构建产物**——
 *   若用 VITE_ADMIN_TOKEN 构建期注入，任何人扒 bundle 即可读；
 * - 后端未配置 ADMIN_TOKEN 时管理接口返回 503，这里给一句提示避免误判。
 */

import { useState } from "react";
import { getAdminToken, setAdminToken } from "./api";
import { GhostButton } from "./ui";

export default function AdminTokenBar({ onSaved }: { onSaved: () => void }) {
  const [value, setValue] = useState(getAdminToken());
  const [saved, setSaved] = useState(false);

  const submit = (): void => {
    setAdminToken(value.trim());
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1500);
    onSaved();
  };

  return (
    <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg bg-black/[0.03] px-4 py-2 dark:bg-white/[0.04]">
      <span className="text-xs text-[#71717A] dark:text-[#A1A1AA]">管理口令</span>
      <input
        type="password"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") submit();
        }}
        placeholder="X-Admin-Token（对应后端 ADMIN_TOKEN）"
        className="w-72 rounded-lg border border-black/10 bg-white px-3 py-1.5 text-xs text-[#18181B] outline-none placeholder:text-[#A1A1AA] focus:border-[#2563EB] dark:border-white/10 dark:bg-[#18181B] dark:text-[#FAFAFA] dark:focus:border-[#60A5FA]"
      />
      <GhostButton onClick={submit}>{saved ? "已应用" : "应用"}</GhostButton>
      <span className="text-xs text-[#A1A1AA]">
        仅存于本标签页；后端未配置 ADMIN_TOKEN 时管理接口返回 503
      </span>
    </div>
  );
}
