# 知企智答 · 架构详解

> 配合 `README.md` 的速览，本文展开各层模块职责、数据契约与关键设计决策，便于评审与维护。

## 一、分层职责

| 层     | 模块                     | 职责                                                                                                                 |
| ------ | ------------------------ | -------------------------------------------------------------------------------------------------------------------- |
| 表现层 | `web/src/pages/*`        | 对话 / 知识库 / 日志三页；`theme.tsx` 明暗主题（localStorage 持久化）；`ui.tsx` 统一 Badge/Card/StatCard/Button      |
| 服务层 | `api.py` + `service.py`  | FastAPI 路由；`service.chat` 维护内存多轮上下文（最近 6 轮）、每轮落库 `chat_logs`、聚合指标与导出                   |
| 编排层 | `agent.py` + `intent.py` | `deepagents` Agent 编排；`intent.classify_intent` 意图分类（LLM JSON + 关键词规则兜底）；RAG 混合检索（原始问句 + LLM 改写双路）+ 客观命中判定 |
| 检索层 | `vectorstore.py`         | Chromadb 持久化向量库；`bge-small-zh-v1.5` 本地 embedding（query 侧加指令前缀）；距离阈值命中判定                    |
| 数据层 | `db.py` + `data/`        | SQLite 双层（`companies` + `chat_logs`）；Chroma 向量库；本地模型权重                                                |

## 二、核心数据流

```
用户问题
  → service.chat(question, session_id)
      → agent.answer_question(question, history)
          → intent.classify_intent
              ├─ 闲聊 → _answer_chitchat（轻量直答，不检索）
              └─ 企业咨询/其他 → deepagents Agent.invoke
                                      └─ 工具 search_company_knowledge
                                          → vectorstore.search（混合检索：原始问句 + LLM 改写 query 双路，去重合并）
                                              → chromadb cosine 检索 top_k
                                          → 命中块 / NO_HIT
          → 客观判定 hit = any(chunk.distance <= RETRIEVAL_MAX_DISTANCE)
          → fallback = not hit
      → 更新内存上下文（裁剪最近 6 轮）
      → insert_chat_log（落库失败不影响回答）
  → ChatResponse(intent, hit, fallback, sources, model, latency_ms)
```

## 三、关键设计决策

### 1. 客观命中判定（可审计、可统计）

`hit` / `fallback` **不依赖模型自述**，而由向量检索的 cosine 距离与阈值 `RETRIEVAL_MAX_DISTANCE=0.45` 客观计算。好处：

- 日志统计的命中率 / 兜底率真实可信，不受模型"幻觉式自信"干扰；
- 兜底触发条件统一，前端徽章、日志标签、指标口径一致。

### 2. 模型免费优先 + 失败回退

`MODEL_CANDIDATES = ["sensenova-6.7-flash-lite", "deepseek-v4-flash"]`。每次调用按序尝试，任一失败（超时 / 5xx / 空回答）即回退下一个；全部失败退回固定兜底话术，绝不让用户看到裸异常。密钥走 `.env` 的 `SENSENOVA_API_KEY`，零硬编码。

### 3. 本地 Embedding，离线可用

`config.EMBEDDING_MODEL` 优先使用项目内 `data/models/bge-small-zh-v1.5`，避免运行时依赖外网下载。query 侧统一加 `BGE_QUERY_INSTRUCTION` 指令前缀以提升召回。

### 4. 知识库增删即重建索引

`rebuild_index()` 先 `collection.get()` 取全部 existing ids，`collection.delete` 全清后全量 `add` **仅「已发布」** 企业。保证：

- 新增 / 删除后索引状态与 `companies` 表严格一致，无残留旧块；
- 「审核中」企业不进入检索索引，避免未审核资料被问答引用。

### 5. 多轮上下文裁剪

`service._SESSIONS` 内存维护每个 session 的最近 6 轮（`history[-12:]`），防上下文无限膨胀；日志已持久化在 SQLite，进程重启不丢审计数据，但内存会话需重新累积。

### 6. 密钥零信任

所有 API Key 仅经环境变量读取，`.env` 已加入 `.gitignore`；无硬编码、无入库。

### 7. 混合检索（原始问句 + LLM 改写 query 双路）

deepagents 的 LLM 在调用 `search_company_knowledge` 工具时，会把用户问题自由改写为更"检索友好"的短 query（如「百度推出了哪款大模型？」→「百度 大模型」）。这种改写对**多轮指代消解**（「它」→「腾讯」）有益，但会削弱**短事实问句**的召回——改写后的短串与知识块语义距离反而越过阈值（实测 0.5298 > 0.45），导致漏召。

解法：检索工具**同时**用「用户原始问句」与「agent 改写 query」两路检索，按文本去重后合并、按距离排序取 top_k，再统一以 `RETRIEVAL_MAX_DISTANCE=0.45` 客观判定命中。这样既保留指代消解能力，又保住短事实问句的忠实召回（实测百度问句原始句距离 0.4423 ≤ 0.45；引入混合检索后评估综合准确率由 87.5% 升至 100%）。

## 四、数据契约

### Company（知识库条目）

`id, name, ticker, business, industry, status["已发布"|"审核中"], knowledge, created_at, updated_at`

### ChatLog（对话日志）

`id, session_id, turn, question, answer, intent, hit(bool), fallback(bool), sources(csv), latency_ms, created_at`

### ChatResponse

`session_id, answer, intent, hit, fallback, sources[list], model, latency_ms`

### Metrics

`total_sessions, total_turns, hit_rate, fallback_rate, avg_turns`

## 五、提示词策略

- **系统提示（RAG）**：必须先用工具检索、仅依据检索块作答、禁止编造、末尾标注【来源：企业名】、NO_HIT 时直接返回固定兜底话术。
- **闲聊提示**：一两句礼貌回应并引导咨询企业信息，≤50 字，不检索。

## 六、可观测性

- 每次 `chat` 输出结构化日志：`session / turn / intent / hit / fallback / latency_ms`；
- 日志落库失败仅告警不阻断回答；
- `/api/metrics` 提供运营指标，`/api/logs/export` 支持 CSV（`utf-8-sig` 防中文乱码）/ JSON 复盘。
