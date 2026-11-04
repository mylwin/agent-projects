"""百度行政区及地点查询客户端。"""

from datetime import UTC, datetime
from typing import Any

import httpx

from backend.schemas.planner_result import QueriedPlace


class BaiduMapClient:
    """
    使用调用方管理的 HTTP 连接查询百度地图。

    Attributes:
        http: 调用方负责关闭的异步 HTTP 客户端。
    """

    def __init__(self, api_key: str, http: httpx.AsyncClient) -> None:
        """
        注入百度地图服务密钥和 HTTP 连接。

        :param self: 当前客户端。
        :param api_key: 百度地图 Web 服务 AK。
        :param http: 调用方管理的异步 HTTP 客户端。
        """
        self._api_key = api_key
        self.http = http

    async def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        """
        查询百度地图并隐藏可能包含密钥的异常 URL。

        :param self: 当前客户端。
        :param path: 百度地图接口路径。
        :param params: 不包含 AK 的查询参数。
        :return: 成功的供应商响应。
        :raises RuntimeError: 网络、响应格式或供应商错误时抛出。
        """
        try:
            response = await self.http.get(
                "https://api.map.baidu.com" + path,
                params={**params, "ak": self._api_key, "output": "json"},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError):
            raise RuntimeError("百度地图查询失败，请检查网络与服务配置") from None
        if not isinstance(data, dict) or data.get("status") != 0:
            raise RuntimeError("百度地图拒绝查询，请检查 AK、权限与额度")
        return data

    async def resolve_region(self, query: str) -> str:
        """
        解析唯一的国内城市或区县，存在同名结果时拒绝猜测。

        :param self: 当前客户端。
        :param query: 用户输入的城市或区县名称。
        :return: 可供百度地点检索使用的区域名称。
        :raises ValueError: 区域不唯一或当前数据源无法解析时抛出。
        """
        data = await self._get(
            "/api_region_search/v1/", {"keyword": query, "sub_admin": "0"}
        )
        districts = data.get("districts")
        if not isinstance(districts, list):
            raise TypeError("百度地图行政区查询返回格式异常")
        names = {query, query + "市", query + "区", query + "县"}
        matches = [
            item
            for item in districts
            if isinstance(item, dict)
            and item.get("name") in names
            and str(item.get("level")) in {"2", "3"}
        ]
        if len(matches) != 1 or not isinstance(matches[0].get("name"), str):
            raise ValueError("目的地未能唯一解析，请提供明确的国内城市或区县")
        # 百度地点检索接受区域名称；不能将高德行政区编码当作百度 cityCode。
        return matches[0]["name"]

    async def search_places(self, region: str, keywords: str) -> list[QueriedPlace]:
        """
        限定行政区域查询候选地点，返回国测局经纬度。

        :param self: 当前客户端。
        :param region: 百度行政区查询解析出的区域名称。
        :param keywords: 景点、餐饮或地点关键词。
        :return: 最多五个有效地点。
        :raises RuntimeError: 供应商响应结构异常时抛出。
        """
        data = await self._get(
            "/place/v2/search",
            {
                "query": keywords,
                "region": region,
                "city_limit": "true",
                "ret_coordtype": "gcj02ll",
                "page_size": "5",
            },
        )
        results = data.get("results")
        if not isinstance(results, list):
            raise TypeError("百度地点检索返回格式异常")
        places = []
        for item in results[:5]:
            try:
                location = item["location"]
                places.append(
                    QueriedPlace(
                        id=item["uid"],
                        name=item["name"],
                        address=item.get("address")
                        if isinstance(item.get("address"), str)
                        else "",
                        longitude=location["lng"],
                        latitude=location["lat"],
                        source="baidu",
                        coordinate_system="GCJ-02",
                        fetched_at=datetime.now(UTC),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return places
