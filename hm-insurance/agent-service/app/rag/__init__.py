from langchain_milvus import BM25BuiltInFunction, Milvus
from langchain_ollama import OllamaEmbeddings

from app.core.config import settings
from app.rag.pipeline import RAGPipeline
from app.rag.retrieval import ParentChunkRetrieval

# 1.初始化向量模型
_embeddings = OllamaEmbeddings(
    model="qwen3-embedding:0.6b", dimensions=1024, base_url="http://10.40.0.31:11434"
)

# 2.初始化vector_store
_vector_store = Milvus(
    embedding_function=_embeddings,
    collection_name="insurance_collection",
    builtin_function=BM25BuiltInFunction(analyzer_params={"type": "chinese"}),
    vector_field=["dense", "sparse"],
    connection_args={"uri": settings.rag.milvus_url},
    auto_id=True,
)

# 3.创建模块级Pipeline和Retriever
pipeline = RAGPipeline(_vector_store)
retrieval = ParentChunkRetrieval(_vector_store)


def close_rag() -> None:
    """关闭RAG组件"""
    pipeline.close()
    _vector_store.client.close()


__all__ = ["close_rag", "pipeline", "retrieval"]
