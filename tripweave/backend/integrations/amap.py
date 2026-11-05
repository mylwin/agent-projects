"""高德国内行政区及地点查询，首版不查询路线和天气。"""

from datetime import UTC, datetime
from typing import Any

import httpx

from backend.schemas.trip import Place


class AmapClient:
    """
    使用调用方管理的 HTTP 连接查询高德。

    Attributes:
        http: 调用方负责关闭的异步 HTTP 客户端。
    """

    def __init__(self, api_key: str, http: httpx.AsyncClient) -> None:
        """
        注入凭证与 HTTP 连接，避免在模块导入时创建外部连接。

        :param self: 当前高德客户端。
        :param api_key: 高德 Web 服务密钥。
        :param http: 可替换为测试传输层的 HTTP 客户端。
        """
        self._api_key = api_key
        self.http = http

    async def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        """
        发起有超时限制的查询，并隐藏异常中的凭证 URL。

        :param self: 当前高德客户端。
        :param path: 高德接口路径，不允许调用方提供任意主机。
        :param params: 不包含密钥的查询参数。
        :return: 成功的供应商 JSON 响应。
        :raises RuntimeError: 网络、响应格式或供应商查询失败时抛出。
        """
        try:
            response = await self.http.get(
                "https://restapi.amap.com" + path,
                params={**params, "key": self._api_key},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError):
            raise RuntimeError("高德查询失败，请检查网络与服务配置") from None
        if not isinstance(data, dict) or data.get("status") != "1":
            raise RuntimeError("高德拒绝查询，请检查 Web 服务密钥、权限与额度")
        return data

    async def resolve_region(self, query: str) -> str:
        """
        将明确国内城市或区县解析为查询范围，歧义时要求补充信息。

        :param self: 当前高德客户端。
        :param query: 目的地城市或区县名称，不使用苏州白名单。
        :return: 唯一匹配区域的高德行政区编码。
        :raises ValueError: 地区不明确、范围过大或供应商没有覆盖时抛出。
        """
        data = await self._get(
            "/v3/config/district",
            {"keywords": query, "subdistrict": "0", "extensions": "base"},
        )
        districts = data.get("districts", [])
        matches = [
            item
            for item in districts
            if isinstance(item, dict)
            and item.get("name")
            in {query, query + "市", query + "区", query + "县", query + "特别行政区"}
            and (
                item.get("level") in {"city", "district"}
                or item.get("name")
                in {
                    "北京市",
                    "天津市",
                    "上海市",
                    "重庆市",
                    "香港特别行政区",
                    "澳门特别行政区",
                }
            )
        ]
        if len(matches) != 1 or not isinstance(matches[0].get("adcode"), str):
            raise ValueError(
                "目的地未能唯一解析，请提供明确的国内城市或区县；数据源也可能暂无覆盖"
            )
        return matches[0]["adcode"]

    async def search_places(self, region: str, keywords: str) -> list[Place]:
        """
        在已确定的行政区中检索有限数量的真实地点。

        :param self: 当前高德客户端。
        :param region: 目的地解析得到的行政区编码。
        :param keywords: 景点、美食或具体地点的查询关键词。
        :return: 最多五个具有有效标识与坐标的地点。
        """
        data = await self._get(
            "/v3/place/text",
            {
                "keywords": keywords,
                "city": region,
                "citylimit": "true",
                "offset": "5",
                "page": "1",
                "extensions": "base",
            },
        )
        places = []
        prefix = (
            region[:2]
            if region.endswith("0000")
            else (region[:4] if region.endswith("00") else region)
        )
        for item in data.get("pois", [])[:5]:
            try:
                # 防止供应商意外返回其他区域的同名地点。
                if not isinstance(item.get("adcode"), str) or not item[
                    "adcode"
                ].startswith(prefix):
                    continue
                longitude, latitude = item["location"].split(",")
                places.append(
                    Place(
                        id=item["id"],
                        name=item["name"],
                        address=(
                            item["address"]
                            if isinstance(item.get("address"), str)
                            else ""
                        ),
                        longitude=float(longitude),
                        latitude=float(latitude),
                        fetched_at=datetime.now(UTC),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return places
