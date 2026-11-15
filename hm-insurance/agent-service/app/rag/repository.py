from app.rag.models import ParentChunk
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession


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
        self.session.add_all(parent_chunks)
