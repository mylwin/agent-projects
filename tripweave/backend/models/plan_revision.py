from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Index,
    Integer,
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


class PlanRevision(Base):
    __tablename__ = "tb_plan_revision"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="逻辑外键：所属项目"
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    trip: Mapped[dict] = mapped_column(JSON, nullable=False)
    places: Mapped[list] = mapped_column(
        JSON, default=list, server_default=text("(JSON_ARRAY())"), nullable=False
    )
    warnings: Mapped[list] = mapped_column(
        JSON, default=list, server_default=text("(JSON_ARRAY())"), nullable=False
    )
    reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_run_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="逻辑外键：关联生成运行"
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), server_default=text("CURRENT_TIMESTAMP(6)")
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id", "number", name="tb_plan_revision_project_number_idx"
        ),
        Index("tb_plan_revision_run_idx", "generation_run_id"),
        {"comment": "行程版本快照，行程主体以 JSON 保存，不拆每日活动和地点表"},
    )
