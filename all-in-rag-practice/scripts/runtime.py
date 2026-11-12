"""集中处理本地启动配置与通用模型环境变量。"""

import os
import sys
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = PROJECT_ROOT / "code" / "C8"


def prepare_environment():
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    os.environ.setdefault("HF_HOME", str(PROJECT_ROOT / ".cache" / "huggingface"))
    sys.path.insert(0, str(CODE_DIR))
    os.chdir(CODE_DIR)


def load_config():
    from config import RAGConfig

    config = RAGConfig.from_env()

    return replace(
        config,
        data_path=str(PROJECT_ROOT / "data" / "C8" / "cook"),
        index_save_path=str(CODE_DIR / "vector_index"),
        embedding_model=os.getenv("EMBEDDING_MODEL") or config.embedding_model,
    )
