from app.core.exceptions import ApplicationError


class InsurancePlanNotFoundError(ApplicationError):
    """保险方案不存在异常"""

    status_code = 404
    code = "INSURANCE_PLAN_NOT_FOUND"
    message = "当前保险方案不存在"


class PlanItemNotFoundError(ApplicationError):
    """方案项不存在或不属于当前用户的指定方案。"""

    status_code = 404
    code = "PLAN_ITEM_NOT_FOUND"
    message = "保险方案项不存在"
