# 环境配置与验证记录

## 环境

- 管理工具：uv（本次使用 0.12.21）。
- Python：3.12 系列（本次选择已安装的 CPython 3.12.14）。
- 平台：macOS arm64。
- 依赖：完整沿用 C8 的 13 项直接依赖约束，间接依赖由 `uv.lock` 固定。
- 软件源：本次沿用本机 uv 配置的清华 PyPI 镜像，锁文件保留实际下载来源。

在项目根目录执行 `uv sync --locked`，无需激活虚拟环境，也无需 conda 或 pip。

## 配置

复制 `.env.example` 为 `.env`，设置 `MOONSHOT_API_KEY`。
不要将真实密钥提交到 Git，也无需将密钥写入源码。

| 配置项 | 默认值或作用 |
| --- | --- |
| `MOONSHOT_API_KEY` | 问答程序必填；纯数据与向量索引检查不需要 |
| `MOONSHOT_MODEL` | 留空使用上游 `kimi-k2-0711-preview`；按账户可用模型覆盖 |
| `EMBEDDING_MODEL` | 留空使用 `BAAI/bge-small-zh-v1.5`，也支持本地模型目录 |
| `HF_ENDPOINT` | 可选的 Hugging Face 端点，遵循用户本地配置 |
| `HF_HOME` | 启动脚本默认设置为本项目 `.cache/huggingface`，可自行覆盖 |
| `HF_HUB_DISABLE_XET` | 下载长时间停滞时可设为 `1`，改用普通 HTTP |

运行：

```bash
uv run --locked python scripts/run.py
```

启动适配器会加载项目根目录的 `.env`，将工作目录切换到 `code/C8`，
并使用项目内的绝对数据和索引路径。原始 `main.py` 保持上游原样；
若直接运行原始入口，仍应遵循教程的工作目录和环境变量要求。

## 数据与模型

导入 323 个 Markdown 文件，其中包括上游的示例菜模板；数据加载器会按上游行为
读取全部 Markdown。共有 326 个资源文件是 Git LFS 指针，保留仓库中的原样内容。
当前系统只读取 Markdown，不需要图片实体。

真实嵌入模型首次运行需要网络。索引使用 CPU 构建，保存在 `code/C8/vector_index`。
如果配置文件下载成功但权重长时间没有进展，可在 `.env` 设置
`HF_HUB_DISABLE_XET=1` 后重新运行。本次验证采用这一传输方式。
更换嵌入模型、菜谱数据或分块逻辑后，需要删除该目录并重新构建，
或者运行 `uv run --locked python scripts/check.py --index` 完整重建。

`check.py --index` 会用全部菜谱构建索引，先在临时目录验证保存与加载，
成功后保存到正式缓存目录。检查记录中的检索示例仅验证链路，不代表系统性质量评估。

## 本次验证（2026-11-12）

| 检查 | 结果 |
| --- | --- |
| 上游文件完整性 | 659 个文件与固定提交的 Git blob 逐字节一致，SHA-256 清单复核通过 |
| 直接依赖迁移 | 与上游 `requirements.txt` 的 13 项约束完全一致 |
| uv 安装 | 锁定 143 个包，本机平台实际安装 120 个包 |
| 锁文件一致性 | `uv lock --check --offline` 通过 |
| 依赖兼容性 | `uv pip check` 通过 |
| Python 与 Shell 语法 | Python 编译检查及 `bash -n scripts/run.sh` 通过 |
| 菜谱读取与分块 | 323 份文档，生成 1,764 个非空子块 |
| 父子文档映射 | 父文档标识唯一，无孤立子块，完整父文档回溯通过 |
| BM25 | “西红柿 鸡蛋”返回西红柿炒鸡蛋、西红柿鸡蛋汤、西葫芦炒鸡蛋 |
| 真实向量索引 | BGE 模型在 CPU 上为全部 1,764 个子块构建 FAISS 索引 |
| 索引持久化 | 临时目录保存与重新加载通过，重新加载后仍为 1,764 条向量 |
| 混合检索 | “西红柿炒鸡蛋需要哪些食材？”返回西红柿炒鸡蛋及温泉蛋的父文档 |
| 正式索引缓存 | 已写入 `code/C8/vector_index/index.faiss` 与 `index.pkl` |
| 跨目录启动 | 从项目外执行 `scripts/run.sh`，正确定位项目并提示缺少密钥 |
| API 问答 | 未执行：本项目尚未配置 `.env`，当前进程也没有 `MOONSHOT_API_KEY` |

嵌入模型下载快照：`BAAI/bge-small-zh-v1.5`，
提交 `7999e1d3359715c523056ef9478215996d62a620`。
本次模型下载使用 `HF_HUB_DISABLE_XET=1`，切换普通 HTTP 后成功完成。
默认 Kimi 模型的账户可用性和三类实际回答尚未验证。

## 后续 API 联调

```bash
uv run --locked python scripts/check.py --api
```

该命令验证菜品做法、菜品推荐、食材查询，会调用账户中的模型。
教程默认模型的当前可用性必须以实际账户调用为准。
