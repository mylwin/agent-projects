"""验证行程草稿的日期、地点引用与时间顺序校验。"""

import unittest
from datetime import UTC, date, datetime

from backend.schemas.planner_result import (
    ActivityPlan,
    DayPlan,
    QueriedPlace,
    TravelDraft,
)
from backend.services.planning import prepare_requirements
from backend.tests.agents.planner.test_planner import make_request
from backend.validators.planner import validate_draft


def _draft(
    place_id: str = "poi-1",
    day: date = date(2027, 3, 12),
    times: tuple[str, ...] = ("10:00",),
) -> TravelDraft:
    """
    构造一份只含一天的结构化草稿。

    :param place_id: 活动引用的地点 ID。
    :param day: 活动日期。
    :param times: 按顺序放入当天的活动开始时间。
    :return: 可通过结构校验的草稿。
    """
    return TravelDraft(
        days=[
            DayPlan(
                date=day,
                title="城市慢游",
                activities=[
                    ActivityPlan(
                        time=time,
                        title="游览测试地点",
                        description="仅用于校验测试",
                        place_id=place_id,
                    )
                    for time in times
                ],
            )
        ]
    )


def _place(place_id: str = "poi-1") -> QueriedPlace:
    """
    构造本轮查询到的候选地点。

    :param place_id: 地点 ID。
    :return: 带坐标、来源和查询时间的候选地点。
    """
    return QueriedPlace(
        id=place_id,
        name="测试地点",
        address="测试地址",
        longitude=104.06,
        latitude=30.67,
        fetched_at=datetime(2026, 11, 4, tzinfo=UTC),
    )


class ValidateDraftTests(unittest.TestCase):
    """覆盖校验器的通过与拒绝路径。"""

    def setUp(self) -> None:
        """准备一份日期已补齐的行程需求。"""
        self.requirements = prepare_requirements(make_request())

    def test_returns_used_place_ids(self) -> None:
        """
        合法草稿返回实际引用的地点 ID 集合。

        :param self: 当前测试实例。
        """
        used = validate_draft(
            _draft(), self.requirements, {"poi-1": _place()}
        )
        self.assertEqual(used, {"poi-1"})

    def test_rejects_wrong_date_and_unknown_place(self) -> None:
        """
        日期不一致或引用未查询地点时拒绝。

        :param self: 当前测试实例。
        """
        with self.assertRaisesRegex(ValueError, "日期或天数"):
            validate_draft(
                _draft(day=date(2027, 3, 13)),
                self.requirements,
                {"poi-1": _place()},
            )
        with self.assertRaisesRegex(ValueError, "未经本轮查询"):
            validate_draft(
                _draft(place_id="invented"),
                self.requirements,
                {"poi-1": _place()},
            )

    def test_rejects_unordered_or_duplicate_times(self) -> None:
        """
        活动开始时间乱序或重复时拒绝。

        :param self: 当前测试实例。
        """
        with self.assertRaisesRegex(ValueError, "按顺序"):
            validate_draft(
                _draft(times=("11:00", "10:00")),
                self.requirements,
                {"poi-1": _place()},
            )
        with self.assertRaisesRegex(ValueError, "按顺序"):
            validate_draft(
                _draft(times=("10:00", "10:00")),
                self.requirements,
                {"poi-1": _place()},
            )
