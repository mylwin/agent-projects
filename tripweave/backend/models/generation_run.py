from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """模型基类"""

    pass


class GenerationRun(Base):
    """每次行程生成尝试记录"""

    __tablename__ = "tb_generation_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="逻辑外键：关联项目"
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="逻辑外键：所属用户"
    )
    request: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    map_provider: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), server_default=text("CURRENT_TIMESTAMP(6)")
    )
    finished_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("tb_generation_run_project_idx", "project_id", text("started_at DESC")),
        Index("tb_generation_run_user_idx", "user_id"),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')", name="chk_run_status"
        ),
        {"comment": "每次行程生成尝试记录，成功与失败均保留"},
    )
