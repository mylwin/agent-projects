/** 复用实际 API 客户端，验证聊天正文快照和服务端编辑契约。 */
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { afterEach, test } from "node:test";
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
const { sendProjectMessage, getProjectMessages, saveProjectRevision } =
  await import(
    `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
  );
const original = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = original;
});

test("普通聊天的正文快照逐步到达，并保留依据版本与未授权状态", async () => {
  let writer;
  globalThis.fetch = async (path, init) => {
    assert.equal(path, "/api/projects/12/messages");
    const body = JSON.parse(init.body);
    assert.equal(body.base_revision_id, 34);
    assert.equal(body.day_id, 2);
    assert.equal(body.generate, false);
    return new Response(
      new ReadableStream({
        start(controller) {
          writer = controller;
        },
      }),
      { headers: { "Content-Type": "text/event-stream" } },
    );
  };
  const messages = [];
  const result = sendProjectMessage(
    12,
    { text: "你好", base_revision_id: 34, day_id: 2, generate: false },
    (event) => messages.push(event.message),
    new AbortController().signal,
  );
  await new Promise((resolve) => setImmediate(resolve));
  writer.enqueue(
    new TextEncoder().encode(
      'event: reply\ndata: {"event":"reply","message":"你"}\n\nevent: reply\ndata: {"event":"reply","message":"你好"}\n\n',
    ),
  );
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(messages, ["你", "你好"]);
  writer.enqueue(
    new TextEncoder().encode(
      'event: complete\ndata: {"event":"complete","data":{"id":1,"assistant_text":"你好","result_revision_id":null}}\n\n',
    ),
  );
  assert.equal((await result).result_revision_id, null);
});

test("历史对话从服务端读取，手动编辑携带依据版本", async () => {
  globalThis.fetch = async (path, init) => {
    assert.equal(init.credentials, "include");
    if (path.endsWith("/messages"))
      return Response.json({
        success: true,
        data: [{ id: 1, assistant_text: "已保存的对话" }],
      });
    assert.equal(path, "/api/projects/12/revisions");
    assert.equal(init.method, "POST");
    assert.deepEqual(JSON.parse(init.body), {
      base_revision_id: 34,
      trip: { id: "test" },
    });
    return Response.json({ success: true, data: { id: 35, number: 2 } });
  };
  assert.equal(
    (await getProjectMessages(12))[0].assistant_text,
    "已保存的对话",
  );
  assert.equal((await saveProjectRevision(12, 34, { id: "test" })).id, 35);
});
