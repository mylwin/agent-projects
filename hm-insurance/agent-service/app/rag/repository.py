from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.models import ParentChunk


class ParentChunkRepository:
    """父块知识块数据库操作"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def delete_by_product_id(self, product_id: int) -> None:
        """根据产品 id 删除所有父块知识块"""
        await self.session.execute(
            delete(ParentChunk).where(ParentChunk.product_id == product_id)
        )

    def add_all(self, parent_chunks: list[ParentChunk]) -> None:
        """批量添加父块知识块"""
        self.session.add_all(parent_chunks)

    async def list_by_ids(self, ids: list[str]) -> list[ParentChunk] | None:
        """根据 id 列表查询父块知识块"""
        result = await self.session.scalars(
            select(ParentChunk).where(ParentChunk.id.in_(ids))
        )
        return list(result.all())
