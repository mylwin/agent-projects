import json
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from app.agents.schemas import InsuranceAgentContext
from app.infra.database import AsyncSessionFactory
from app.modules.insurance_plan.schemas import InsurancePlanCreate
from app.modules.insurance_plan.service import InsurancePlanService
from app.modules.product.service import ProductService
from fastapi.encoders import jsonable_encoder
from langchain.tools import ToolRuntime, tool
from langgraph.config import get_stream_writer
from langgraph.types import interrupt


@tool
async def query_candidate_products(
    categories: list[str], premium_min: Decimal | None = None, limit: int = 5
):
    """
    根据险种和保费条件查询可用于推荐的候选保险产品。当用户咨询具体保险产品或需要保险产品推荐时使用。

    Args:
        categories: 产品分类列表，可选值为 medical、critical_illness、life、accident。
        premium_min: 最低保费上限，可选参数，只返回最低保费小于该值的产品。
        limit: 每个险种最多返回的产品数量，可选参数，默认5。
    """

    async with AsyncSessionFactory() as session:
        # 1.初始化 service
        product_service = ProductService(session)

        # 2.得到候选
        candidate_products = await product_service.list_limited_products(
            categories, premium_min, limit
        )

        # 3.将候选产品同步到前端
        products = jsonable_encoder(candidate_products)
        writer = get_stream_writer()
        writer({"type": "additional_info", "data": {"candidate_products": products}})
        return products


@tool
async def save_insurance_plan(
    plan: InsurancePlanCreate,
    runtime: ToolRuntime[InsuranceAgentContext],
) -> dict[str, str]:
    """
    发起保险推荐方案的保存确认；用户批准后才写入数据库。

    调用条件：
    - 已查询候选产品，并向用户展示完整方案。
    - 用户明确表示希望保存该方案。
    - 用户只是同意继续推荐、选择产品或修改方案，不代表要求保存。

    plan 必须与展示给用户的方案一致，使用真实产品 ID，
    不得编造用户信息、产品信息或保费。

    本工具会暂停执行并展示确认信息，等待用户批准或拒绝。
    无需在调用前重复进行最终确认。用户批准后保存；拒绝则不保存，
    返回拒绝原因供后续调整方案。拒绝后不得自动重试保存，
    应先沟通调整并获得新的保存意愿。
    只有工具返回保存成功后，才能告知用户方案已保存。
    """

    # TODO(citation-flow): 中断前固化方案版本、所选产品及有效来源快照，随确认载荷返回；
    # 批准恢复后使用同一快照保存并发送 plan_items/来源，拒绝时不得发送已保存事件。
    # 来源从服务端证据注册表解析并校验产品归属，不接受模型编造的原文。
    # 中断执行,用户确认方案没问题再保存到数据库中
    decision = interrupt(
        {
            "plan": plan.model_dump(mode="json"),
            "confirm_info": "请确认是否保存当前保险方案?",
            "action": ["approve", "reject"],
        }
    )

    # 如果拒绝,则不进行保存
    if not isinstance(decision, dict) or decision.get("action") not in ("approve", "reject"):
        return {"status": "not_saved", "message": "确认结果无效，方案未保存，请重新发起确认。"}
    if decision["action"] == "reject":
        reason = decision.get("reject_reason")
        reason = reason.strip() if isinstance(reason, str) else ""
        return {
            "status": "rejected",
            "reject_reason": reason or "用户未填写原因",
            "message": "用户拒绝保存，方案未写入数据库。请结合拒绝原因沟通调整，不要自动重试保存。",
        }
    async with AsyncSessionFactory() as session:
        service = InsurancePlanService(session)
        plan_id = await service.create_plan(
            user_id=runtime.context.user_id,
            data=plan,
        )

    # 保存成功后同步方案产品，拒绝或保存失败时不发送
    plan_items = [
        {**item.model_dump(mode="json"), "plan_id": str(plan_id)}
        for item in plan.items
    ]
    writer = get_stream_writer()
    writer({"type": "additional_info", "data": {"plan_items": plan_items}})

    return {
        "plan_id": str(plan_id),
        "status": "saved",
        "message": "保险方案保存成功",
    }


@tool
async def query_product_clause(query: str, k: int, product_id: int) -> str | None:
    """
    从知识库中检索指定产品的条款信息

    Args:
        query: 检索的条款内容
        k: 检索的条数
        product_id: 条款所属的产品ID
    """

    from app.rag import retrieval

    # 检索得到结果
    chunks = await retrieval.retrieve(query, k, product_id)
    if not chunks:
        return "没有从[知识库]中检索到该产品相关的保险条款"

    # 使用产品、父块和内容生成固定编号，多次查询不会重名覆盖
    sources = {
        f"ref-clause-{chunk.product_id}-{uuid5(NAMESPACE_URL, f'{chunk.id}:{chunk.content}')}": {
            "product_id": chunk.product_id,
            "clause_name": chunk.clause_name,
            "section_path": chunk.section_path,
            "content": chunk.content,
        }
        for chunk in chunks
    }

    # 把source写到自定义事件中
    writer = get_stream_writer()
    writer({"type": "additional_info", "data": {"sources": sources}})

    # 以JSON格式返回
    return json.dumps(sources, ensure_ascii=False)
