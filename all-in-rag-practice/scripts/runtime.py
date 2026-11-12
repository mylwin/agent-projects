"""集中处理本地启动配置与通用模型环境变量。"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = PROJECT_ROOT / "code" / "C8"


def prepare_environment():
    sys.path.insert(0, str(CODE_DIR))

    from config import load_environment

    load_environment()


def load_config():
    from config import RAGConfig

    return RAGConfig.from_env()
