"""加载项目根目录的 .env，仅供进程入口调用。"""

from pathlib import Path

from dotenv import load_dotenv

DEFAULT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def load_env(path: Path = DEFAULT_ENV_FILE) -> None:
    """
    将 .env 载入进程环境；已存在的环境变量优先。

    :param path: 环境变量文件路径，默认项目根目录 .env。
    """
    load_dotenv(path, override=False)
