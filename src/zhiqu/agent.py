"""编排层：deepagents Agent（意图识别 + RAG 工具调用 + 兜底判定）。

流程：用户问题 -> Agent（可调用知识库检索工具）-> 回答 + 来源引用。
命中/兜底由检索距离阈值客观判定，不依赖模型自述。
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from .config import MODEL_CANDIDATES, SENSENOVA_API_KEY, SENSENOVA_BASE_URL
from .intent import INTENT_CHITCHAT, classify_intent
from .vectorstore import RetrievedChunk, search

logger = logging.getLogger(__name__)

FALLBACK_TEXT = (
    "抱歉，知识库中暂未收录与该问题相关的企业资料。"
    "目前支持咨询：腾讯控股、阿里巴巴集团、字节跳动、百度。"
    "您可以换个问法，或联系管理员在知识库后台补充相关企业条目。"
)

CHITCHAT_SYSTEM_PROMPT = (
    "你是「知企智答」智能客服，专注解答中国互联网公司相关问题。"
    "当前用户在寒暄闲聊，请用一两句话礼貌回应，并自然引导用户咨询企业信息"
    "（目前支持：腾讯控股、阿里巴巴集团、字节跳动、百度）。中文作答，50 字以内。"
)

SYSTEM_PROMPT = """你是「知企智答」智能客服，专门解答关于中国互联网公司的问题。

