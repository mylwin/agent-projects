from pathlib import Path
from uuid import uuid4

from app.core.config import APP_ROOT, settings
from app.core.logging import get_logger
from app.infra.database import AsyncSessionFactory
from app.modules.product.models import Product
from app.rag.models import ParentChunk
from app.rag.repository import ParentChunkRepository
from langchain.chat_models import init_chat_model
from langchain.messages import SystemMessage
from langchain_classic.schema import Document
from langchain_core.messages import HumanMessage
from langchain_milvus import Milvus
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
from mineru import MinerU

MARKDOWN_OPTIMIZATION_PROMPT = """
下面这份Markdown文档是从保险条款PDF解析得来，由于PDF中的各个小节是以表格形式存在，所以解析时出现错乱。
你分析内容，帮我转为格式正确的Markdown，特别是标题编号要正确。
- 标题等级要从1级标题开始，逐层增加，目录和文档名不计入标题等级。
- 输出结果中不要包含正文开始之前的部分。
- 输出结果只包含Markdown正文，不要解释或代码围栏。
- 不要修改保险条款。
""".strip()

logger = get_logger(__name__)


class RAGPipeline:
    """RAG pipeline 流水线处理知识入库"""

    def __init__(self, vector_store: Milvus) -> None:
        self._vector_store = vector_store

        # 1.初始化文档解析工具
        self._mineru = MinerU(settings.rag.mineru_token)

        self._model = init_chat_model(
            settings.llm.chat_model,
            api_key=settings.llm.api_key,
            extra_body={"thinking": {"type": "disabled"}},
            max_tokens=10000,
        )

        # 2.初始化文档切分工具
        self._markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "h1"),
                ("##", "h2"),
                ("###", "h3"),
                ("####", "h4"),
                ("#####", "h5"),
                ("######", "h6"),
            ],
            strip_headers=True,
        )
        self._child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", "。", "；", ";", "，", ","],
            keep_separator="end",
        )
        logger.info("RAG Pipeline 初始化完成✅️")

    def close(self) -> None:
        """关闭流水线持有的 MinerU 客户端。"""
        self._mineru.close()

    async def ingest(self, product: Product) -> None:
        """将新的产品对应的条款注入知识库中"""
        # 1.解析并优化文档内容
        markdown = self._parse_and_optimize_markdown(product.clause_name)
        if not markdown:
            raise ValueError(f"{product.clause_name} 未解析出内容")

        # 2.切分父块和子块
        parent_chunks, child_chunks = self._chunk(markdown, product) or (None, None)
        if not parent_chunks or not child_chunks:
            raise ValueError(f"{product.clause_name} 未切分出知识块")

        # 3.保存子块到向量数据库中
        self._save_children_chunks(product.id, child_chunks)

        # 4.保存父块到数据库中
        await self._save_parent_chunks(product.id, parent_chunks)

    def _parse_and_optimize_markdown(self, clause_name: str) -> str:
        """解析并优化 Markdown 内容"""
        # 1.使用 MinerU 进行解析
        file_path = Path(APP_ROOT / "data" / "raw" / "kb" / clause_name)
        result = self._mineru.extract(str(file_path))
        if result.state != "done" or not result.markdown:
            raise ValueError(f"{clause_name} 解析失败：{result.error or result.state}")

        # 2.进行优化
        response = self._model.invoke(
            [
                SystemMessage(MARKDOWN_OPTIMIZATION_PROMPT),
                HumanMessage(result.markdown),
            ]
        )

        # 3.返回优化后的解析结果
        return str(response.content)

    def _chunk(
        self, markdown: str, product: Product
    ) -> tuple[list[ParentChunk], list[Document]] | None:
        """切分父块和子块"""
        # 1.按照 markdown 标题切分父块
        sections = self._markdown_splitter.split_text(markdown)

        parent_chunks = []
        children_chunks = []

        # 2.遍历父块，继续切分子块
        for section in sections:
            section_path = list(section.metadata.values())
            parent_chunk = ParentChunk(
                id=uuid4(),
                product_id=product.id,
                clause_name=product.clause_name,
                section_path=section_path,
                content=section.page_content,
            )
            parent_chunks.append(parent_chunk)

            # 处理子块，子块通过 parent_id 与父块关联
            section.metadata = {
                "parent_id": str(parent_chunk.id),
                "product_id": product.id,
            }
            # 得到子块
            children_chunk = self._child_splitter.split_documents([section])

            # 将 section 路径保存到子块中，方便后续查询
            section_header = "\n".join(section_path) + "\n"
            for child_chunk in children_chunk:
                child_chunk.page_content = section_header + child_chunk.page_content
            children_chunks.extend(children_chunk)
        return parent_chunks, children_chunks

    def _save_children_chunks(
        self, product_id: int, children_chunks: list[Document]
    ) -> None:
        """将子块知识保存到向量数据库"""
        # 如果 collection 存在时，删除该产品对应的旧子块
        if self._vector_store.client.has_collection(self._vector_store.collection_name):
            self._vector_store.delete(expr=f"product_id=={product_id}")

        # 添加新的文档子块
        self._vector_store.add_documents(children_chunks)

    async def _save_parent_chunks(
        self, product_id: int, parent_chunks: list[ParentChunk]
    ) -> None:
        """将父块知识保存到数据库"""
        async with AsyncSessionFactory() as session, session.begin():
            # 获取数据操作类
            repository = ParentChunkRepository(session)
            # 删除该产品的旧父块
            await repository.delete_by_product_id(product_id)
            # 批量添加父块到数据库中
            repository.add_all(parent_chunks)
