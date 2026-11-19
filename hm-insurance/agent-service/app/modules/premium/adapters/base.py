from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol


@dataclass(slots=True)
class PricingRequest:
    """传给计价适配器的统一请求"""

    adapter_code: str
    external_product_code: str
    api_code: str
    payload: dict[str, Any]


@dataclass(slots=True)
class PricingResult:
    """计价适配器的统一结果"""

    annual_premium: Decimal
    payment_frequency: str
    breakdown: list[dict[str, Any]]
    raw: dict[str, Any]


class PricingAdapter(Protocol):
    """计价适配器协议"""

    pricing_mode: str

    async def quote(
        self, request: PricingRequest, mock_config: dict[str, Any]
    ) -> PricingResult: ...
