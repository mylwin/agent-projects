from app.core.exceptions import ApplicationError


class InsurancePlanNotFoundError(ApplicationError):
    status_code = 404
    code = "INSURANCE_PLAN_NOT_FOUND"
    message = "当前保险方案不存在"
