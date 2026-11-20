from uuid import UUID

from app.modules.claim.exceptions import ClaimNotFoundError
from app.modules.claim.repository import ClaimRepository
from app.modules.claim.schemas import (
    ClaimData,
    ClaimGuideData,
    ClaimGuideMaterial,
    ClaimGuideStep,
    ClaimListData,
    ClaimStatus,
)
from app.modules.policy.exceptions import PolicyNotFoundError
from app.modules.policy.repository import PolicyRepository
from sqlalchemy.ext.asyncio import AsyncSession

APPLICATION_FORM_URI = "/api/v1/claim-guides/application-form"

CATEGORY_MATERIALS: dict[str, tuple[str, str]] = {
    "medical": ("就诊记录和医疗费用凭证", "按就诊情况准备病历、费用清单及发票。"),
    "accident": ("意外事故证明", "按事故类型和承保公司要求提供相关证明。"),
    "critical_illness": ("诊断证明和检查报告", "请向承保公司确认所需诊断依据。"),
    "life": ("保险事故相关证明", "涉及身故责任时，向承保公司确认所需证明。"),
}


class ClaimService:
    """提供理赔记录查询和保单理赔指引。"""

    def __init__(self, session: AsyncSession):
        """初始化理赔和保单查询仓库。"""
        self.claims = ClaimRepository(session)
        self.policies = PolicyRepository(session)

    async def list_claims(
        self, user_id: int, policy_id: UUID | None, status: ClaimStatus | None
    ) -> ClaimListData:
        """返回当前用户符合条件的理赔记录。"""
        claims = await self.claims.list_by_user(user_id, policy_id, status)
        return ClaimListData(
            items=[ClaimData.model_validate(claim) for claim in claims]
        )

    async def get_claim(self, claim_id: UUID, user_id: int) -> ClaimData:
        """返回当前用户指定理赔记录的详情。"""
        claim = await self.claims.find_by_id_and_user(claim_id, user_id)
        if claim is None:
            raise ClaimNotFoundError
        return ClaimData.model_validate(claim)

    async def get_guide(self, policy_id: UUID, user_id: int) -> ClaimGuideData:
        """按当前用户的保单及其险种生成理赔指引。"""
        policy = await self.policies.find_by_id_and_user(policy_id, user_id)
        if policy is None:
            raise PolicyNotFoundError

        product = policy.product
        material_name, material_remark = CATEGORY_MATERIALS[product.category]
        return ClaimGuideData(
            policy_id=policy.id,
            product_id=product.id,
            product_name=product.name,
            download_uri=APPLICATION_FORM_URI,
            steps=[
                ClaimGuideStep(
                    title="联系承保公司",
                    description=f"向{product.insurer}报案并确认申请渠道、时限和所需材料。",
                ),
                ClaimGuideStep(
                    title="准备并提交材料",
                    description="按承保公司的材料清单准备资料，通过其指定渠道提交。",
                ),
                ClaimGuideStep(
                    title="查询审核进度",
                    description="使用承保公司提供的案件号查询进度，按通知补交材料。",
                ),
            ],
            materials=[
                ClaimGuideMaterial(
                    name="理赔申请书",
                    required=True,
                    remark="可下载教学版申请表参考填写，正式申请使用承保公司的表格。",
                ),
                ClaimGuideMaterial(
                    name="身份证明及保单信息",
                    required=True,
                    remark="按承保公司要求提供申请人身份证明和保单号。",
                ),
                ClaimGuideMaterial(
                    name=material_name,
                    required=False,
                    remark=material_remark,
                ),
            ],
            notes=[
                "本商城提供教学指引，理赔申请由承保公司受理。",
                "具体保障、材料和时限以保险合同及承保公司的要求为准。",
            ],
        )
