/** 验证助手回复的轻量 Markdown 解析，不依赖浏览器或 React 渲染。 */
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import ts from "typescript";

const source = await readFile(
  new URL("../src/utils/chatMarkdown.ts", import.meta.url),
  "utf8",
);
const { outputText } = ts.transpileModule(source, {
  compilerOptions: {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.ES2022,
  },
});
const { parseChatMarkdown, parseInline } = await import(
  `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
);

test("截图中的回复解析为段落和两天列表", () => {
  const blocks = parseChatMarkdown(`你好！👋

看到你正在规划宿州两天的一人小旅行，节奏安排得挺舒服的——

- **第 1 天**：老城觅食 + 新汴河/紫薇园漫步。
- **第 2 天**（当前选中）：雪枫公园晨间慢游，11:30 退房离宿。

有什么想聊的或想调整的地方，随时告诉我😊`);
  assert.deepEqual(
    blocks.map((block) => block.kind),
    ["paragraph", "paragraph", "unordered-list", "paragraph"],
  );
  assert.equal(blocks[2].items.length, 2);
  assert.deepEqual(parseInline(blocks[2].items[0].blocks[0].text)[0], {
    kind: "bold",
    text: "第 1 天",
  });
});

test("标题、有序列表和列表续行都保留顺序", () => {
  const blocks = parseChatMarkdown(`### 建议
1. 先去公园
   再吃午饭
2. 下午休息`);
  assert.deepEqual(
    blocks.map((block) => block.kind),
    ["heading", "ordered-list"],
  );
  assert.equal(blocks[0].text, "建议");
  assert.deepEqual(blocks[1].items, [
    { number: 1, blocks: [{ kind: "paragraph", text: "先去公园\n再吃午饭" }] },
    { number: 2, blocks: [{ kind: "paragraph", text: "下午休息" }] },
  ]);
});

test("行内加粗、代码和 http 链接拆成片段", () => {
  const tokens = parseInline(
    "**重点**：用 `步行` 去[地图](https://example.com/a)",
  );
  assert.deepEqual(
    tokens.map((token) => token.kind),
    ["bold", "text", "code", "text", "link"],
  );
  assert.equal(tokens[0].text, "重点");
  assert.equal(tokens[2].text, "步行");
  assert.deepEqual(tokens[4], {
    kind: "link",
    text: "地图",
    href: "https://example.com/a",
  });
});

test("未闭合标记和 HTML 都按普通文本保留，不执行也不丢内容", () => {
  const tokens = parseInline("**未闭合 和 `未闭合 <b>粗体</b>");
  assert.equal(tokens.length, 1);
  assert.equal(tokens[0].kind, "text");
  const blocks = parseChatMarkdown("<script>alert(1)</script>");
  assert.equal(blocks.length, 1);
  assert.equal(blocks[0].kind, "paragraph");
  assert.equal(blocks[0].text, "<script>alert(1)</script>");
});

test("空行有序列表保留原始编号，嵌套列表保留层级", () => {
  const [list] = parseChatMarkdown(
    "3. 上午\n   - 园林\n   - 茶馆\n\n4. 下午\n\n7. 晚餐",
  );
  assert.equal(list.kind, "ordered-list");
  assert.deepEqual(
    list.items.map((item) => item.number),
    [3, 4, 7],
  );
  assert.equal(list.items[0].blocks[1].kind, "unordered-list");
  assert.equal(list.items[0].blocks[1].items[1].blocks[0].text, "茶馆");
});

test("流式未闭合围栏保留原文，闭合后转为代码块", () => {
  assert.deepEqual(parseChatMarkdown("```text\n**原文"), [
    { kind: "literal", text: "```text\n**原文" },
  ]);
  assert.deepEqual(parseChatMarkdown("```text\n**原文\n```"), [
    { kind: "code", text: "**原文" },
  ]);
});

