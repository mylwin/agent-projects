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
  assert.deepEqual(parseInline(blocks[2].items[0])[0], {
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
  assert.deepEqual(blocks[1].items, ["先去公园 再吃午饭", "下午休息"]);
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
