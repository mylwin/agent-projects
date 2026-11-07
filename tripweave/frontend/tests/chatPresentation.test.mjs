import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import ts from "typescript";

async function load(relative) {
  const source = await readFile(new URL(relative, import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ES2022,
    },
  });
  return import(
    `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
  );
}
const {
  aggregateExecution,
  findSubmittedTurn,
  newestResult,
  nearConversationBottom,
  isSendKey,
} = await load("../src/utils/chatConversation.ts");
const { compareRevisionTrips } = await load("../src/utils/revisionChanges.ts");

test("工具开始和终态按call_id更新，记录有界且正文不进过程", () => {
  let steps = aggregateExecution([], {
    event: "tool_start",
    message: "查询中",
    call_id: "a",
  });
  steps = aggregateExecution(steps, {
    event: "tool_error",
    message: "查询失败",
    call_id: "a",
  });
  assert.equal(steps.length, 1);
  assert.equal(steps[0].event, "tool_error");
  assert.deepEqual(
    aggregateExecution(steps, { event: "reply", message: "正文" }),
    steps,
  );
  for (let i = 0; i < 30; i++)
    steps = aggregateExecution(steps, {
      event: "progress",
      message: `阶段${i}`,
    });
  assert.equal(steps.length, 24);
});

test("同文旧消息不能冒充本轮提交，依据不同也不匹配", () => {
  const input = {
    text: "调整",
    draft: "调整",
    baseRevisionId: 2,
    dayId: 1,
    generate: false,
    knownIds: [1],
  };
  const turn = {
    id: 1,
    user_text: "调整",
    base_revision_id: 2,
    day_id: 1,
    generate: false,
  };
  assert.equal(findSubmittedTurn([turn], input), undefined);
  assert.equal(
    findSubmittedTurn([{ ...turn, id: 3, base_revision_id: 1 }], input),
    undefined,
  );
  assert.equal(findSubmittedTurn([{ ...turn, id: 4 }], input).id, 4);
});

test("只同步最新未处理的成功结果，失败与重复回读不跳转", () => {
  const seen = new Set([1]);
  const turns = [
    { id: 1, status: "succeeded", result_revision_id: 1 },
    { id: 2, status: "succeeded", result_revision_id: 2 },
    { id: 3, status: "succeeded", result_revision_id: 3 },
    { id: 4, status: "failed", result_revision_id: 4 },
  ];
  assert.equal(newestResult(turns, seen), 3);
  assert.equal(newestResult(turns, seen), null);
  assert.equal(seen.has(4), false);
});

test("跟随阈值和中文输入法边界明确", () => {
  assert.equal(nearConversationBottom(1000, 528, 400), true);
  assert.equal(nearConversationBottom(1000, 527, 400), false);
  assert.equal(isSendKey("Enter", false, false, 13), true);
  assert.equal(isSendKey("Enter", true, false, 13), false);
  assert.equal(isSendKey("Enter", false, true, 13), false);
  assert.equal(isSendKey("Enter", false, false, 229), false);
});

test("修改清单由版本字段产生，不读取模型回复或补全未知费用", () => {
  const base = {
    destination: "苏州",
    travelers: 2,
    budget: 2000,
    currency: "CNY",
    days: [
      {
        id: 1,
        date: "2026-11-15",
        label: "首日",
        title: "慢游",
        description: "",
        distance: "待核实",
        activities: [
          {
            id: "a",
            time: "14:00",
            title: "散步",
            description: "",
            location: "平江路",
            cost: null,
            point: null,
            kind: "walk",
          },
        ],
      },
    ],
  };
  const next = structuredClone(base);
  next.days[0].activities[0].time = "15:00";
  assert.deepEqual(compareRevisionTrips(base, next), [
    { label: "第 1 天 · 散步 · 时间", before: "14:00", after: "15:00" },
  ]);
  assert.deepEqual(compareRevisionTrips(base, structuredClone(base)), []);
  next.days[0].activities[0].cost = 0;
  assert.deepEqual(compareRevisionTrips(base, next)[1], {
    label: "第 1 天 · 散步 · 费用",
    before: "待核实",
    after: "0",
  });
  next.days[0].activities = [];
  const changes = compareRevisionTrips(base, next);
  assert(changes.some((change) => change.after === "已移除"));
  assert(!changes.some((change) => change.before === "a"));
});
