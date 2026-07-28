"""意图识别：在进入 RAG 流程前对用户问题做轻量分类。

三类意图：
- 闲聊       ：问候/寒暄/客套，不走检索，直接礼貌回复。
- 企业咨询   ：询问企业相关信息，走 RAG 检索。
- 其他       ：非企业类实质问题，仍走一次检索兜底判定（防分类误判）。

策略：LLM 分类（免费模型）优先，失败时回退关键词规则，保证链路不断。
"""

from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .config import MODEL_CANDIDATES, SENSENOVA_API_KEY, SENSENOVA_BASE_URL

logger = logging.getLogger(__name__)

INTENT_CHITCHAT = "闲聊"
INTENT_COMPANY = "企业咨询"
INTENT_OTHER = "其他"

_VALID_INTENTS = {INTENT_CHITCHAT, INTENT_COMPANY, INTENT_OTHER}

_CLASSIFY_PROMPT = """你是意图分类器。将用户输入分为三类之一：

- 闲聊：问候、寒暄、感谢、告别、询问你是谁等客套话。
- 企业咨询：询问任何公司/企业的业务、产品、创始人、上市、财务、历史等信息。
- 其他：不属于以上两类的实质性问题（如天气、数学、生活常识）。

只输出 JSON：{"intent": "闲聊|企业咨询|其他"}，不要输出其他内容。"""

# 关键词规则兜底（LLM 不可用时）
_COMPANY_KEYWORDS = (
    "腾讯", "阿里", "字节", "百度", "公司", "企业", "上市", "股票",
    "创始人", "业务", "营收", "微信", "抖音", "淘宝", "游戏",
)
_CHITCHAT_KEYWORDS = ("你好", "您好", "谢谢", "再见", "你是谁", "在吗", "早上好", "晚上好", "hi", "hello")


def _rule_classify(question: str) -> str:
    q = question.strip().lower()
    if len(q) <= 12 and any(k in q for k in _CHITCHAT_KEYWORDS):
        return INTENT_CHITCHAT
    if any(k in question for k in _COMPANY_KEYWORDS):
        return INTENT_COMPANY
    return INTENT_OTHER


def classify_intent(question: str) -> str:
    """返回意图标签；LLM 优先，异常时回退规则分类。"""
    if not SENSENOVA_API_KEY:
        logger.warning("无 API Key，意图分类走规则回退")
        return _rule_classify(question)

    for model_name in MODEL_CANDIDATES:
        try:
            llm = ChatOpenAI(
                model=model_name,
                base_url=SENSENOVA_BASE_URL,
                api_key=SENSENOVA_API_KEY,  # type: ignore[arg-type]
                temperature=0.0,
                timeout=20,
                max_retries=0,
            )
            resp = llm.invoke(
                [SystemMessage(content=_CLASSIFY_PROMPT), HumanMessage(content=question)]
            )
            text = str(resp.content).strip()
            # 容忍模型输出 ```json 包裹
            if text.startswith("```"):
                text = text.strip("`").removeprefix("json").strip()
            intent = str(json.loads(text).get("intent", ""))
            if intent in _VALID_INTENTS:
                return intent
            logger.warning("意图分类返回非法标签 %r，回退规则", intent)
            return _rule_classify(question)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("意图分类 JSON 解析失败 (model=%s): %s", model_name, e)
            return _rule_classify(question)
        except Exception as e:  # noqa: BLE001 - 网络/限流等，换下一个模型
            logger.warning("意图分类模型 %s 调用失败: %s", model_name, e)

    return _rule_classify(question)
