import examples from "../data/assistant-examples.json";
import type { Trip } from "../types/trip";

export { examples };

/** 本地规则仅演示明确支持的调整，不冒充大模型推理。 */
export function planLocally(trip: Trip, dayId: number, input: string) {
  const match = /不想|不要|不吃|取消|别/.test(input)
    ? undefined
    : /预算|省钱|便宜/.test(input)
      ? examples.find((example) => example.id === "budget")
      : examples.find((example) =>
          example.keywords.some((keyword) => input.includes(keyword)),
        );
  const day = trip.days.find((entry) => entry.id === dayId);
  if (!match || !day)
    return {
      trip,
      title: "",
      changed: false,
      reply:
        "这条要求已经留在当前计划的调整清单里，尚未自动修改行程。你也可以点击活动标题直接编辑安排；目前支持下方示例中的轻松节奏、清淡午餐和餐饮预算调整。",
    };
  const next = structuredClone(trip);
  const target = next.days.find((entry) => entry.id === dayId)!;
  let changed = false;
  if (match.id === "relax") {
    const reverseIndex = target.activities
      .slice()
      .reverse()
      .findIndex(
        (a) =>
          ["garden", "museum", "walk", "lotus"].includes(a.kind) &&
          Number.parseInt(a.time, 10) >= 12,
      );
    const index =
      reverseIndex < 0 ? -1 : target.activities.length - 1 - reverseIndex;
    if (index >= 0) {
      target.activities[index] = {
        ...target.activities[index],
        title: "自由时光 · 随心慢逛",
        description: "不再安排固定景点，留给休息、喝茶或在附近散步。",
        location: "自由安排",
        kind: "free",
        point: null,
        cost: 0,
      };
      target.distance = "待核实";
      changed = true;
    }
  } else {
    target.activities = target.activities.map((a) => {
      if (a.kind !== "food") return a;
      if (match.id === "budget" && a.cost !== null && a.cost <= 40 * trip.travelers) return a;
      const updated =
        match.id === "budget"
          ? {
              ...a,
              title: "午餐 · 苏式简餐",
              description:
                "以汤面、时蔬为主，餐费按每人 ¥40 估计，实际以店内菜单为准。",
              cost: 40 * trip.travelers,
            }
          : {
              ...a,
              title: "午餐 · 清淡苏帮菜",
              description:
                "选择清炒虾仁、清蒸鱼和时蔬，少油少盐；菜单与营业情况请提前核实。",
            };
      changed ||= JSON.stringify(updated) !== JSON.stringify(a);
      return updated;
    });
  }
  return {
    trip: changed ? next : trip,
    title: match.title,
    changed,
    reply: changed
      ? `已为第 ${dayId} 天${match.title}，其他日期保持原样。`
      : "当前安排已经符合这项调整，没有重复生成新版本。可以换个要求，或直接编辑具体活动。",
  };
}
