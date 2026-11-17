from typing import Literal, TypeAlias

from app.common.models import Base, CreateAtMixin, UpdateAtMixin
from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

Status: TypeAlias = Literal["active", "inactive", "suspended"]


class Users(Base, CreateAtMixin, UpdateAtMixin):
    """用户"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    username: Mapped[str] = mapped_column(
        String(80),
        unique=True,
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        String(160),
        unique=True,
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    display_name: Mapped[str] = mapped_column(String(100))

    status: Mapped[Status] = mapped_column(
        String(30),
        default="active",
        server_default="active",
        nullable=False,
    )
