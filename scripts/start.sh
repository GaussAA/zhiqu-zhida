#!/usr/bin/env bash
# 知企智答 · 一键启动脚本（开发模式：前后端分离）
# 用法：bash scripts/start.sh
# 前置：已执行 `uv sync` 与 `cd web && pnpm install`
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== 知企智答 启动检查 =="
if [ ! -f .env ]; then
  echo "✗ 缺少 .env，请先执行：cp .env.example .env 并填入 SENSENOVA_API_KEY"
  exit 1
fi

if [ ! -d web/node_modules ]; then
  echo "✗ 前端依赖未安装，请先执行：cd web && pnpm install"
  exit 1
fi

# 避免 WorkBuddy 安全垫片误拦截 pnpm 临时文件（真实环境无此变量则忽略）
export NODE_OPTIONS="${NODE_OPTIONS:-} --use-system-ca"

echo ">>> 启动后端 (uvicorn :8720)"
uv run uvicorn zhiqu.api:app --app-dir src --host 127.0.0.1 --port 8720 &
API_PID=$!
sleep 3

echo ">>> 启动前端 (vite :5173)"
( cd web && pnpm dev ) &
WEB_PID=$!

cleanup() {
  echo ""
  echo ">>> 正在关闭服务..."
  kill "$API_PID" "$WEB_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo ""
echo "✓ 已启动："
echo "    前端工作台  http://localhost:5173"
echo "    后端 API    http://127.0.0.1:8720"
echo "    按 Ctrl+C 停止"
echo ""
wait
