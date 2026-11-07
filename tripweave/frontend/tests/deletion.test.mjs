/** 验证整项删除的接口契约和本地存储失败恢复。 */
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { afterEach, test } from "node:test";
import ts from "typescript";

const originalFetch = globalThis.fetch;
const originalStorage = globalThis.localStorage;
afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalStorage === undefined) delete globalThis.localStorage;
  else globalThis.localStorage = originalStorage;
});
let moduleId = 0;
/** 编译真实源码，不复制业务实现，独立模块用于验证刷新后的初始化。 */
async function loadModule(path, transform = (source) => source) {
  const source = transform(
    await readFile(new URL(path, import.meta.url), "utf8"),
  );
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ES2022,
    },
  });
  return import(
    `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}#${++moduleId}`
  );
}
const fixture = await readFile(
  new URL("../src/data/trip.json", import.meta.url),
  "utf8",
);
/** 使用真实工作区模块，并内联其静态行程样例。 */
function loadStore() {
  return loadModule("../src/api/workspaceStore.ts", (source) =>
    source.replace(
      'import fixture from "../data/trip.json";',
      `const fixture = ${fixture};`,
    ),
  );
}
/** 提供可控的本地存储替身。 */
function setupStorage() {
  const values = new Map();
  globalThis.localStorage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
  return values;
}

test("服务端整项删除携带 Cookie，成功响应为 null", async () => {
  const { deleteSavedProject } = await loadModule("../src/api/projects.ts");
  globalThis.fetch = async (path, init) => {
    assert.equal(path, "/api/projects/12");
    assert.equal(init.method, "DELETE");
    assert.equal(init.credentials, "include");
    return Response.json({ success: true, data: null });
  };
  assert.equal(await deleteSavedProject(12), null);
});

test("生成中的计划保留冲突错误，供弹窗提示重试", async () => {
  const { deleteSavedProject } = await loadModule("../src/api/projects.ts");
  globalThis.fetch = async () =>
    Response.json(
      {
        success: false,
        error: { code: "project_generating", message: "计划正在生成" },
      },
      { status: 409 },
    );
  await assert.rejects(deleteSavedProject(12), {
    code: "project_generating",
    message: "计划正在生成",
  });
});

test("本地整项删除保留另一项目，刷新后不会恢复被删除项目", async () => {
  setupStorage();
  const store = await loadStore();
  const original = store.getSnapshot().workspace.projects[0];
  const other = store.newProject("另一个计划", original.trip);
  store.addProject(other);
  assert.equal(store.deleteLocalProject(original.id), true);
  assert.deepEqual(
    store.getSnapshot().workspace.projects.map((project) => project.id),
    [other.id],
  );
  const reloaded = await loadStore();
  assert.deepEqual(
    reloaded.getSnapshot().workspace.projects.map((project) => project.id),
    [other.id],
  );
});

test("删除最后一个草稿后保持空列表", async () => {
  setupStorage();
  const store = await loadStore();
  store.deleteLocalProject(store.getSnapshot().workspace.projects[0].id);
  assert.equal((await loadStore()).getSnapshot().workspace.projects.length, 0);
});

test("存储失败时完整保留项目及版本，并允许重试", async () => {
  setupStorage();
  const store = await loadStore();
  const before = store.getSnapshot().workspace;
  globalThis.localStorage.setItem = () => {
    throw new Error("存储失败");
  };
  assert.equal(store.deleteLocalProject(before.projects[0].id), false);
  assert.equal(store.getSnapshot().workspace, before);
  assert.ok(store.getSnapshot().error);
});
