import type { Trip } from "../types/trip";

export interface RevisionChange {
  label: string;
  before: string;
  after: string;
}

/** 从读回的两个行程逐字段比较，不使用助手的自然语言推断修改。 */
export function compareRevisionTrips(
  base: Trip,
  result: Trip,
): RevisionChange[] {
  const changes: RevisionChange[] = [];
  /** 只记录确实变化的服务端值，未知费用等空值明确标为待核实。 */
  function compare(label: string, before: unknown, after: unknown) {
    if (JSON.stringify(before) === JSON.stringify(after)) return;
    const display = (value: unknown) =>
      value === null || value === undefined
        ? "待核实"
        : typeof value === "object"
          ? JSON.stringify(value)
          : String(value);
    changes.push({ label, before: display(before), after: display(after) });
  }
  for (const [key, label] of [
    ["destination", "目的地"],
    ["travelers", "同行人数"],
    ["budget", "预算"],
    ["currency", "币种"],
  ] as const) {
    compare(label, base[key], result[key]);
  }
  compare(
    "日期顺序",
    base.days.map((day) => day.id).join("、"),
    result.days.map((day) => day.id).join("、"),
  );
  for (const id of new Set(
    [...base.days, ...result.days].map((day) => day.id),
  )) {
    const before = base.days.find((day) => day.id === id);
    const after = result.days.find((day) => day.id === id);
    if (!before || !after) {
      changes.push({
        label: `第 ${id} 天`,
        before: before?.title ?? "无",
        after: after?.title ?? "已移除",
      });
      continue;
    }
    for (const [key, label] of [
      ["date", "日期"],
      ["label", "标签"],
      ["title", "主题"],
      ["description", "说明"],
      ["distance", "路程"],
    ] as const) {
      compare(`第 ${id} 天 · ${label}`, before[key], after[key]);
    }
    if (
      before.activities.map((a) => a.id).join("、") !==
      after.activities.map((a) => a.id).join("、")
    ) {
      compare(
        `第 ${id} 天 · 活动顺序`,
        before.activities.map((a) => a.title).join(" → "),
        after.activities.map((a) => a.title).join(" → "),
      );
    }
    for (const activityId of new Set(
      [...before.activities, ...after.activities].map(
        (activity) => activity.id,
      ),
    )) {
      const old = before.activities.find(
        (activity) => activity.id === activityId,
      );
      const next = after.activities.find(
        (activity) => activity.id === activityId,
      );
      const label = `第 ${id} 天 · ${next?.title ?? old?.title}`;
      if (!old || !next) {
        changes.push({
          label,
          before: old ? `${old.time} ${old.title}` : "无",
          after: next ? `${next.time} ${next.title}` : "已移除",
        });
        continue;
      }
      for (const [key, field] of [
        ["time", "时间"],
        ["title", "名称"],
        ["description", "说明"],
        ["location", "地点"],
        ["cost", "费用"],
        ["kind", "类别"],
        ["placeId", "地点引用"],
        ["point", "示意位置"],
      ] as const) {
        compare(`${label} · ${field}`, old[key], next[key]);
      }
    }
  }
  return changes;
}
