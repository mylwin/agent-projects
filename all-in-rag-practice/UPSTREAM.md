# 上游来源与许可

- 项目：Datawhale China / All-in-RAG
- 仓库：https://github.com/datawhalechina/all-in-rag
- 分支：`main`
- 导入提交：`cec956e80ae28d6c0ca84c9d39dddcf61ad633fd`
- 提交链接：https://github.com/datawhalechina/all-in-rag/commit/cec956e80ae28d6c0ca84c9d39dddcf61ad633fd
- 导入日期：2026-11-12（Asia/Shanghai）
- 导入目录：`code/C8/`、`data/C8/`
- 导入方式：临时目录稀疏检出后复制文件，不在本项目嵌套 Git 仓库。
- 校验清单：[docs/upstream-manifest.json](docs/upstream-manifest.json)

初次导入共 659 个文件，其中 323 个菜谱 Markdown，导入时均与上游 Git blob
逐字节校验一致。通用模型适配修改了下述 3 个源文件。
其中 326 个图片文件在上游为 Git LFS 文本指针，本地已恢复为原始图片；
其余 330 个文件保持上游原样。

## 图片恢复

核查 All-in-RAG 的固定提交未发现 `.gitattributes`，这批图片的 324 个唯一对象
在该仓库的 LFS 下载接口均返回 `Object does not exist on the server`。
菜谱来源 HowToCook 的公开 LFS 对象库能提供对应原图，因此从该来源恢复图片。

- 来源：https://github.com/Anduin2017/HowToCook
- 方法：按原始指针的对象标识请求 LFS `download`，不以当前同名图片替代。
- 范围：326 个文件、324 个唯一对象，原始总大小约 95.89 MiB。
- 校验：每个图片实体的 SHA-256 与原始指针的 `oid` 一致，字节数与 `size` 一致。
- 路径：原文件夹和文件名保持不变，Markdown 的相对图片引用无需修改。
- 恢复脚本：`scripts/restore_images.py`，支持重复运行并跳过已匹配的图片。

清单中的 `files` 保留初始导入哈希；`lfs_objects` 单独记录恢复原图的哈希与大小。
校验脚本同时接受原始指针及其匹配原图。原图存储为普通图片文件，
本项目不要求安装 Git LFS；无需密钥即可重新获取这些公开对象。

## 署名与许可

上游 README 声明采用
[知识共享署名－非商业性使用－相同方式共享 4.0 国际许可协议（CC BY-NC-SA 4.0）](https://creativecommons.org/licenses/by-nc-sa/4.0/)。
上游许可原文见
[固定提交的 README](https://github.com/datawhalechina/all-in-rag/blob/cec956e80ae28d6c0ca84c9d39dddcf61ad633fd/README.md#许可证)。

菜谱数据来自上游收录的
[HowToCook / 程序员做饭指南](https://github.com/Anduin2017/HowToCook)，
原文件中的作者与来源信息均予保留。

## 本地新增内容

本地新增 uv 项目配置、依赖锁文件、环境变量示例、启动与验证脚本、
通用模型接口集成测试及中文说明。启动适配器将数据、索引及模型缓存路径固定到项目内。

通用模型适配修改以下上游文件：

- `code/C8/config.py`：增加通用模型配置加载、别名兼容与校验。
- `code/C8/main.py`：使用通用配置初始化生成模块。
- `code/C8/rag_modules/generation_integration.py`：将 MoonshotChat 替换为 ChatOpenAI，
  显式使用 Chat Completions，支持普通与流式回答。

新增 `langchain-openai` 依赖。生成模型通过 `LLM_BASE_URL`、`LLM_API_KEY`、
`LLM_MODEL` 配置，也支持 `OPENAI_*` 别名；嵌入模型仍由 `EMBEDDING_MODEL` 配置。
校验清单保留初次导入的哈希，并在 `local_modifications` 中记录以上 3 个文件。
验证脚本对原样文件比对哈希，对本地适配文件检查存在性；适配改动由 Git 记录。

## 后续同步

先选择新的上游提交，比较 `code/C8/` 与 `data/C8/`，再替换所需文件并重新生成
清单、更新本文中的提交信息。依赖变更同步修改 `pyproject.toml`，执行 `uv lock`
及 `uv sync --locked`，重新运行验证脚本。不要直接覆盖本地新增的配置和脚本。
