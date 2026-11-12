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

导入共 659 个文件，其中 323 个菜谱 Markdown。所有导入文件均与上游 Git blob
逐字节校验一致。326 个资源文件在上游为 Git LFS 文本指针，本地按原样保留；
这些文件不是可显示的图片，当前 RAG 只读取 Markdown，不需要下载对应图片实体。

## 署名与许可

上游 README 声明采用
[知识共享署名－非商业性使用－相同方式共享 4.0 国际许可协议（CC BY-NC-SA 4.0）](https://creativecommons.org/licenses/by-nc-sa/4.0/)。
上游许可原文见
[固定提交的 README](https://github.com/datawhalechina/all-in-rag/blob/cec956e80ae28d6c0ca84c9d39dddcf61ad633fd/README.md#许可证)。

菜谱数据来自上游收录的
[HowToCook / 程序员做饭指南](https://github.com/Anduin2017/HowToCook)，
原文件中的作者与来源信息均予保留。

## 本地新增内容

`code/C8/` 与 `data/C8/` 保持上游原样。本地新增 uv 项目配置、依赖锁文件、
环境变量示例、启动与验证脚本及中文说明，便于在 Python 3.12 环境中复现。
启动适配器将数据、索引及模型缓存路径固定到项目内，并支持
`MOONSHOT_MODEL`、`EMBEDDING_MODEL` 覆盖默认模型。

## 后续同步

先选择新的上游提交，比较 `code/C8/` 与 `data/C8/`，再替换所需文件并重新生成
清单、更新本文中的提交信息。依赖变更同步修改 `pyproject.toml`，执行 `uv lock`
及 `uv sync --locked`，重新运行验证脚本。不要直接覆盖本地新增的配置和脚本。
