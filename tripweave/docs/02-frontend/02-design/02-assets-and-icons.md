# 前端素材与图标

## 设计参考

用户最终确认的参考图为 `exec-4758c091-2d9e-4887-be0c-f0f7568d369c.png`，对应暖白酒红的日笺界面。参考图只用于布局、配色与层级判断，没有作为整页背景或图片组件堆叠。

## 园林图片

- 项目位置：`frontend/public/images/suzhou-garden.png`。
- 来源：本次使用内置 ImageGen 单独生成，作为苏州古典园林意境配图。
- 用途：以月洞门、水面和绿植承接旅行日笺的视觉氛围。
- 限制：非实拍，不代表拙政园等具体景点的真实视角或即时状态。
- 图片显示：代码使用 `object-fit: cover` 适配版面，未通过程序修改原图。

生成提示词：

> A quiet photographic landscape of a classical Suzhou Chinese garden: circular moon gate in white plaster wall and dark gray tiled roof, framing an elegant pavilion and lush trees, limestone rockery and still reflecting pond in foreground, soft spring daylight, sophisticated natural muted green palette, authentic architectural details. Landscape 4:3 composition for a travel journal photograph, no people, no text, no frame, photorealistic, not an illustration.

曾尝试获取 Wikimedia 图片，但下载超时，最终未使用该图片，页面没有对其进行错误署名。

## 路线图

由 `frontend/src/components/RouteMap.tsx` 绘制街区、水系、绿地和路线。坐标来自开发样本中的 SVG 平面点位，表示地点顺序，不能用作导航和地理测量。全部标记可交互，正文与图形均为可编辑代码。

## 图标与字体

- 图标为 npm 包 `lucide-react` 的真实 SVG 组件，许可为 ISC；依赖版本与其许可随包保留。使用说明：[Lucide React](https://lucide.dev/guide/packages/lucide-react)。
- 品牌标记改为 Lucide Compass 细线罗盘，与旅行规划及手册风格对应，不将其称作独家设计标识。列表和详情共用 `Brand.tsx`，沿用酒红色。桌面图标为 34px、字标为 26px；窄屏为 30px / 23px，统一垂直居中与图文间距。
- 系统宋体与 Georgia 字体回退，不下载或分发商业字体，不依赖外部字体服务。
