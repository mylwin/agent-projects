"""保存项目内每轮对话及其依据和生成结果，不保存隐藏推理。"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.project import Base


class ConversationTurn(Base):
    """一轮用户输入与助手回复；运行状态用于并发保护和失败恢复。"""

    __tablename__ = "tb_conversation_turn"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    base_revision_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    result_revision_id: Mapped[int | None] = mapped_column(BigInteger)
    day_id: Mapped[int] = mapped_column(Integer, nullable=False)
    generate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user_text: Mapped[str] = mapped_column(Text, nullable=False)
    assistant_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), server_default=text("CURRENT_TIMESTAMP(6)")
    )
    deadline_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    __table_args__ = (
        Index("tb_conversation_project_id_idx", "project_id", "id"),
        Index("tb_conversation_project_status_idx", "project_id", "status"),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'cancelled')",
            name="chk_conversation_status",
        ),
    )
