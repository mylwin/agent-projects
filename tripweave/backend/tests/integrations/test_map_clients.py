"""地图供应商工厂及百度 API 适配测试。"""

import unittest
from unittest.mock import patch

import httpx

from backend.config.planner import PlannerSettings
from backend.integrations.amap import AmapClient
from backend.integrations.baidu import BaiduMapClient
from backend.integrations.map_client import create_map_client
from backend.services.planning import plan_trip
from backend.tests.agents.planner.test_planner import (
    ToolCallingModel,
    draft_message,
    make_request,
)


def baidu_response(request: httpx.Request) -> httpx.Response:
    """
    返回百度地图接口的合成数据并检查请求参数。

    :param request: 客户端发出的请求。
    :return: 无需外部访问的响应。
    """
    assert request.url.params["ak"] == "test-key"
    if request.url.path == "/api_region_search/v1/":
        return httpx.Response(
            200,
            json={
                "status": 0,
                "districts": [
                    {"name": "成都市", "level": 2, "code": 510100},
                ],
            },
        )
    assert request.url.path == "/place/v2/search"
    assert request.url.params["region"] == "成都市"
    assert request.url.params["city_limit"] == "true"
    assert request.url.params["ret_coordtype"] == "gcj02ll"
    return httpx.Response(
        200,
        json={
            "status": 0,
            "results": [
                {
                    "uid": "baidu-poi",
                    "name": "测试地点",
                    "address": "测试地址",
                    "location": {"lng": 104.06, "lat": 30.67},
                },
            ],
        },
    )


class MapClientTests(unittest.IsolatedAsyncioTestCase):
    """覆盖供应商选择、百度查询和故障边界。"""

    async def test_factory_and_baidu_lookup(self) -> None:
        """
        工厂构造两种客户端，百度返回统一地点类型和真实来源标记。

        :param self: 当前测试实例。
        """
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(baidu_response)
        ) as http:
            self.assertIsInstance(create_map_client("amap", "key", http), AmapClient)
            client = create_map_client("baidu", "test-key", http)
            self.assertIsInstance(client, BaiduMapClient)
            region = await client.resolve_region("成都")
            places = await client.search_places(region, "景点")
            self.assertEqual(region, "成都市")
            self.assertEqual(places[0].id, "baidu-poi")
            self.assertEqual(places[0].source, "baidu")
            self.assertEqual(places[0].coordinate_system, "GCJ-02")
            self.assertEqual(places[0].longitude, 104.06)
            with self.assertRaises(ValueError):
                create_map_client("unknown", "key", http)
            with self.assertRaises(ValueError):
                create_map_client("baidu", "", http)

    async def test_ambiguous_region_and_supplier_error(self) -> None:
        """
        多个同名区域不能被静默选择，错误中不暴露密钥。

        :param self: 当前测试实例。
        """
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(baidu_response)
        ) as http:
            client = BaiduMapClient("private-key", http)
            with patch.object(
                client,
                "_get",
                return_value={
                    "districts": [
                        {"name": "朝阳区", "level": 3},
                        {"name": "朝阳区", "level": 3},
                    ]
                },
            ):
                with self.assertRaises(ValueError):
                    await client.resolve_region("朝阳")
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(403))
        ) as http:
            with self.assertRaises(RuntimeError) as caught:
                await BaiduMapClient("private-key", http).resolve_region("成都")
            self.assertNotIn("private-key", str(caught.exception))

    async def test_baidu_runs_through_agent(self) -> None:
        """
        百度客户端可供同一个 Agent 执行工具调用并返回来源。

        :param self: 当前测试实例。
        """
        model = ToolCallingModel(responses=[draft_message("baidu-poi")])
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(baidu_response)
        ) as http:
            result = await plan_trip(
                make_request(), model, BaiduMapClient("test-key", http)
            )
        self.assertEqual(result.places[0].source, "baidu")
        self.assertEqual(result.itinerary.days[0].activities[0].place_id, "baidu-poi")

    def test_selected_provider_requires_only_its_key(self) -> None:
        """
        只读取选中供应商的密钥，保留默认高德配置兼容。

        :param self: 当前测试实例。
        """
        with patch.dict(
            "os.environ", {"MODEL_API_KEY": "model", "AMAP_API_KEY": "amap"}, clear=True
        ):
            self.assertEqual(PlannerSettings.from_env().map_provider, "amap")
        with patch.dict(
            "os.environ",
            {
                "MODEL_API_KEY": "model",
                "MAP_PROVIDER": "baidu",
                "BAIDU_MAP_API_KEY": "private-baidu-key",
            },
            clear=True,
        ):
            settings = PlannerSettings.from_env()
            self.assertEqual(settings.baidu_api_key, "private-baidu-key")
            self.assertNotIn("private-baidu-key", repr(settings))
        with patch.dict(
            "os.environ",
            {"MODEL_API_KEY": "model", "MAP_PROVIDER": "baidu", "AMAP_API_KEY": "amap"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "BAIDU_MAP_API_KEY"):
                PlannerSettings.from_env()
