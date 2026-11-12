# All-in-RAG 第 8 章实战

基于 Datawhale 的“尝尝咸淡”菜谱 RAG 命令行项目，使用 **uv + Python 3.12** 管理。
保留 `code/C8` 源码结构及 `data/C8` 配套数据，生成模块已适配通用模型接口。

## 快速开始

在本项目根目录执行：

```bash
uv sync --locked
cp .env.example .env
# 在编辑器中填写 .env 的 LLM_BASE_URL、LLM_API_KEY、LLM_MODEL
uv run --locked python scripts/run.py
```

在 `.env` 配置服务商的 OpenAI Chat Completions 兼容接口，例如：

```dotenv
LLM_BASE_URL=https://api.example.com/v1
LLM_API_KEY=你的API密钥
LLM_MODEL=你的模型名称
```

地址、密钥和模型名称均按实际服务商填写。基础地址通常包含 `/v1`，
也可能是服务商指定的其他前缀；不要附加 `/chat/completions`。
也支持 `OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL`，非空的 `LLM_*` 优先。
模型无默认值，原有 Moonshot 配置请迁移到这三项。
无需密钥的本地兼容服务也需给 `LLM_API_KEY` 填一个非空占位值。
其他厂商的原生协议（如 Messages API）需要独立适配。

首次启动会下载 `BAAI/bge-small-zh-v1.5` 并构建索引。
仅更换生成模型时，可复用已有向量索引。

菜谱原图已按原路径补齐。上游 All-in-RAG 中的部分图片是 LFS 指针，
本项目从菜谱来源 HowToCook 的公开 LFS 对象库获取原图，并逐张校验原始 SHA-256。
如需恢复缺失图片，可运行 `uv run --locked python scripts/restore_images.py`，
已校验的图片会自动跳过。

也可从任意目录执行 `bash /本项目绝对路径/scripts/run.sh`。

## 验证

```bash
# 本地模拟服务测试：配置、鉴权、模型传递、普通回答与 SSE；无需真实密钥
uv run --locked python -m unittest discover -s tests -v

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
tests/                通用模型接口本地集成测试
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
