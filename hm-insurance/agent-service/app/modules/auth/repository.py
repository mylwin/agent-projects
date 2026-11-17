from app.modules.auth.models import Users
from sqlalchemy import Select, or_
from sqlalchemy.ext.asyncio import AsyncSession


class UsersRepository:
    """用户数据库相关操作"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, user: Users) -> None:
        """添加用户"""
        self.session.add(user)

    async def find_by_id(self, user_id: int) -> Users | None:
        """根据用户 ID 查询用户"""
        return await self.session.scalar(Select(Users).where(Users.id == user_id))

    async def find_by_username_or_email(
        self, username: str, email: str | None = None
    ) -> Users | None:
        """按用户名查询用户；传入邮箱时同时匹配邮箱，用于注册查重。"""
        condition = Users.username == username
        if email is not None:
            condition = or_(condition, Users.email == email)
        return await self.session.scalar(
            Select(Users).where(condition).limit(1)
        )
