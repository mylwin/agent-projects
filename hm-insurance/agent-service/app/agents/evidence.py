from app.agents.schemas import AdditionalInfo


def merge_info(previous: AdditionalInfo, current: AdditionalInfo) -> AdditionalInfo:
    """合并产品和条款信息。"""
    result = dict(previous)
    if not current:
        return result

    for key, value in current.items():
        if key == "sources":
            # 合并字典
            result[key] = {**result.get(key, {}), **value}
        elif key in ("candidate_products", "plan_items"):
            # 得到唯一产品列表
            products = {
                str(item.get("product_id", item.get("id"))): item
                for item in [*result.get(key, []), *value]
            }
            result[key] = list(products.values())
        else:
            result[key] = value
    return result


def collect_sources(additional_info: dict[str, AdditionalInfo]) -> AdditionalInfo:
    """从各条消息的附加信息中收集来源。"""
    sources = {}
    for info in additional_info.values():
        sources.update(info.get("sources", {}))
    return sources


def referenced_sources(content: str, sources: AdditionalInfo) -> AdditionalInfo:
    """只补充正文实际引用的历史来源。"""
    return {
        source_id: source
        for source_id, source in sources.items()
        if f"[{source_id}]" in content
    }
