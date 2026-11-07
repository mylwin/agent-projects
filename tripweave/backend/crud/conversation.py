"""项目对话轮次的数据库读写。"""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.conversation_turn import ConversationTurn


async def list_turns(
    db: AsyncSession, user_id: int, project_id: int, limit: int
) -> list[ConversationTurn]:
    """
    按时间正序读取当前用户项目最近若干轮对话。

    :param db: 当前事务的数据库会话。
    :param user_id: 当前用户 ID，用于过滤越权数据。
    :param project_id: 对话所属项目 ID。
    :param limit: 最多读取的轮次数量，须为正整数。
    :return: 从旧到新排列的对话轮次。
    """
    rows = await db.scalars(
        select(ConversationTurn)
        .where(
            ConversationTurn.project_id == project_id,
            ConversationTurn.user_id == user_id,
        )
        .order_by(ConversationTurn.id.desc())
        .limit(limit)
    )
    return list(reversed(list(rows)))


async def expire_running_turns(
    db: AsyncSession, project_id: int, now: datetime
) -> None:
    """
    把已超过截止时间的运行中轮次标记为失败。

    进程异常退出后没有代码写入终态，因此在新一轮开始前统一回收。

    :param db: 当前事务的数据库会话。
    :param project_id: 需要回收的项目 ID。
    :param now: 当前 UTC 无时区时间，用于比较截止时间并写入结束时间。
    """
    await db.execute(
        update(ConversationTurn)
        .where(
            ConversationTurn.project_id == project_id,
            ConversationTurn.status == "running",
            ConversationTurn.deadline_at < now,
        )
        .values(status="failed", error_code="conversation_interrupted", finished_at=now)
    )


async def create_turn(
    db: AsyncSession,
    *,
    project_id: int,
    user_id: int,
    base_revision_id: int,
    day_id: int,
    generate: bool,
    user_text: str,
    deadline_at: datetime,
) -> ConversationTurn:
    """
    写入一条运行中的对话轮次并回填主键。

    :param db: 当前事务的数据库会话。
    :param project_id: 对话所属项目 ID。
    :param user_id: 发起对话的用户 ID。
    :param base_revision_id: 本轮依据的行程版本 ID。
    :param day_id: 用户当前选中的行程日期 ID。
    :param generate: 本轮是否授权完整重新规划。
    :param user_text: 已通过接口校验的用户输入。
    :param deadline_at: 本轮最晚完成时间，UTC 无时区。
    :return: 已 flush 的对话轮次。
    """
    turn = ConversationTurn(
        project_id=project_id,
        user_id=user_id,
        base_revision_id=base_revision_id,
        day_id=day_id,
        generate=generate,
        user_text=user_text,
        assistant_text="",
        status="running",
        deadline_at=deadline_at,
    )
    db.add(turn)
    await db.flush()
    return turn


async def lock_turn(db: AsyncSession, turn_id: int) -> ConversationTurn | None:
    """
    读取并锁定一轮对话，避免终态被并发覆盖。

    :param db: 当前事务的数据库会话。
    :param turn_id: 对话轮次 ID。
    :return: 对话轮次，不存在时为 None。
    """
    return await db.scalar(
        select(ConversationTurn).where(ConversationTurn.id == turn_id).with_for_update()
    )


async def save_turn_result(
    db: AsyncSession,
    turn: ConversationTurn,
    *,
    assistant_text: str,
    status: str,
    result_revision_id: int | None,
    error_code: str | None,
    finished_at: datetime,
) -> None:
    """
    写入公开回复和终态；调用方须先通过 ``lock_turn`` 锁定该轮次。

    :param db: 当前事务的数据库会话。
    :param turn: 已锁定的对话轮次。
    :param assistant_text: 可公开的助手回复全文。
    :param status: 终态，取值见模型的状态约束。
    :param result_revision_id: 本轮生成的行程版本 ID，未生成时为 None。
    :param error_code: 失败或取消时的稳定错误码，成功时为 None。
    :param finished_at: 本轮结束时间，UTC 无时区。
    """
    turn.assistant_text = assistant_text
    turn.status = status
    turn.result_revision_id = result_revision_id
    turn.error_code = error_code
    turn.finished_at = finished_at
    await db.flush()
