import json
from decimal import Decimal

from app.agents.schemas import InsuranceAgentContext
from app.infra.database import AsyncSessionFactory
from app.modules.insurance_plan.schemas import InsurancePlanCreate
from app.modules.insurance_plan.service import InsurancePlanService
from app.modules.product.service import ProductService
from fastapi.encoders import jsonable_encoder
from langchain.tools import ToolRuntime, tool
from langgraph.config import get_stream_writer


@tool
async def query_candidate_products(
    categories: list[str], premium_min: Decimal | None = None, limit: int = 5
):
    """
    根据险种和保费条件查询可用于推荐的候选保险产品。当用户咨询具体保险产品或需要保险产品推荐时使用。

    Args:
        categories: 产品分类列表，可选值为 medical、critical_illness、life、accident。
        premium_min: 最低保费上限，可选参数，只返回最低保费小于该值的产品。
        limit_per_category: 每个险种最多返回的产品数量，可选参数，默认5。
    """

    async with AsyncSessionFactory() as session:
        # 1.初始化 service
        product_service = ProductService(session)

        # 2.得到候选
        candidate_products = await product_service.list_limited_products(
            categories, premium_min, limit
        )

        # 3.返回 json 格式数据
        return jsonable_encoder(candidate_products)


@tool
async def save_insurance_plan(
    plan: InsurancePlanCreate,
    runtime: ToolRuntime[InsuranceAgentContext],
) -> dict[str, str]:
    """
    保存当前用户已确认的保险推荐方案。

    调用前应已查询候选产品，结合用户画像生成完整方案，
    并向用户展示推荐产品、推荐理由和预算信息。

    仅当用户明确要求保存，或明确同意保存刚刚展示的方案时调用。
    如果用户尚未确认，应先询问是否保存，收到明确同意后再调用。

    保存内容必须与用户确认的方案一致。
    只有工具返回保存成功后，才能告知用户方案已保存
    """

    async with AsyncSessionFactory() as session:
        service = InsurancePlanService(session)
        plan_id = await service.create_plan(
            user_id=runtime.context.user_id,
            data=plan,
        )

    return {
        "plan_id": str(plan_id),
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

    # 把model转换字典数据
    sources = {
        # 给文档编号，最终格式 {"ref-001": {"content": ""}}
        f"ref-{i:03d}": {
            "product_id": chunk.product_id,
            "clause_name": chunk.clause_name,
            "section_path": chunk.section_path,
            "content": chunk.content,
        }
        for i, chunk in enumerate(chunks, start=1)
    }

    # 把source写到自定义事件中
    writer = get_stream_writer()
    writer({"type": "additional_info", "data": sources})

    # 以JSON格式返回
    return json.dumps(sources, ensure_ascii=False)
