"""运行过程中面向调用方的可观察事件。"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class RunEvent:
    """所有运行事件的公共类型，``type`` 与未来 SSE 事件名保持一致。"""

    type: ClassVar[str]


@dataclass(frozen=True, slots=True)
class StageChanged(RunEvent):
    """
    业务阶段发生变化。

    Attributes:
        stage: 稳定阶段名，例如 resolving_destination、generating。
        message: 可直接展示的中文说明。
    """

    type: ClassVar[str] = "stage.changed"

    stage: str
    message: str


@dataclass(frozen=True, slots=True)
class ReasoningDelta(RunEvent):
    """
    模型思考链的一段增量文本。

    Attributes:
        text: 本次新增的思考内容。
        call_index: 触发该内容的模型调用序号。
    """

    type: ClassVar[str] = "reasoning.delta"

    text: str
    call_index: int


@dataclass(frozen=True, slots=True)
class MessageDelta(RunEvent):
    """
    模型面向用户回复的一段增量文本。

    Attributes:
        text: 本次新增的回复内容。
        call_index: 触发该内容的模型调用序号。
    """

    type: ClassVar[str] = "message.delta"

    text: str
    call_index: int


@dataclass(frozen=True, slots=True)
class ToolStarted(RunEvent):
    """
    模型开始提交一次工具调用。

    Attributes:
        name: 工具名，例如 TravelDraft。
        call_index: 触发该工具调用的模型调用序号。
    """

    type: ClassVar[str] = "tool.started"

    name: str
    call_index: int


@dataclass(frozen=True, slots=True)
class ToolFinished(RunEvent):
    """
    一次工具调用已经返回。

    Attributes:
        name: 工具名，例如 TravelDraft。
        call_index: 触发该工具调用的模型调用序号。
    """

    type: ClassVar[str] = "tool.finished"

    name: str
    call_index: int


# 调用方只依赖这组事件，后续 SSE 层再补充 run_id、seq 与 timestamp。
AgentEvent = (
    StageChanged | ReasoningDelta | MessageDelta | ToolStarted | ToolFinished
)

# 运行事件回调：运行时、业务层和 CLI 都通过这个类型接收事件。
EventSink = Callable[[AgentEvent], None]
