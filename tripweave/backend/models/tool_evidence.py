from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """模型基类"""

    pass


class ToolEvidence(Base):
    """地图工具返回原文及结构化内容，作为研究证据"""

    __tablename__ = "tb_tool_evidence"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="逻辑外键：关联研究报告"
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    tool: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_call_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    __table_args__ = (
        Index("tb_tool_evidence_report_idx", "report_id", "sequence"),
        {"comment": "地图工具返回原文及结构化内容，作为研究证据"},
    )
