"""验证 Planner 输入的字段边界与 JSON 契约。"""

import json
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from pydantic import ValidationError

from backend.schemas.planner_input import (
    BudgetRequirement,
    PlannerInput,
    TravelRequirements,
)


def make_example() -> dict:
    """
    读取可直接运行的 CLI 示例，避免样本与测试漂移。

    :return: 示例输入的可变字典副本。
    """
    path = (
        Path(__file__).resolve().parents[2]
        / "agents/planner/examples/generate.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


class PlannerInputTests(unittest.TestCase):
    """
    覆盖首次生成输入的字段边界与序列化行为。
    """

    def test_example_and_json_round_trip(self) -> None:
        """
        示例输入可被读取，序列化后不改变日期与精确金额。

        :param self: 当前测试用例实例。
        """
        request = PlannerInput.model_validate(make_example())
        self.assertEqual(request.requirements.start_date, date(2027, 3, 12))
        self.assertEqual(request.requirements.budget.amount, Decimal("3000.00"))
        self.assertEqual(
            request, PlannerInput.model_validate_json(request.model_dump_json())
        )
        self.assertEqual(
            request.model_dump(mode="json")["requirements"]["budget"]["amount"],
            "3000.00",
        )

    def test_missing_requirements_remain_available_for_clarification(self) -> None:
        """
        允许不完整需求和未知预算口径，不替用户填充事实。

        :param self: 当前测试用例实例。
        """
        request = PlannerInput(
            operation="generate", requirements={"budget": {"amount": "100"}}
        )
        self.assertIsNone(request.requirements.destination)
        self.assertIsNone(request.requirements.start_date)
        self.assertIsNone(request.requirements.budget.scope)
        self.assertEqual(request.requirements.preferences.interests, [])

    def test_no_suzhou_allowlist_and_original_instruction_preserved(self) -> None:
        """
        全国地点查询不依赖城市白名单，用户原话不被裁剪改写。

        :param self: 当前测试用例实例。
        """
        for destination in ("成都", "喀什", "香港", "朝阳"):
            with self.subTest(destination=destination):
                request = PlannerInput(
                    operation="generate",
                    instruction="  想轻松一点  ",
                    requirements={"destination": {"query": destination}},
                )
                self.assertEqual(request.requirements.destination.query, destination)
                self.assertEqual(request.instruction, "  想轻松一点  ")

    def test_rejects_extra_fields_at_each_input_layer(self) -> None:
        """
        防止拼错字段或注入执行策略被静默忽略。

        :param self: 当前测试用例实例。
        """
        cases = [
            {"owner_id": "someone"},
            {"max_model_calls": 1000},
            {"requirements": {"destination": {"query": "成都", "latitude": 30}}},
            {"requirements": {"budget": {"amount": "100", "curreny": "CNY"}}},
        ]
        for extra in cases:
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                PlannerInput.model_validate(
                    {"operation": "generate", "requirements": {}, **extra}
                )

    def test_rejects_scalar_coercion_and_invalid_ranges(self) -> None:
        """
        人数、天数和日期不接受布尔、数字字符串或时间戳替代。

        :param self: 当前测试用例实例。
        """
        cases = [
            {"travelers": True},
            {"travelers": "2"},
            {"travelers": 13},
            {"day_count": 0},
            {"day_count": 6},
            {"start_date": "2027-02-29"},
            {"start_date": 1800000000},
            {"start_date": datetime(2027, 3, 12)},
            {"destination": {"query": "   "}},
        ]
        for fields in cases:
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                TravelRequirements.model_validate(fields)

    def test_rejects_lossy_or_non_finite_money(self) -> None:
        """
        金额只接受精确十进制输入，拒绝非法小数与无穷值。

        :param self: 当前测试用例实例。
        """
        for amount in (
            0,
            3000.1,
            True,
            "0",
            "-1",
            "3.001",
            "NaN",
            "1e3",
            Decimal("Infinity"),
        ):
            with self.subTest(amount=amount), self.assertRaises(ValidationError):
                BudgetRequirement(amount=amount)
        self.assertEqual(
            BudgetRequirement(amount=Decimal("10.20")).amount, Decimal("10.20")
        )

    def test_date_interval_consistency(self) -> None:
        """
        拒绝倒置或相互矛盾的结构化日期，保留未填的派生字段。

        :param self: 当前测试用例实例。
        """
        valid = TravelRequirements(start_date="2028-02-28", end_date="2028-03-01")
        self.assertIsNone(valid.day_count)
        cases = [
            {"start_date": "2027-03-13", "end_date": "2027-03-12"},
            {"start_date": "2027-03-12", "end_date": "2027-03-14", "day_count": 2},
            {"start_date": "2027-03-12", "end_date": "2027-03-17"},
        ]
        for fields in cases:
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                TravelRequirements.model_validate(fields)

    def test_mutable_defaults_are_not_shared(self) -> None:
        """
        两次调用的偏好列表互不共享。

        :param self: 当前测试用例实例。
        """
        first = PlannerInput(operation="generate", requirements={})
        second = PlannerInput(operation="generate", requirements={})
        first.requirements.preferences.interests.append("历史")
        self.assertEqual(second.requirements.preferences.interests, [])

    def test_only_generate_operation_is_accepted(self) -> None:
        """
        局部修改尚未实现，输入模型直接拒绝其他操作类型。

        :param self: 当前测试用例实例。
        """
        with self.assertRaises(ValidationError):
            PlannerInput.model_validate({"operation": "modify", "requirements": {}})
