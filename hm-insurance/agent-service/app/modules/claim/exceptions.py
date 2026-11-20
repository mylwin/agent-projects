from app.core.exceptions import ApplicationError


class ClaimNotFoundError(ApplicationError):
    """理赔记录不存在或不属于当前用户。"""

    status_code = 404
    code = "CLAIM_NOT_FOUND"
    message = "理赔记录不存在"


class ApplicationFormNotFoundError(ApplicationError):
    """教学理赔申请表文件不存在。"""

    status_code = 404
    code = "APPLICATION_FORM_NOT_FOUND"
    message = "Application form not found"
