from app.core.security import (
    create_access_token, decode_refresh_token, hash_password, verify_password,
)
from app.modules.auth.exceptions import (
    InvalidCredentialsError,
    InactiveRefreshUserError,
    InvalidRefreshTokenError,
    RefreshUserNotFoundError,
    UserAlreadyExistError,
    UserInactiveError,
    UserNotFoundError,
    UserSuspendedError,
)
from app.modules.auth.models import Users
from app.modules.auth.repository import UsersRepository
from app.modules.auth.schemas import (
    UserAuthData,
    UserLoginRequest,
    UserLoginResponse,
    UserRegisterRequest,
    UserRegisterResponse,
)
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


class UsersService:
    """用户服务"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = UsersRepository(session)

    async def register(self, request: UserRegisterRequest) -> UserRegisterResponse:
        """创建用户并签发访问令牌，事务失败时回滚。"""
        try:
            async with self.session.begin():
                # 1.检查用户名或邮箱是否已被使用
                existing_user = await self.repository.find_by_username_or_email(
                    request.username, request.email
                )
                if existing_user is not None:
                    raise UserAlreadyExistError

                # 2.生成密码哈希并创建用户
                # Argon2 计算在线程池执行，避免阻塞异步请求。
                hashed_password = await run_in_threadpool(hash_password, request.password)
                user = Users(
                    username=request.username,
                    email=request.email,
                    password_hash=hashed_password,
                    display_name=request.username,
                    status="active",
                )
                await self.repository.add(user)

                # 3.刷新数据，获取数据库生成的用户 ID
                await self.session.flush()
                await self.session.refresh(user)

                # 4.签发访问令牌并组装响应
                response = UserRegisterResponse(
                    access_token=create_access_token(str(user.id)),
                    user=UserAuthData.model_validate(user, from_attributes=True),
                )
            return response
        except IntegrityError as exc:
            # 预查询无法避免并发请求同时注册，最终由数据库唯一约束兜底。
            if getattr(exc.orig, "sqlstate", None) == "23505":
                cause = getattr(exc.orig, "__cause__", None)
                constraint = getattr(cause, "constraint_name", None)
                if constraint in ("users_username_key", "users_email_key"):
                    raise UserAlreadyExistError from exc
            raise
    async def login(self, request: UserLoginRequest) -> UserLoginResponse:
        """校验用户状态和密码，登录成功后签发访问令牌。"""
        # 1.根据用户名查询用户
        user = await self.repository.find_by_username_or_email(request.username)
        if user is None:
            raise UserNotFoundError

        # 2.检查用户是否被封禁或未激活，仅允许 active 状态登录
        if user.status == "suspended":
            raise UserSuspendedError
        if user.status != "active":
            raise UserInactiveError

        # 3.在线程池校验密码，避免 Argon2 计算阻塞异步请求
        password_valid = await run_in_threadpool(
            verify_password, request.password, user.password_hash
        )
        if not password_valid:
            raise InvalidCredentialsError

        # 4.签发访问令牌并返回用户信息
        return UserLoginResponse(
            access_token=create_access_token(str(user.id)),
            user=UserAuthData.model_validate(user, from_attributes=True),
        )

    async def refresh(self, token: str | None) -> UserRegisterResponse:
        """通过刷新令牌重新检查用户状态，并签发新的访问令牌。"""
        # 1.校验 Cookie 中的刷新令牌，不依赖 Access Token
        if not token:
            raise InvalidRefreshTokenError
        payload = decode_refresh_token(token)
        try:
            user_id = int(payload["sub"])
        except (ValueError, TypeError, OverflowError) as exc:
            raise InvalidRefreshTokenError from exc
        if not 0 < user_id <= 2**63 - 1:
            raise InvalidRefreshTokenError

        # 2.从数据库读取最新的用户状态
        user = await self.repository.find_by_id(user_id)
        if user is None:
            raise RefreshUserNotFoundError
        if user.status != "active":
            raise InactiveRefreshUserError

        # 3.返回与注册相同结构的认证响应
        return UserRegisterResponse(
            access_token=create_access_token(str(user.id)),
            user=UserAuthData.model_validate(user, from_attributes=True),
        )
