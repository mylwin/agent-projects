"""将产品条款注入 RAG 知识库。"""

import asyncio
import sys
from pathlib import Path

# 支持从任意工作目录直接运行脚本。
service_root = Path(__file__).resolve().parents[1]
if str(service_root) not in sys.path:
    sys.path.insert(0, str(service_root))

from app.core.config import APP_ROOT, settings
from app.core.logging import get_logger, setup_logging
from app.infra.database import AsyncSessionFactory, close_database
from app.modules.product.service import ProductService
from app.rag.pipeline import RAGPipeline
from langchain_milvus import BM25BuiltInFunction, Milvus
from langchain_ollama import OllamaEmbeddings

logger = get_logger(__name__)

# Ollama 向量模型服务地址，使用本机服务时改为 http://127.0.0.1:11434。
OLLAMA_URL = "http://10.40.0.31:11434"


def create_pipeline() -> RAGPipeline:
    """初始化稠密向量、BM25 稀疏向量和入库流水线。"""
    embeddings = OllamaEmbeddings(
        model="qwen3-embedding:0.6b",
        dimensions=1024,
        base_url=OLLAMA_URL,
    )
    vector_store = Milvus(
        embedding_function=embeddings,
        collection_name="insurance_collection",
        builtin_function=BM25BuiltInFunction(analyzer_params={"type": "chinese"}),
        vector_field=["dense", "sparse"],
        connection_args={"uri": settings.rag.milvus_url},
        auto_id=True,
    )
    return RAGPipeline(vector_store)


async def ingest_products() -> int:
    """查询产品并逐个注入，返回失败的产品数量。"""

    async with AsyncSessionFactory() as session:
        products = await ProductService(session).list_products(category=None)

    if not products:
        logger.info("没有需要注入的产品")
        return 0
    logger.info("开始构建 RAG 知识库")
    logger.info(f"产品条款目录：{APP_ROOT / 'data' / 'raw' / 'kb'}")
    pipeline = create_pipeline()
    failures = 0
    for product in products:
        logger.info(f"开始注入产品：{product.id} {product.name}")
        try:
            await pipeline.ingest(product)
        except Exception:
            failures += 1
            logger.exception(f"产品注入失败：{product.id} {product.name}")
        else:
            logger.info(f"产品注入完成：{product.id} {product.name}")

    logger.info(f"注入结束：共 {len(products)} 个产品，失败 {failures} 个")
    logger.info("RAG 知识库构建完成")
    return failures


async def main() -> int:
    """运行注入任务并释放数据库连接。"""
    try:
        return await ingest_products()
    finally:
        await close_database()


if __name__ == "__main__":
    setup_logging(settings.logging.level)
    sys.exit(1 if asyncio.run(main()) else 0)
