"""
RAG系统配置文件
"""

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

CODE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CODE_DIR.parents[1]


def load_environment() -> None:
    """从项目根目录读取配置，保证所有入口使用同一份环境和模型缓存。"""
    load_dotenv(PROJECT_ROOT / ".env")
    os.environ.setdefault("HF_HOME", str(PROJECT_ROOT / ".cache" / "huggingface"))


# 在模型相关模块导入前确定配置与缓存位置。
load_environment()


def env_value(*names: str) -> str:
    """优先使用通用配置，忽略空值，并兼容 OPENAI_* 环境变量。"""
    return next(
        (os.environ[name].strip() for name in names if os.getenv(name, "").strip()), ""
    )


def get_llm_api_key() -> str:
    """获取 LLM API Key"""
    return env_value("LLM_API_KEY", "OPENAI_API_KEY")


@dataclass
class RAGConfig:
    """RAG系统配置类"""

    # 路径配置
    data_path: str = str(PROJECT_ROOT / "data" / "C8" / "cook")
    index_save_path: str = str(CODE_DIR / "vector_index")

    # 模型配置
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    llm_model: str = ""
    llm_base_url: str = ""

    # 检索配置
    top_k: int = 3

    # 生成配置
    temperature: float = 0.1
    max_tokens: int = 2048

    @classmethod
    def from_env(cls) -> "RAGConfig":
        return cls(
            embedding_model=env_value("EMBEDDING_MODEL") or cls.embedding_model,
            llm_model=env_value("LLM_MODEL", "OPENAI_MODEL"),
            llm_base_url=env_value("LLM_BASE_URL", "OPENAI_BASE_URL"),
        )

    def validate_llm(self):
        missing = [
            name
            for name, value in (
                ("LLM_API_KEY", get_llm_api_key()),
                ("LLM_BASE_URL", self.llm_base_url.strip()),
                ("LLM_MODEL", self.llm_model.strip()),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "请在 .env 中配置 "
                + "、".join(missing)
                + "（也支持对应的 OPENAI_* 变量）"
            )
        url = urlparse(self.llm_base_url)
        if url.scheme not in ("http", "https") or not url.netloc:
            raise ValueError("LLM_BASE_URL 必须是有效的 http(s) API 基础地址")

    @classmethod
    def from_dict(cls, config_dict: dict[str, Any]) -> "RAGConfig":
        """从字典创建配置对象"""
        return cls(**config_dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return asdict(self)


# 默认配置实例
DEFAULT_CONFIG = RAGConfig()
