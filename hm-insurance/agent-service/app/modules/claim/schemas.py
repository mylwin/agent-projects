from decimal import Decimal
from typing import Literal
from uuid import UUID

from app.common.dates import BusinessDateTime
from pydantic import BaseModel, ConfigDict, computed_field

type ClaimStatus = Literal["submitted", "reviewing", "approved", "rejected", "paid"]

STATUS_MESSAGES: dict[ClaimStatus, str] = {
    "submitted": "理赔申请已提交，等待承保公司受理。",
    "reviewing": "保险公司正在审核材料，可能要求补充资料。",
    "approved": "理赔审核已通过，等待支付。",
    "rejected": "理赔申请未通过，请向承保公司查询原因。",
    "paid": "理赔款已支付。",
}


class ClaimPolicyData(BaseModel):
    """理赔记录关联的保单摘要。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    policy_number: str


class ClaimData(BaseModel):
    """理赔列表和详情共用的记录。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: int
    policy_id: UUID | None
    claim_number: str | None
    claim_type: str
    amount: Decimal | None
    description: str | None
    status: ClaimStatus
    policy: ClaimPolicyData | None
    submitted_at: BusinessDateTime
    updated_at: BusinessDateTime

    @computed_field
    @property
    def status_message(self) -> str:
        """提供理赔状态对应的中文说明。"""
        return STATUS_MESSAGES[self.status]


class ClaimListData(BaseModel):
    """当前用户的理赔记录列表。"""

    items: list[ClaimData]


class ClaimGuideStep(BaseModel):
    """理赔指引中的一个步骤。"""

    title: str
    description: str


class ClaimGuideMaterial(BaseModel):
    """理赔指引中的一项参考材料。"""

    name: str
    required: bool
    remark: str


class ClaimGuideData(BaseModel):
    """保单对应产品的理赔指引。"""

    policy_id: UUID
    product_id: int
    product_name: str
    download_uri: str
    steps: list[ClaimGuideStep]
    materials: list[ClaimGuideMaterial]
    notes: list[str]
