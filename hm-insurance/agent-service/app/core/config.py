from collections.abc import Callable
from pathlib import Path
from typing import Literal, cast

from pydantic import Field, PostgresDsn, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 向上查找根目录
APP_ROOT = Path(__file__).resolve().parents[2]


class EnvSettings(BaseSettings):
    """公共 settings，配置 .env 文件"""

    model_config = SettingsConfigDict(
        env_file=APP_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class AppSettings(EnvSettings):
    """项目 settings"""

    name: str = Field(alias="APP_NAME")
    host: str = Field(alias="APP_HOST", default="127.0.0.1")
    port: int = Field(alias="APP_PORT", default=8001)
    debug: bool = Field(
        alias="APP_DEBUG", default=True, description="是否开启DEBUG模式"
    )


class DatabaseSettings(EnvSettings):
    """数据库 settings"""

    host: str = Field(alias="DB_HOST", default="localhost")
    port: int = Field(alias="DB_PORT", default=5432)
    name: str = Field(alias="DB_NAME", default="insurance")
    user: str = Field(alias="DB_USER", default="insurance")
    password: str = Field(alias="DB_PASSWORD", default="insurance123")
    echo: bool = Field(
        alias="DB_ECHO", default=False, description="是否打印数据库操作日志"
    )
    pool_size: int = Field(alias="DB_POOL_SIZE", default=5)
    max_overflow: int = Field(alias="DB_MAX_OVERFLOW", default=10)
    pool_recycle: int = Field(alias="DB_POOL_RECYCLE", default=1800)

    def build_url(self, scheme: str) -> str:
        """构建数据库连接字符串"""
        return PostgresDsn.build(
            scheme=scheme,
            host=self.host,
            port=self.port,
            username=self.user,
            password=self.password,
            path=self.name,
        ).encoded_string()

    @computed_field
    @property
    def url(self) -> str:
        """SQLAlchemy 连接字符串"""
        return self.build_url("postgresql+asyncpg")

    @computed_field
    @property
    def checkpoint_url(self) -> str:
        """PostgreSQL Checkpoint 兼容的连接字符串"""
        return self.build_url("postgresql")


class LLMSettings(EnvSettings):
    """LLM settings"""

    api_key: str = Field(alias="DEEPSEEK_API_KEY")
    chat_model: str = Field(alias="CHAT_MODEL", default="deepseek-flash")


class LoggingSettings(EnvSettings):
    """日志 settings"""

    # 可选值：DEBUG, INFO, WARNING, ERROR, CRITICAL
    level: str = Field(alias="LOG_LEVEL", default="INFO")


class RAGSettings(EnvSettings):
    """RAG settings"""

    mineru_token: str = Field(alias="MINERU_TOKEN")
    milvus_host: str = Field(alias="MILVUS_HOST", default="127.0.0.1")
    milvus_port: int = Field(alias="MILVUS_PORT", default=19530)

    @computed_field
    @property
    def milvus_url(self) -> str:
        """拼接 Milvus 服务地址"""
        return f"http://{self.milvus_host}:{self.milvus_port}"


class JWTSettings(EnvSettings):
    """JWT 签名与有效期配置"""

    secret_key: SecretStr = Field(alias="JWT_SECRET_KEY", min_length=32)
    algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = Field(
        alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES", default=30, gt=0
    )
    refresh_token_expire_days: int = Field(
        alias="JWT_REFRESH_TOKEN_EXPIRE_DAYS", default=7, gt=0
    )
    refresh_cookie_secure: bool = Field(
        alias="JWT_REFRESH_COOKIE_SECURE",
        default=False,
        description="HTTPS 部署时设为 true，本地 HTTP 开发设为 false",
    )


class Settings(BaseSettings):
    app: AppSettings = Field(
        default_factory=cast(Callable[[], AppSettings], AppSettings)
    )
    db: DatabaseSettings = Field(
        default_factory=cast(Callable[[], DatabaseSettings], DatabaseSettings)
    )
    llm: LLMSettings = Field(
        default_factory=cast(Callable[[], LLMSettings], LLMSettings)
    )
    logging: LoggingSettings = Field(
        default_factory=cast(Callable[[], LoggingSettings], LoggingSettings)
    )
    rag: RAGSettings = Field(
        default_factory=cast(Callable[[], RAGSettings], RAGSettings)
    )
    jwt: JWTSettings = Field(
        default_factory=cast(Callable[[], JWTSettings], JWTSettings)
    )


settings = Settings()
