from datetime import datetime

from sqlalchemy import (
    BigInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """模型基类"""

    pass


class User(Base):
    """用户表"""

    __tablename__ = "tb_user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), server_default=text("CURRENT_TIMESTAMP(6)")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DATETIME(fsp=6), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("username", name="tb_user_username_idx"),
        {"comment": "用户表，仅保存用户名和密码哈希，登录态不落库"},
    )
