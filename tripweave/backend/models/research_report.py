from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """模型基类"""

    pass


class ResearchReport(Base):
    """研究报告"""

    __tablename__ = "tb_research_report"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="逻辑外键：关联生成运行"
    )
    topic: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    warnings: Mapped[list] = mapped_column(
        JSON, default=list, server_default=text("(JSON_ARRAY())"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), server_default=text("CURRENT_TIMESTAMP(6)")
    )

    __table_args__ = (
        UniqueConstraint("run_id", "topic", name="tb_research_report_run_topic_idx"),
        CheckConstraint(
            "topic IN ('attractions', 'weather', 'hotels')", name="chk_report_topic"
        ),
        {"comment": "每次生成运行中每个研究主题的摘要与警告"},
    )
