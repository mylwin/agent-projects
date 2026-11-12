"""
RAG系统配置文件
"""

import os
from dataclasses import asdict, dataclass
from typing import Dict, Any
from urllib.parse import urlparse


def env_value(*names: str) -> str:
    """优先使用通用配置，忽略空值，并兼容 OPENAI_* 环境变量。"""
    return next((os.environ[name].strip() for name in names if os.getenv(name, "").strip()), "")


def get_llm_api_key() -> str:
    return env_value("LLM_API_KEY", "OPENAI_API_KEY")

@dataclass
class RAGConfig:
    """RAG系统配置类"""

    # 路径配置
    data_path: str = "../../data/C8/cook"
    index_save_path: str = "./vector_index"

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
    def from_env(cls) -> 'RAGConfig':
        return cls(
            llm_model=env_value("LLM_MODEL", "OPENAI_MODEL"),
            llm_base_url=env_value("LLM_BASE_URL", "OPENAI_BASE_URL"),
        )

    def validate_llm(self):
        missing = [name for name, value in (
            ("LLM_API_KEY", get_llm_api_key()),
            ("LLM_BASE_URL", self.llm_base_url.strip()),
            ("LLM_MODEL", self.llm_model.strip()),
        ) if not value]
        if missing:
            raise ValueError("请在 .env 中配置 " + "、".join(missing) + "（也支持对应的 OPENAI_* 变量）")
        url = urlparse(self.llm_base_url)
        if url.scheme not in ("http", "https") or not url.netloc:
            raise ValueError("LLM_BASE_URL 必须是有效的 http(s) API 基础地址")

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'RAGConfig':
        """从字典创建配置对象"""
        return cls(**config_dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

# 默认配置实例
DEFAULT_CONFIG = RAGConfig()
