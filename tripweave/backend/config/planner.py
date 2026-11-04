"""从环境变量读取最小模型与地图配置。"""

import os
from dataclasses import dataclass, field

# 一轮规划的总时长上限。单次模型请求另有独立超时，这里约束整轮耗时。
DEFAULT_PLANNER_TIMEOUT_SECONDS = 300.0


@dataclass(frozen=True)
class PlannerSettings:
    """
    首次行程生成所需的服务配置。

    Attributes:
        model_api_key: 模型密钥，不参与对象的文本展示。
        amap_api_key: 高德 Web 服务密钥，不参与对象的文本展示。
        model_name: 支持工具调用的模型名称。
        model_base_url: 模型服务的 OpenAI 兼容接口地址。
        map_provider: 地图供应商，默认 amap，也支持 baidu。
        baidu_api_key: 百度地图 Web 服务 AK，不参与对象的文本展示。
        model_timeout_seconds: 单次模型请求的超时秒数，默认 60。
        planner_timeout_seconds: 整轮规划的总超时秒数，默认 300。
        model_enable_thinking: 是否开启思考链；None 表示不发送该参数。
        model_thinking_budget: 思考链最大 token 数；None 表示不发送该参数。
    """

    model_api_key: str = field(repr=False)
    amap_api_key: str = field(repr=False)
    model_name: str = "qwen-plus"
    model_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    map_provider: str = "amap"
    baidu_api_key: str = field(default="", repr=False)
    model_timeout_seconds: float = 60.0
    planner_timeout_seconds: float = DEFAULT_PLANNER_TIMEOUT_SECONDS
    model_enable_thinking: bool | None = None
    model_thinking_budget: int | None = None

    @classmethod
    def from_env(cls) -> "PlannerSettings":
        """
        读取并检查运行所需的环境变量。

        :param cls: 当前配置类。
        :return: 不包含隐式本地文件读取的配置对象。
        :raises ValueError: 模型或地图凭证缺失时抛出，仅显示变量名。
        """
        provider = os.getenv("MAP_PROVIDER", "amap").strip().lower()
        if provider not in {"amap", "baidu"}:
            raise ValueError("MAP_PROVIDER 仅支持 amap 或 baidu")
        map_key_name = "AMAP_API_KEY" if provider == "amap" else "BAIDU_MAP_API_KEY"
        values = {
            "MODEL_API_KEY": os.getenv("MODEL_API_KEY", "").strip(),
            map_key_name: os.getenv(map_key_name, "").strip(),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise ValueError("缺少环境变量：" + "、".join(missing))
        return cls(
            model_api_key=values["MODEL_API_KEY"],
            amap_api_key=values[map_key_name] if provider == "amap" else "",
            baidu_api_key=values[map_key_name] if provider == "baidu" else "",
            map_provider=provider,
            model_name=os.getenv("MODEL_NAME", "qwen-plus").strip() or "qwen-plus",
            model_base_url=os.getenv(
                "MODEL_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ).strip(),
            model_timeout_seconds=_read_positive_seconds("MODEL_TIMEOUT_SECONDS", 60.0),
            planner_timeout_seconds=_read_positive_seconds(
                "PLANNER_TIMEOUT_SECONDS", DEFAULT_PLANNER_TIMEOUT_SECONDS
            ),
            model_enable_thinking=_read_optional_bool("MODEL_ENABLE_THINKING"),
            model_thinking_budget=_read_optional_positive_int("MODEL_THINKING_BUDGET"),
        )


def _read_positive_seconds(name: str, default: float) -> float:
    """
    读取以秒为单位的正数环境变量。

    模型首次响应包含系统提示、工具定义和完整需求，耗时波动较大，
    因此超时通过环境变量调整，不在代码中写死。

    :param name: 环境变量名，用于错误提示。
    :param default: 变量未设置或为空时使用的默认值。
    :return: 大于零的秒数。
    :raises ValueError: 变量不是正数时抛出。
    """
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{name} 必须是大于 0 的秒数") from None
    if value <= 0:
        raise ValueError(f"{name} 必须是大于 0 的秒数")
    return value


def _read_optional_bool(name: str) -> bool | None:
    """
    读取可选的布尔开关，未设置或为 auto 时返回 None。

    思考链参数只被部分供应商和模型支持，默认不发送，避免不支持的接口报错。

    :param name: 环境变量名，用于错误提示。
    :return: True、False 或 None（不发送该参数）。
    :raises ValueError: 取值无法识别时抛出。
    """
    raw = os.getenv(name, "").strip().lower()
    if not raw or raw == "auto":
        return None
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} 仅支持 auto、true 或 false")


def _read_optional_positive_int(name: str) -> int | None:
    """
    读取可选的正整数环境变量，未设置时返回 None。

    :param name: 环境变量名，用于错误提示。
    :return: 大于零的整数或 None。
    :raises ValueError: 变量不是正整数时抛出。
    """
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} 必须是大于 0 的整数") from None
    if value <= 0:
        raise ValueError(f"{name} 必须是大于 0 的整数")
    return value
