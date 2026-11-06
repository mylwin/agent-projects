# TripWeave 前端

React + TypeScript + Vite，沿用暖白酒红旅行日笺设计和 lucide-react 图标。

在本目录执行：

```bash
pnpm install --frozen-lockfile
pnpm dev
```

打开终端显示的本地地址。验证命令为 `pnpm typecheck`、`pnpm lint`、`pnpm build`。

已登录页面通过后端读取已保存的项目列表、详情、版本和公开生成轨迹，并可设置最终方案。
新建计划调用后端生成接口并保存到服务端；旧版苏州草稿、手动编辑与本地助手仍保存在浏览器。
服务端版本详情展示完整行程、地点事实、调研资料、工具证据和未核实提示。
样例统一放在 src/data，SVG 路线为示意，不提供导航。
活动费用允许 null，未知费用合计显示为“待核实”。

[项目文档入口](../docs/README.md) · [数据与接入边界](../docs/03-frontend-data.md)