test("列表后的独立段落不吞入列表，危险协议不转链接", () => {
  const blocks = parseChatMarkdown("- 园林\n\n另一段解释");
  assert.equal(blocks[1].kind, "paragraph");
  assert.equal(blocks[1].text, "另一段解释");
  for (const input of [
    "[链接](javascript:alert(1))",
    "[链接](data:text/html,test)",
    "[链接](https://)",
  ])
    assert.equal(
      parseInline(input).some((token) => token.kind === "link"),
      false,
    );
});

test("住宿候选表格解析为表头、对齐和补齐的数据行", () => {
  const blocks = parseChatMarkdown(`以下为高德地图返回的候选：
| 候选 | uid | 地址 | 坐标 (lat,lng) | 评分/类型 |
| --- | :--- | --- | ---: | :---: |
| **宿州宾馆** | B0FF | 埇桥区胜利路 1 号 | 33.64,116.98 | 4.6 / 舒适型 |
| 汇源大酒店 | B0GG | 银河一路 2 号 | 33.65,116.99 |
正文补充说明。`);
  assert.deepEqual(
    blocks.map((block) => block.kind),
    ["paragraph", "table", "paragraph"],
  );
  const table = blocks[1];
  assert.deepEqual(table.header, [
    "候选",
    "uid",
    "地址",
    "坐标 (lat,lng)",
    "评分/类型",
  ]);
  assert.deepEqual(table.align, [null, "left", null, "right", "center"]);
  assert.equal(table.rows.length, 2);
  assert.deepEqual(table.rows[1], [
    "汇源大酒店",
    "B0GG",
    "银河一路 2 号",
    "33.65,116.99",
    "",
  ]);
  assert.equal(blocks[2].text, "正文补充说明。");
  assert.deepEqual(parseInline(table.rows[0][0])[0], {
    kind: "bold",
    text: "宿州宾馆",
  });
});

test("分隔行不完整或列数不符时保留原文，转义竖线属于单元格", () => {
  assert.deepEqual(parseChatMarkdown("| 候选 | 地址 |\n| --- |"), [
    { kind: "paragraph", text: "| 候选 | 地址 |\n| --- |" },
  ]);
  assert.deepEqual(parseChatMarkdown("| 候选 | 地址 |\n| --- | --- | --- |"), [
    { kind: "paragraph", text: "| 候选 | 地址 |\n| --- | --- | --- |" },
  ]);
  assert.deepEqual(parseChatMarkdown("候选 | 地址\n--- | ---\n宾馆 | 胜利路"), [
    {
      kind: "table",
      header: ["候选", "地址"],
      align: [null, null],
      rows: [["宾馆", "胜利路"]],
    },
  ]);
  const [table] = parseChatMarkdown("| 名称 |\n| --- |\n| A\\|B |");
  assert.deepEqual(table.rows, [["A|B"]]);
  assert.equal(parseChatMarkdown("| 名称 |\n| --- |")[0].rows.length, 0);
});

test("表格不吞掉后续标题、列表和围栏，单元格内不执行HTML", () => {
  const blocks = parseChatMarkdown(`| 候选 | 备注 |
| --- | --- |
| 宾馆 | <b>加粗</b> |

## 结论
- 优先选择近老城的候选

\`\`\`text
| 不是表格 |
\`\`\``);
  assert.deepEqual(
    blocks.map((block) => block.kind),
    ["table", "heading", "unordered-list", "code"],
  );
  assert.equal(blocks[0].rows[0][1], "<b>加粗</b>");
  assert.equal(blocks[3].text, "| 不是表格 |");
});

test("逐前缀解析嵌套内容不会抛错或输出HTML", () => {
  const text =
    "## 安排\n\n- 上午 **游园**\n  - [来源](https://example.com)\n\n1. 午餐\n\n2. 散步\n\n| 候选 | 评分 |\n| --- | ---: |\n| 宾馆 | 4.6 |";
  for (let i = 0; i <= text.length; i++)
    assert.doesNotThrow(() => parseChatMarkdown(text.slice(0, i)));
  const deep =
    "- 起点\n" +
    Array.from({ length: 30 }, (_, i) => "  ".repeat(i + 1) + "- 下一层").join(
      "\n",
    );
  assert.doesNotThrow(() => parseChatMarkdown(deep));
});
