from app.modules.premium.adapters.base import PricingAdapter
from app.modules.premium.adapters.mock import MockPricingAdapter

_ADAPTERS: dict[str, PricingAdapter] = {
    "mock": MockPricingAdapter(),
}


def get_adapter(adapter_type: str) -> PricingAdapter:
    """按 insurer_api_adapters.adapter_type 取计价适配器。"""
    return _ADAPTERS[adapter_type]
