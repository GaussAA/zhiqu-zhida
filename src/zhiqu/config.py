"""全局配置：路径、模型端点、检索参数。

所有敏感凭证一律走环境变量（.env），严禁硬编码。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（src/zhiqu/config.py -> 上溯两级）
ROOT_DIR: Path = Path(__file__).resolve().parents[2]
DATA_DIR: Path = ROOT_DIR / "data"
DB_PATH: Path = DATA_DIR / "zhiqu.db"
CHROMA_DIR: Path = DATA_DIR / "chroma"

load_dotenv(ROOT_DIR / ".env")

# ---- LLM 端点（免费优先，付费兜底）----
SENSENOVA_API_KEY: str = os.environ.get("SENSENOVA_API_KEY", "")
SENSENOVA_BASE_URL: str = os.environ.get(
    "SENSENOVA_BASE_URL", "https://token.sensenova.cn/v1"
)

# 模型回退顺序：sensenova 免费主力 -> sensenova 免费 deepseek 通道
MODEL_CANDIDATES: list[str] = [
    "sensenova-6.7-flash-lite",
    "deepseek-v4-flash",
]

# ---- Embedding ----
# 优先使用项目内本地权重（避免运行时依赖外网），不存在时回退 HF 仓库名
_LOCAL_EMBEDDING_DIR: Path = DATA_DIR / "models" / "bge-small-zh-v1.5"
EMBEDDING_MODEL: str = os.environ.get(
    "EMBEDDING_MODEL",
    str(_LOCAL_EMBEDDING_DIR) if _LOCAL_EMBEDDING_DIR.exists() else "BAAI/bge-small-zh-v1.5",
)
# bge 系列查询侧建议加指令前缀以提升召回
BGE_QUERY_INSTRUCTION: str = "为这个句子生成表示以用于检索相关文章："

# ---- 检索参数 ----
RETRIEVAL_TOP_K: int = 4
# cosine 距离阈值：低于该相似度视为未命中（chromadb 返回距离 = 1 - 相似度）
RETRIEVAL_MAX_DISTANCE: float = float(os.environ.get("RETRIEVAL_MAX_DISTANCE", "0.45"))

# ---- 服务 ----
SERVER_HOST: str = os.environ.get("SERVER_HOST", "127.0.0.1")
SERVER_PORT: int = int(os.environ.get("SERVER_PORT", "8720"))


def ensure_dirs() -> None:
    """确保数据目录存在。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
