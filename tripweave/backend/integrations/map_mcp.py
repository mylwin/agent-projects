"""地图 MCP 客户端工厂：只切换官方服务地址，不重写地图 Web API。"""

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import StreamableHttpConnection

from backend.config.planner import PlannerSettings


@dataclass(frozen=True)
class MapTools:
    """
    同一 MCP 会话内发现的地图工具和供应商信息。

    Attributes:
        provider: 官方地图供应商标识，amap 或 baidu。
        tools: 当前会话发现的工具，研究 Agent 再按只读白名单筛选。
    """

    provider: str
    tools: list[BaseTool]


def _create_http_client(
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | None = None,
    auth: httpx.Auth | None = None,
) -> httpx.AsyncClient:
    """
    创建不读取系统代理的地图 MCP 客户端。

    :param headers: MCP 适配器传入的请求头。
    :param timeout: MCP 适配器传入的超时配置。
    :param auth: MCP 适配器传入的认证配置。
    :return: 不使用环境或系统代理的异步 HTTP 客户端。
    """
    return httpx.AsyncClient(
        trust_env=False,
        headers=headers,
        timeout=timeout,
        auth=auth,
    )


def create_map_mcp(settings: PlannerSettings) -> MultiServerMCPClient:
    """
    工厂按供应商创建官方 Streamable HTTP 客户端，不在此发起连接。

    :param settings: 地图供应商、对应凭据及整轮读取超时配置。
    :return: 尚未连接的官方地图 MCP 客户端，由调用方管理会话。
    :raises ValueError: 地图供应商不受支持或对应密钥为空。
    """
    if settings.map_provider == "amap":
        endpoint = "https://mcp.amap.com/mcp"
        credentials = {"key": settings.amap_api_key}
    elif settings.map_provider == "baidu":
        endpoint = "https://mcp.map.baidu.com/mcp"
        credentials = {"ak": settings.baidu_api_key}
    else:
        raise ValueError("MAP_PROVIDER 仅支持 amap 或 baidu")
    if not next(iter(credentials.values())).strip():
        raise ValueError("选定的地图 MCP 服务缺少密钥")
    connection: StreamableHttpConnection = {
        "transport": "streamable_http",
        "url": endpoint + "?" + urlencode(credentials),
        "timeout": 30,
        "sse_read_timeout": settings.planner_timeout_seconds,
        "httpx_client_factory": _create_http_client,
    }
    return MultiServerMCPClient({settings.map_provider: connection})
