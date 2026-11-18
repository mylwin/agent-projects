from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidRefreshTokenError
from app.core.security import (
    create_access_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.modules.auth.exceptions import (
    InvalidCredentialsError,
    UserAlreadyExistsError,
    status_exception,
)
from app.modules.auth.models import Users
from app.modules.auth.repository import UsersRepository
from app.modules.auth.schemas import (
    AuthResponse,
    UserAuthData,
    UserLoginRequest,
    UserRegisterRequest,
)


class UsersService:
    """用户服务"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = UsersRepository(session)

    async def register(self, request: UserRegisterRequest) -> AuthResponse:
        """创建用户并签发访问令牌。"""
        user = Users(
            username=request.username,
            email=request.email,
            # Argon2 计算在线程池执行，避免阻塞事件循环
            password_hash=await run_in_threadpool(hash_password, request.password),
            display_name=request.username,
            status="active",
        )
        try:
            async with self.session.begin():
                if await self.repository.find_by_username_or_email(
                    request.username, request.email
                ):
                    raise UserAlreadyExistsError
                await self.repository.add(user)
        except IntegrityError as exc:
            # 预查询挡不住并发注册，最终由数据库唯一约束兜底
            raise UserAlreadyExistsError from exc
        return self._auth_response(user)

    async def login(self, request: UserLoginRequest) -> AuthResponse:
        """校验用户状态和密码，登录成功后签发访问令牌。"""
        # 登录账号可能是用户名或邮箱，两列都按同一个值匹配
        user = await self.repository.find_by_username_or_email(
            request.username, request.username
        )
        # 用户不存在与密码错误返回同一提示，避免暴露账号是否注册
        if user is None:
            raise InvalidCredentialsError
        if user.status != "active":
            raise status_exception(user.status)
        if not await run_in_threadpool(
            verify_password, request.password, user.password_hash
        ):
            raise InvalidCredentialsError
        return self._auth_response(user)

    async def refresh(self, token: str) -> AuthResponse:
        """用刷新令牌重新检查用户状态，并签发新的访问令牌。"""
        user = await self.repository.find_by_id(int(decode_refresh_token(token)["sub"]))
        if user is None:
            raise InvalidRefreshTokenError
        if user.status != "active":
            raise status_exception(user.status)
        return self._auth_response(user)

    def _auth_response(self, user: Users) -> AuthResponse:
        """组装认证响应，注册、登录、刷新共用。"""
        return AuthResponse(
            access_token=create_access_token(str(user.id)),
            user=UserAuthData.from_user(user),
        )
