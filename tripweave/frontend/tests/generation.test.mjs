/** 使用现有 TypeScript 编译器和 Node 测试工具，验证浏览器流式接口。 */
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test, afterEach } from "node:test";
import ts from "typescript";

const source = await readFile(
  new URL("../src/api/projects.ts", import.meta.url),
  "utf8",
);
const { outputText } = ts.transpileModule(source, {
  compilerOptions: {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.ES2022,
  },
});
const { generateSavedPlan } = await import(
  `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
);
const originalFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = originalFetch;
});
const input = { name: "测试" };
const frame = (event) =>
  `event: ${event.event}\r\ndata: ${JSON.stringify(event)}\r\n\r\n`;

/** 创建逐个字节分片的 UTF-8 流，覆盖中文及帧边界拆分。 */
function byteStream(text) {
  const bytes = new TextEncoder().encode(text);
  let index = 0;
  return new Response(
    new ReadableStream({
      pull(controller) {
        if (index === bytes.length) controller.close();
        else controller.enqueue(bytes.slice(index, ++index));
      },
    }),
    { headers: { "Content-Type": "text/event-stream" } },
  );
}

test("完成前立即交付进度，支持中文、CRLF 和心跳", async () => {
  let writer;
  globalThis.fetch = async (_url, init) => {
    assert.equal(init.headers.Accept, "text/event-stream");
    assert.equal(init.credentials, "include");
    return new Response(
      new ReadableStream({
        start(controller) {
          writer = controller;
        },
      }),
      { headers: { "Content-Type": "text/event-stream" } },
    );
  };
  const progress = [];
  const promise = generateSavedPlan(
    input,
    (event) => progress.push(event),
    new AbortController().signal,
  );
  await new Promise((resolve) => setImmediate(resolve));
  writer.enqueue(
    new TextEncoder().encode(frame({ event: "progress", message: "查询天气" })),
  );
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(progress[0].message, "查询天气");
  writer.enqueue(
    new TextEncoder().encode(
      frame({ event: "complete", data: { project_id: 12 } }),
    ),
  );
  assert.equal((await promise).project_id, 12);
});

test("任意字节分片与多帧仍能正确拼接", async () => {
  globalThis.fetch = async () =>
    byteStream(
      ": heartbeat\r\n\r\n" +
        frame({ event: "progress", message: "景点研究" }) +
        frame({ event: "complete", data: { revision_id: 34 } }),
    );
  const progress = [];
  const result = await generateSavedPlan(
    input,
    (event) => progress.push(event),
    new AbortController().signal,
  );
  assert.equal(progress.length, 1);
  assert.equal(progress[0].message, "景点研究");
  assert.equal(result.revision_id, 34);
});

test("流内错误保留业务错误码", async () => {
  globalThis.fetch = async () =>
    byteStream(
      frame({
        event: "error",
        error: { code: "planning_timeout", message: "规划超时" },
      }),
    );
  await assert.rejects(
    generateSavedPlan(input, () => {}, new AbortController().signal),
    { code: "planning_timeout", message: "规划超时" },
  );
});

test("缺少终态的断流不冒充成功", async () => {
  globalThis.fetch = async () =>
    byteStream(frame({ event: "started", message: "开始" }));
  await assert.rejects(
    generateSavedPlan(input, () => {}, new AbortController().signal),
    { code: "stream_interrupted" },
  );
});

test("开始前的登录失败仍正确显示", async () => {
  globalThis.fetch = async () =>
    Response.json(
      { success: false, error: { code: "unauthorized", message: "请先登录" } },
      { status: 401 },
    );
  await assert.rejects(
    generateSavedPlan(input, () => {}, new AbortController().signal),
    { code: "unauthorized", message: "请先登录" },
  );
});
