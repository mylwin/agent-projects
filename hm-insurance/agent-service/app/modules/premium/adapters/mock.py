from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.modules.premium.adapters.base import PricingRequest, PricingResult
from app.modules.premium.exceptions import PriceParamsInvalidError


class MockPricingAdapter:
    """按 product_pricing_bindings.mock_config 计价的 mock 适配器"""

    pricing_mode = "mock_adapter"

    async def quote(
        self, request: PricingRequest, mock_config: dict[str, Any]
    ) -> PricingResult:
        # 试算的数据
        payload = request.payload
        # 获取计划编码
        plan_code = str(payload.get("packageCode") or "basic")
        # 得到基础保费
        base = mock_config["base_premium_by_plan"].get(plan_code)
        if base is None:
            raise PriceParamsInvalidError(f"不支持的计划编码：{plan_code}")
        # 根据mocked_config的要求进行因子计算
        factor = Decimal(1)
        factor *= _range_factor(mock_config["age_factor"], int(payload["age"]))
        factor *= _map_factor(mock_config.get("gender_factor"), payload.get("gender"))
        factor *= _map_factor(
            mock_config.get("social_security_factor"),
            payload.get("hasSocialSecurity"),
        )
        factor *= _map_factor(
            mock_config.get("occupation_factor"), payload.get("occupationClass")
        )
        factor *= _map_factor(
            mock_config.get("deductible_factor"), payload.get("deductible")
        )
        # 如果启用了保额系数，则按保额进行计算
        if mock_config["coverage_factor_enabled"]:
            unit = Decimal(str(mock_config["coverage_unit"]))
            amount = Decimal(str(payload["sumInsured"]))
            factor *= amount / unit
        # 计算一年的保费(四舍五入)
        annual = (Decimal(str(base)) * factor).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        # 返回结果
        return PricingResult(
            annual_premium=annual,
            payment_frequency="annual",
            breakdown=[
                {
                    "item": "main",
                    "name": plan_code,
                    "premium": f"{annual:.2f}",
                    "source": {"adapter": request.adapter_code, "mode": "mock"},
                }
            ],
            raw={
                "base_premium": str(base),
                "factor": str(factor),
                "plan_code": plan_code,
                "payload": payload,
            },
        )


def _range_factor(ranges: list[dict[str, Any]], age: int) -> Decimal:
    """年龄落在哪个区间，就取该区间系数；没有命中按 1.0。"""
    for item in ranges:
        if item["min"] <= age <= item["max"]:
            return Decimal(str(item["factor"]))
    return Decimal(1)


def _map_factor(mapping: dict[str, Any] | None, value: Any) -> Decimal:
    """性别/社保/职业/免赔额这类枚举系数；没有配置按 1.0。"""
    if mapping is None or value is None:
        return Decimal(1)
    factor = mapping.get(str(value))
    return Decimal(str(factor)) if factor is not None else Decimal(1)
