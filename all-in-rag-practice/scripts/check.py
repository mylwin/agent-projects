"""验证数据处理链路，可选执行真实模型索引和 API 联调。"""

import argparse
import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory

from runtime import PROJECT_ROOT, load_config, prepare_environment


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def check_imported_files():
    import hashlib

    manifest = json.loads((PROJECT_ROOT / "docs/upstream-manifest.json").read_text())
    modified = set(manifest.get("local_modifications", []))
    images = manifest.get("lfs_objects", {})
    require(modified <= {entry["path"] for entry in manifest["files"]}, "本地适配清单包含未知文件")
    for entry in manifest["files"]:
        path = PROJECT_ROOT / entry["path"]
        require(path.is_file(), f"上游文件缺失：{entry['path']}")
        if entry["path"] in modified:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        expected = {entry["sha256"]}
        if entry["path"] in images:
            image = images[entry["path"]]
            expected.add(image["oid"])
            if digest == image["oid"]:
                require(path.stat().st_size == image["size"], f"图片大小不一致：{entry['path']}")
        require(digest in expected, f"文件已偏离上游快照或原始图片：{entry['path']}")
    return len(manifest["files"]) - len(modified), len(modified)


def check_data(config):
    from langchain_community.retrievers import BM25Retriever
    from rag_modules import DataPreparationModule

    data = DataPreparationModule(config.data_path)
    documents = data.load_documents()
    expected = len(list(Path(config.data_path).rglob("*.md")))
    require(expected > 0 and len(documents) == expected, "存在未能读取的菜谱")
    chunks = data.chunk_documents()
    require(len(chunks) >= len(documents), "分块数量异常")
    parents = {doc.metadata["parent_id"]: doc for doc in documents}
    require(len(parents) == len(documents), "父文档标识发生冲突")
    require(all(c.metadata["parent_id"] in parents for c in chunks), "存在孤立子块")
    require(all(c.page_content.strip() for c in chunks), "存在空文本块")
    require(len(data.get_parent_documents(chunks)) == len(documents), "父文档回溯不完整")

    retriever = BM25Retriever.from_documents(chunks, k=config.top_k)
    hits = retriever.invoke("西红柿 鸡蛋")
    require(bool(hits), "BM25 未返回结果")
    summary = data.get_statistics()
    summary["bm25_hits"] = [hit.metadata["dish_name"] for hit in hits]
    print(json.dumps({"data_check": summary}, ensure_ascii=False, indent=2))
    return data, chunks


def check_index(config, data, chunks):
    from rag_modules import IndexConstructionModule, RetrievalOptimizationModule

    index = IndexConstructionModule(config.embedding_model, config.index_save_path)
    vectorstore = index.build_vector_index(chunks)
    require(vectorstore.index.ntotal == len(chunks), "向量索引条数与分块数不一致")

    # 先在临时目录验证持久化往返，成功后再保存供问答程序使用。
    with TemporaryDirectory(prefix="rag-index-", dir=PROJECT_ROOT / ".cache") as temp:
        original_path = index.index_save_path
        index.index_save_path = temp
        index.save_index()
        restored = index.load_index()
        require(restored is not None, "索引重新加载失败")
        require(restored.index.ntotal == len(chunks), "重新加载后索引条数不一致")
        retrieval = RetrievalOptimizationModule(restored, chunks)
        hits = retrieval.hybrid_search("西红柿炒鸡蛋需要哪些食材？", top_k=config.top_k)
        require(bool(hits), "混合检索未返回结果")
        parents = data.get_parent_documents(hits)
        require(bool(parents), "无法获取检索结果的完整父文档")
        print(json.dumps({"index_check": {
            "vectors": restored.index.ntotal,
            "reloaded": True,
            "retrieved_dishes": [doc.metadata["dish_name"] for doc in parents],
        }}, ensure_ascii=False, indent=2))
        index.index_save_path = original_path
    index.save_index()


def check_api(config):
    from main import RecipeRAGSystem

    system = RecipeRAGSystem(config)
    system.initialize_system()
    system.build_knowledge_base()
    for query in ("西红柿炒鸡蛋怎么做？", "推荐几个简单的素菜", "红烧肉需要什么食材？"):
        answer = system.ask_question(query, stream=False)
        require(isinstance(answer, str) and bool(answer.strip()), "API 未返回有效回答")
        require("抱歉，没有找到相关的食谱信息" not in answer, "问题未能检索到食谱")
        print(json.dumps({"query": query, "answer": answer}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", action="store_true", help="使用真实嵌入模型构建完整菜谱索引")
    parser.add_argument("--api", action="store_true", help="执行三类问答，产生 API 调用费用")
    args = parser.parse_args()
    prepare_environment()
    logging.basicConfig(level=logging.WARNING)
    config = load_config()
    if args.api:
        try:
            config.validate_llm()
        except ValueError as error:
            parser.error(str(error))
    count, modified = check_imported_files()
    print(f"上游文件校验通过：{count} 个（支持 LFS 原图）；本地适配文件：{modified} 个（检查存在性）")
    data, chunks = check_data(config)
    if args.index:
        (PROJECT_ROOT / ".cache").mkdir(exist_ok=True)
        check_index(config, data, chunks)
    if args.api:
        check_api(config)
    print("所选检查全部通过。")


if __name__ == "__main__":
    main()
