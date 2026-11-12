# All-in-RAG 第 8 章实战

基于 Datawhale 的“尝尝咸淡”菜谱 RAG 命令行项目，使用 **uv + Python 3.12** 管理。
完整保留 `code/C8` 核心源码及 `data/C8` 配套数据，便于对照教程学习。

## 快速开始

在本项目根目录执行：

```bash
uv sync --locked
cp .env.example .env
# 在编辑器中填写 .env 的 MOONSHOT_API_KEY
uv run --locked python scripts/run.py
```

默认使用教程的 `kimi-k2-0711-preview`。如果账户无法使用该模型，
在 `.env` 中设置 `MOONSHOT_MODEL` 为账户可用的模型名称。
首次启动会下载 `BAAI/bge-small-zh-v1.5` 并构建索引。

也可从任意目录执行 `bash /本项目绝对路径/scripts/run.sh`。

## 验证

```bash
# 检查依赖、菜谱加载、分块、父文档映射和 BM25，无需密钥或模型下载
uv run --locked python scripts/check.py

# 下载真实嵌入模型，检查向量检索、索引保存与重新加载，无需 API 密钥
uv run --locked python scripts/check.py --index

# 已配置密钥时，验证三类完整问答，会产生 API 调用费用
uv run --locked python scripts/check.py --api
```

## 目录

```text
code/C8/              上游配置、命令行入口及四个核心模块
data/C8/cook/dishes/   上游菜谱 Markdown 及仓库中的配套资源
scripts/              uv 启动、配置适配和验证脚本
docs/setup.md         环境说明、限制及本次验证结果
UPSTREAM.md           来源、版本、许可及文件校验信息
uv.lock               完整依赖锁文件，需提交版本控制
.venv/                uv 虚拟环境，自动生成且忽略提交
.cache/huggingface/    模型缓存，自动生成且忽略提交
code/C8/vector_index/  问答程序生成的索引缓存，忽略提交
```

依赖以 `pyproject.toml` 和 `uv.lock` 为准。
`code/C8/requirements.txt` 保留为上游参考，不另行使用 pip 安装。
第 9 章 Graph RAG 扩展尚未引入。

上游：[All-in-RAG](https://github.com/datawhalechina/all-in-rag) ·
[环境与架构教程](https://datawhalechina.github.io/all-in-rag/#/chapter8/01_env_architecture)

许可与署名见 [UPSTREAM.md](UPSTREAM.md)。
