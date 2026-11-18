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
        self, username: str, email: str
    ) -> Users | None:
        """查询用户名或邮箱匹配的用户，任一命中即返回"""
        return await self.session.scalar(
            Select(Users)
            .where(or_(Users.username == username, Users.email == email))
            .limit(1)
        )
