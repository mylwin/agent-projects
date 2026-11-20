from app.core.exceptions import ApplicationError


class PolicyNotFoundError(ApplicationError):
    """保单不存在或不属于当前用户。"""

    status_code = 404
    code = "POLICY_NOT_FOUND"
    message = "保单不存在"
