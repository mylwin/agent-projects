"""认证测试共用的替身与 FastAPI 装配。"""

from typing import Self
from unittest.mock import AsyncMock

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exception_handlers import build_validation_error_response
from app.core.exceptions import ApplicationError
from app.modules.auth.models import Users
from app.modules.auth.repository import UsersRepository
from app.modules.auth.router import get_user_service, router
from app.modules.auth.service import UsersService


class FakeTransaction:
    """事务替身：不提交也不吞异常。"""

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        return False


class FakeSession:
    """只实现业务代码用到的事务接口。"""

    def begin(self) -> FakeTransaction:
        return FakeTransaction()


def make_user(**overrides) -> Users:
    data = {
        "id": 42,
        "username": "tester",
        "email": "tester@example.com",
        "display_name": "测试用户",
        "password_hash": "",
        "status": "active",
    }
    return Users(**(data | overrides))


def make_service() -> UsersService:
    service = UsersService(FakeSession())
    service.repository = AsyncMock(spec=UsersRepository)
    service.repository.find_by_username_or_email.return_value = None

    async def add(user: Users) -> None:
        user.id = 42

    service.repository.add.side_effect = add
    return service


def handle_application_error(request: Request, exc: ApplicationError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
    )


def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return build_validation_error_response(exc)


def build_app(service: UsersService) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(ApplicationError, handle_application_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.dependency_overrides[get_user_service] = lambda: service
    return app
