from langchain_milvus import Milvus
from pymilvus import Function, FunctionType

from app.core.logging import get_logger
from app.infra.database import AsyncSessionFactory
from app.rag.models import ParentChunk
from app.rag.repository import ParentChunkRepository

logger = get_logger(__name__)


def create_reranker(query: str) -> Function:
    """milvus的reranker function,这里采用[阿里]的重排模型"""
    return Function(
        name="dashscope_semantic_reranker",
        input_field_names=["text"],
        function_type=FunctionType.RERANK,
        params={
            "reranker": "model",
            "provider": "ali",
            "model_name": "gte-rerank-v2",
            "queries": [query],
            "max_client_bath_size": 5,
        },
    )


class ParentChunkRetrieval:
    """父chunk检索"""

    def __init__(self, vector_store: Milvus):
        self._vector_store = vector_store
        logger.info("RAG Retrieval 初始化完成✅")

    async def retrieve(self, query: str, k: int, product_id: int) -> list[ParentChunk]:
        # 1.在指定产品下混合检索得到子块
        children_chunks = await self._vector_store.asimilarity_search(
            query=query,
            k=k,
            fetch_k=10,
            expr=f"product_id=={product_id}",
            reranker=create_reranker(query),
        )

        # 2.提取父块的id,按照召回顺序进行去重
        parent_ids = list(
            dict.fromkeys(child.metadata["parent_id"] for child in children_chunks)
        )
        if not parent_ids:
            return []

        # 3.根据id列表查询父块
        async with AsyncSessionFactory() as session, session.begin():
            parent_chunk_repository = ParentChunkRepository(session)
            parent_chunks = await parent_chunk_repository.list_by_ids(parent_ids)

        # 4.根据子块检索顺序重新拼装
        if parent_chunks is not None:
            parent_chunk_map = {str(parent.id): parent for parent in parent_chunks}

        return [parent_chunk_map[parent_id] for parent_id in parent_ids]
