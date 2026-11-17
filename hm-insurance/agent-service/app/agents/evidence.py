import hashlib
import json
import re
from copy import deepcopy
from decimal import Decimal
from typing import Any

from app.modules.insurance_plan.schemas import InsurancePlanCreate
from langchain.messages import AIMessage, HumanMessage, ToolMessage

SOURCE_PATTERN = re.compile(r"\[(ref-[A-Za-z0-9-]+)\]")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()[:16]


def tool_result(payload: dict) -> tuple[str, dict]:
    """同一份来源同时提供给模型和程序。"""
    artifact = {
        "citation_schema": 1,
        **payload,
    }
    return canonical_json(artifact), artifact


def read_artifact(message: Any) -> dict:
    if not isinstance(message, ToolMessage):
        return {}

    artifact = message.artifact
    if not isinstance(artifact, dict):
        return {}

    if artifact.get("citation_schema") != 1:
        return {}

    return artifact


def collect_sources(messages: list) -> dict[str, dict]:
    """从当前会话已经执行完成的工具消息读取来源。"""
    sources: dict[str, dict] = {}

    for message in messages:
        artifact = read_artifact(message)
        sources.update(artifact.get("sources", {}))

    return sources


def build_history_messages(
    messages: list,
    legacy_info: dict | None = None,
) -> list[dict]:
    """
    按消息顺序解析来源。

    某条 AI 回答只能引用它之前已经出现的工具证据，
    不能使用后面才检索出来的来源补齐之前的回答。
    """
    sources: dict[str, dict] = {}
    pending_products: dict[str, list] = {}
    result: list[dict] = []
    legacy_info = legacy_info or {}

    for message in messages:
        if isinstance(message, ToolMessage):
            artifact = read_artifact(message)
            sources.update(artifact.get("sources", {}))

            if "candidate_products" in artifact:
                pending_products["candidate_products"] = artifact["candidate_products"]

            if "plan_items" in artifact:
                # 保存结果优先展示方案产品。
                pending_products.pop("candidate_products", None)
                pending_products["plan_items"] = artifact["plan_items"]

            continue

        if isinstance(message, HumanMessage):
            pending_products = {}

            if message.text:
                result.append(
                    {
                        "id": message.id,
                        "role": "user",
                        "content": message.text,
                        "additional_info": None,
                    }
                )
            continue

        if not isinstance(message, AIMessage) or not message.text:
            continue

        referenced_ids = list(dict.fromkeys(SOURCE_PATTERN.findall(message.text)))

        used_sources = {
            source_id: sources[source_id]
            for source_id in referenced_ids
            if source_id in sources
        }

        unresolved_ids = [
            source_id for source_id in referenced_ids if source_id not in sources
        ]

        info = {
            "schema_version": 1,
            "sources": used_sources,
            "unresolved_source_ids": unresolved_ids,
            **deepcopy(pending_products),
        }

        # 对旧数据只读取当前消息原有的来源，
        # 不按 ref-001 去其他消息猜测匹配。
        old_info = legacy_info.get(message.id)
        if old_info and not used_sources and not pending_products:
            info = old_info

        result.append(
            {
                "id": message.id,
                "role": "assistant",
                "content": message.text,
                "additional_info": info,
            }
        )

        # 带工具调用的中间 AI 消息，不消费待展示产品。
        if not message.tool_calls:
            pending_products = {}

    return result


def build_plan_snapshot(
    plan: InsurancePlanCreate,
    messages: list,
) -> dict:
    """从服务端已有证据构造确认和保存使用的快照。"""
    registry = collect_sources(messages)
    selected_sources: dict[str, dict] = {}
    product_ids: set[int] = set()

    for item in plan.items:
        if item.product_id in product_ids:
            raise ValueError("方案中不能重复添加同一产品")

        product_ids.add(item.product_id)

        if not item.source_ids:
            raise ValueError(f"产品 {item.product_id} 缺少来源 ID")

        item_sources: list[dict] = []

        for source_id in item.source_ids:
            source = registry.get(source_id)

            if source is None:
                raise ValueError(f"来源不存在：{source_id}")

            if source.get("product_id") != item.product_id:
                raise ValueError(f"来源 {source_id} 不属于产品 {item.product_id}")

            selected_sources[source_id] = deepcopy(source)
            item_sources.append(source)

        product_sources = [
            source for source in item_sources if source.get("kind") == "product"
        ]

        if len(product_sources) != 1:
            raise ValueError(f"产品 {item.product_id} 必须指定一个产品资料来源")

        product = product_sources[0]["product"]

        if item.product_name != product["name"]:
            raise ValueError("产品名称与查询结果不一致")

        if item.category != product["category"]:
            raise ValueError("产品险种与查询结果不一致")

        min_premium = product.get("min_premium")
        expected_premium = (
            Decimal(str(min_premium)) if min_premium is not None else None
        )

        # 当前项目该字段表示产品最低保费，因此按这个含义校验。
        if item.annual_premium_budget != expected_premium:
            raise ValueError(f"产品 {item.product_id} 的最低保费与查询结果不一致")

    snapshot = {
        "schema_version": 1,
        "plan": plan.model_dump(mode="json"),
        "sources": selected_sources,
    }

    snapshot["plan_hash"] = content_hash(snapshot)
    return snapshot
