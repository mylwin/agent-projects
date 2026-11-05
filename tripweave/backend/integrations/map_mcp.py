"""地图 MCP 客户端工厂：只切换官方服务地址，不重写地图 Web API。"""

from dataclasses import dataclass
from urllib.parse import urlencode

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import StreamableHttpConnection

from backend.config.planner import PlannerSettings


@dataclass(frozen=True)
class MapTools:
    """同一 MCP 会话内发现的地图工具和供应商信息。"""

    provider: str
    tools: list[BaseTool]


def create_map_mcp(settings: PlannerSettings) -> MultiServerMCPClient:
    """工厂按供应商创建官方 Streamable HTTP 客户端，不在此发起连接。"""
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
    }
    return MultiServerMCPClient({settings.map_provider: connection})