工作规则：
1. 收到用户问题后，必须先调用 search_company_knowledge 工具检索企业知识库。
2. 仅依据检索到的知识块作答，禁止编造知识库之外的事实。
3. 回答末尾用「【来源：企业名】」标注引用来源。
4. 如果工具返回「NO_HIT」，直接回复固定兜底话术，不要自行发挥。
5. 回答保持简洁专业，中文作答，不超过 200 字。
"""


@dataclass
class RetrievalTrace:
    """单次问答内的检索痕迹（用于客观判定命中/兜底）。"""

    calls: int = 0
    chunks: list[RetrievedChunk] = field(default_factory=list)

    @property
    def hit(self) -> bool:
        return any(c.hit for c in self.chunks)

    @property
    def sources(self) -> list[str]:
        seen: list[str] = []
        for c in self.chunks:
            if c.hit and c.company not in seen:
                seen.append(c.company)
        return seen


@dataclass
class AgentAnswer:
    """一次问答的完整结果。"""

    question: str
    answer: str
    intent: str
    hit: bool
    fallback: bool
    sources: list[str]
    model: str
    latency_ms: int
    session_id: str


_TRACE: RetrievalTrace | None = None
_CURRENT_QUESTION: str | None = None


@tool
def search_company_knowledge(query: str) -> str:
    """检索企业知识库，返回与 query 最相关的知识块；无命中时返回 NO_HIT。

    混合检索：同时用「agent 改写后的 query」与「用户原始问句」检索并去重合并，
    兼顾多轮指代消解（agent 能解析代词）与短事实问句的忠实召回
    （避免 LLM 改写削弱语义匹配，例如「百度推出了哪款大模型」被改作「百度 大模型」后距离升高而漏召）。
    """
    global _TRACE, _CURRENT_QUESTION
    queries = [query]
    if _CURRENT_QUESTION and _CURRENT_QUESTION.strip() != query.strip():
        queries.append(_CURRENT_QUESTION)
    merged: list[RetrievedChunk] = []
    seen_texts: set[str] = set()
    for q in queries:
        for c in search(q):
            if c.text not in seen_texts:
                seen_texts.add(c.text)
                merged.append(c)
    merged.sort(key=lambda c: c.distance)
    if _TRACE is not None:
        _TRACE.calls += 1
        _TRACE.chunks.extend(merged)
    hits = [c for c in merged if c.hit]
    if not hits:
        return "NO_HIT：知识库中没有与该问题足够相关的资料。"
    parts = [f"[来源:{c.company} 距离:{c.distance}]\n{c.text}" for c in hits]
    return "\n\n".join(parts)


def _build_model(model_name: str) -> ChatOpenAI:
    if not SENSENOVA_API_KEY:
        raise RuntimeError("缺少 SENSENOVA_API_KEY 环境变量，请在 .env 中配置")
    return ChatOpenAI(
        model=model_name,
        base_url=SENSENOVA_BASE_URL,
        api_key=SENSENOVA_API_KEY,  # type: ignore[arg-type]
        temperature=0.3,
        timeout=60,
        max_retries=1,
    )


def _build_agent(model_name: str) -> Any:
    from deepagents import create_deep_agent

    return create_deep_agent(
        tools=[search_company_knowledge],
        model=_build_model(model_name),
        system_prompt=SYSTEM_PROMPT,
    )


def _extract_final_text(messages: list[BaseMessage]) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage):
            content = m.content
            if isinstance(content, str) and content.strip():
                return content.strip()
            if isinstance(content, list):
                texts = [
                    str(b.get("text", ""))
                    for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                joined = "".join(texts).strip()
                if joined:
                    return joined
    return ""


def _answer_chitchat(
    question: str, history: list[dict[str, str]], sid: str, start: float
) -> AgentAnswer:
    """闲聊分支：不走检索，直接轻量回复。"""
    last_err: Exception | None = None
    for model_name in MODEL_CANDIDATES:
        try:
            llm = _build_model(model_name)
            msgs: list[dict[str, str]] = [
                {"role": "system", "content": CHITCHAT_SYSTEM_PROMPT},
                *history,
                {"role": "user", "content": question},
            ]
            resp = llm.invoke(msgs)
            answer = str(resp.content).strip()
            if not answer:
                raise RuntimeError("模型返回空回答")
            return AgentAnswer(
                question=question,
                answer=answer,
                intent=INTENT_CHITCHAT,
                hit=False,
                fallback=False,
                sources=[],
                model=model_name,
                latency_ms=int((time.monotonic() - start) * 1000),
                session_id=sid,
            )
        except Exception as e:  # noqa: BLE001 - 记录后回退下一个模型
            last_err = e
            logger.warning("闲聊模型 %s 调用失败，尝试回退: %s", model_name, e)
    logger.error("闲聊所有候选模型均失败: %s", last_err)
    return AgentAnswer(
        question=question,
        answer="您好！我是知企智答客服，可以咨询腾讯、阿里、字节、百度的企业信息。",
        intent=INTENT_CHITCHAT,
        hit=False,
        fallback=False,
        sources=[],
        model="none",
        latency_ms=int((time.monotonic() - start) * 1000),
        session_id=sid,
    )


def answer_question(
    question: str,
    session_id: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> AgentAnswer:
    """单次问答入口：意图识别 -> 闲聊直答 / RAG 检索；模型免费优先、失败回退。"""
    global _TRACE, _CURRENT_QUESTION
    sid = session_id or uuid.uuid4().hex[:12]
    start = time.monotonic()

    intent = classify_intent(question)
    hist: list[dict[str, str]] = list(history or [])
    if intent == INTENT_CHITCHAT:
        return _answer_chitchat(question, hist, sid, start)

    messages: list[dict[str, str]] = hist
    messages.append({"role": "user", "content": question})

    last_err: Exception | None = None
    for model_name in MODEL_CANDIDATES:
        _TRACE = RetrievalTrace()
        _CURRENT_QUESTION = question
        try:
            agent = _build_agent(model_name)
            result = agent.invoke({"messages": messages})
            answer = _extract_final_text(result.get("messages", []))
            trace = _TRACE
            hit = trace.hit
            fallback = not hit
            if fallback and not answer:
                answer = FALLBACK_TEXT
            if not answer:
                raise RuntimeError("模型返回空回答")
            latency = int((time.monotonic() - start) * 1000)
            return AgentAnswer(
                question=question,
                answer=answer,
                intent=intent,
                hit=hit,
                fallback=fallback,
                sources=trace.sources,
                model=model_name,
                latency_ms=latency,
                session_id=sid,
            )
        except Exception as e:  # noqa: BLE001 - 记录后回退下一个模型
            last_err = e
            logger.warning("模型 %s 调用失败，尝试回退: %s", model_name, e)
        finally:
            _TRACE = None
            _CURRENT_QUESTION = None

    latency = int((time.monotonic() - start) * 1000)
    logger.error("所有候选模型均失败: %s", last_err)
    return AgentAnswer(
        question=question,
        answer=FALLBACK_TEXT,
        intent=intent,
        hit=False,
        fallback=True,
        sources=[],
        model="none",
        latency_ms=latency,
        session_id=sid,
    )
