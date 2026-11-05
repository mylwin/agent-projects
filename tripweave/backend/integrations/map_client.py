"""地点查询接口及供应商工厂。"""

from typing import Protocol

import httpx

from backend.schemas.trip import Place


class MapClient(Protocol):
    """规划工具使用的行政区解析与地点检索接口。"""

    async def resolve_region(self, query: str) -> str:
        """
        解析唯一目的地区域。

        :param self: 当前地图客户端。
        :param query: 用户输入的城市或区县。
        :return: 当前供应商可用于检索的区域标识。
        """
        ...

    async def search_places(self, region: str, keywords: str) -> list[Place]:
        """
        在已解析区域内查询地点。

        :param self: 当前地图客户端。
        :param region: 当前供应商解析得到的区域标识。
        :param keywords: 搜索关键词。
        :return: 带来源和坐标系的候选地点。
        """
        ...


def create_map_client(
    provider: str, api_key: str, http: httpx.AsyncClient
) -> MapClient:
    """
    根据配置创建地图客户端。

    :param provider: 地图供应商，支持 amap 和 baidu。
    :param api_key: 对应供应商的 Web 服务密钥。
    :param http: 调用方管理的异步 HTTP 客户端。
    :return: 实现地点查询接口的客户端。
    :raises ValueError: 供应商不受支持或密钥为空时抛出。
    """
    if not api_key.strip():
        raise ValueError("地图服务密钥不能为空")
    if provider == "amap":
        from backend.integrations.amap import AmapClient

        return AmapClient(api_key, http)
    if provider == "baidu":
        from backend.integrations.baidu import BaiduMapClient

        return BaiduMapClient(api_key, http)
    raise ValueError("MAP_PROVIDER 仅支持 amap 或 baidu")
