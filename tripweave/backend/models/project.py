from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """模型基类"""

    pass


class Project(Base):
    """旅游计划项目表"""

    __tablename__ = "tb_project"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 逻辑外键：去除 ForeignKey 参数
    user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="逻辑外键：所属用户"
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    final_revision_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="逻辑外键：最终版本修订 ID"
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), server_default=text("CURRENT_TIMESTAMP(6)")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        server_default=text("CURRENT_TIMESTAMP(6)"),
        onupdate=text("CURRENT_TIMESTAMP(6)"),
    )

    __table_args__ = (
        Index("tb_project_user_updated_idx", "user_id", text("updated_at DESC")),
        {"comment": "旅行计划文件夹/项目表"},
    )
