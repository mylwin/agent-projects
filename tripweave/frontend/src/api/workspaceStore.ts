import fixture from "../data/trip.json";
import type { Message, PlanProject, Trip } from "../types/trip";

const key = "tripweave:workspace:v2";
const listeners = new Set<() => void>();
type Workspace = { version: 2; projects: PlanProject[] };
/**
 * 判断值是否为非空对象。
 *
 * @param value - 待检查的外部数据。
 * @returns 是否可按键读取对象字段。
 */
const isRecord = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object";

/**
 * 校验持久化行程结构，避免损坏的草稿阻止页面打开。
 *
 * @param value - 从本地存储读取的未知数据。
 * @returns 是否满足当前行程结构的检查条件。
 */
function isTrip(value: unknown): value is Trip {
  return (
    isRecord(value) &&
    value.schemaVersion === 1 &&
    typeof value.id === "string" &&
    typeof value.destination === "string" &&
    typeof value.travelers === "number" &&
    Number.isFinite(value.travelers) &&
    value.travelers >= 1 &&
    Number.isFinite(value.budget) &&
    typeof value.currency === "string" &&
    Array.isArray(value.days) &&
    value.days.length > 0 &&
    value.days.every(
      (day) =>
        isRecord(day) &&
        typeof day.id === "number" &&
        typeof day.date === "string" &&
        !Number.isNaN(Date.parse(day.date)) &&
        typeof day.title === "string" &&
        typeof day.label === "string" &&
        typeof day.distance === "string" &&
        typeof day.description === "string" &&
        Array.isArray(day.activities) &&
        day.activities.every(
          (a) =>
            isRecord(a) &&
            typeof a.id === "string" &&
            typeof a.title === "string" &&
            typeof a.time === "string" &&
            typeof a.description === "string" &&
            typeof a.location === "string" &&
            typeof a.kind === "string" &&
            (a.cost === null || Number.isFinite(a.cost)) &&
            (a.point === null ||
              (Array.isArray(a.point) &&
                a.point.length === 2 &&
                a.point.every(Number.isFinite))),
        ),
    )
  );
}
/**
 * 检查本地对话记录的基本结构。
 *
 * @param value - 待检查的消息集合。
 * @returns 是否为包含有效角色和文本的消息数组。
 */
function isMessages(value: unknown): value is Message[] {
  return (
    Array.isArray(value) &&
    value.every(
      (message) =>
        isRecord(message) &&
        typeof message.id === "string" &&
        ["assistant", "user"].includes(String(message.role)) &&
        typeof message.content === "string" &&
        typeof message.time === "string",
    )
  );
}
/**
 * 检查项目、版本及待处理要求的持久化结构。
 *
 * @param value - 待检查的项目数据。
 * @returns 是否满足当前项目结构的检查条件。
 */
function isProject(value: unknown): value is PlanProject {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.name === "string" &&
    typeof value.updatedAt === "string" &&
    !Number.isNaN(Date.parse(value.updatedAt)) &&
    typeof value.createdAt === "string" &&
    !Number.isNaN(Date.parse(value.createdAt)) &&
    isTrip(value.trip) &&
    isMessages(value.messages) &&
    Array.isArray(value.requests) &&
    value.requests.every(
      (r) =>
        isRecord(r) &&
        typeof r.dayId === "number" &&
        typeof r.text === "string",
    ) &&
    Array.isArray(value.revisions) &&
    value.revisions.length > 0 &&
    value.revisions.every(
      (r) =>
        isRecord(r) &&
        typeof r.id === "string" &&
        typeof r.number === "number" &&
        typeof r.title === "string" &&
        isTrip(r.trip),
    ) &&
    (value.pending === null ||
      (isRecord(value.pending) &&
        typeof value.pending.text === "string" &&
        typeof value.pending.dayId === "number"))
  );
}

/**
 * 创建带初始版本的旅行项目，尚不写入存储。
 *
 * @param name - 项目展示名称。
 * @param trip - 初始行程，复制后分配项目 ID。
 * @param messages - 初始对话，空数组时创建默认欢迎语。
 * @returns 包含初始版本、对话和创建时间的新项目。
 */
export function newProject(
  name: string,
  trip: Trip,
  messages: Message[] = [],
): PlanProject {
  const now = new Date().toISOString();
  const id = crypto.randomUUID();
  const initialTrip = { ...structuredClone(trip), id };
  const revisionId = crypto.randomUUID();
  return {
    id,
    name,
    createdAt: now,
    updatedAt: now,
    trip: initialTrip,
    messages: messages.length
      ? messages
      : [
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: `「${name}」的旅行文件夹已准备好。可以从下方例子开始调整，结果和对话都会留在这个计划里。`,
            time: "刚刚",
            revisionId,
          },
        ],
    requests: [],
    revisions: [
      {
        id: revisionId,
        number: 1,
        title: "初始行程",
        createdAt: now,
        trip: structuredClone(initialTrip),
      },
    ],
    draft: false,
    finalRevisionId: null,
    pending: null,
  };
}

/**
 * 读取工作区；首次打开时迁移旧单行程存储，旧键保留用于恢复。
 *
 * @returns 工作区及读取错误；读取失败时使用初始行程。
 */
function load(): { workspace: Workspace; error: string | null } {
  const { messages, ...trip } = fixture;
  let project = newProject(
    "苏州三日慢游",
    trip,
    messages.map((m) => ({
      ...m,
      role: m.role === "assistant" ? "assistant" : "user",
    })),
  );
  try {
    const raw = localStorage.getItem(key);
    if (raw) {
      const data: unknown = JSON.parse(raw);
      if (
        !isRecord(data) ||
        data.version !== 2 ||
        !Array.isArray(data.projects) ||
        !data.projects.every(isProject) ||
        new Set(data.projects.map((p) => p.id)).size !== data.projects.length
      )
        throw new Error("invalid");
      const workspace = data as Workspace;
      workspace.projects = workspace.projects.map((p) => ({
        ...p,
        finalRevisionId:
          typeof p.finalRevisionId === "string" &&
          p.revisions.some((r) => r.id === p.finalRevisionId)
            ? p.finalRevisionId
            : null,
      }));
      return { workspace, error: null };
    }
    const old = localStorage.getItem("tripweave:journal:v1");
    if (old) {
      const data: unknown = JSON.parse(old);
      if (isRecord(data) && isTrip(data.trip) && isMessages(data.messages)) {
        project = newProject("苏州三日慢游", data.trip, data.messages);
        if (
          Array.isArray(data.requests) &&
          data.requests.every(
            (r) =>
              isRecord(r) &&
              typeof r.dayId === "number" &&
              typeof r.text === "string",
          )
        )
          project.requests = data.requests;
      }
    }
    project.id = "suzhou-initial";
    project.trip.id = project.id;
    project.revisions[0].id = "suzhou-initial-r1";
    project.revisions[0].trip.id = project.id;
    return { workspace: { version: 2, projects: [project] }, error: null };
  } catch {
    project.id = "suzhou-initial";
    project.trip.id = project.id;
    project.revisions[0].id = "suzhou-initial-r1";
    project.revisions[0].trip.id = project.id;
    return {
      workspace: { version: 2, projects: [project] },
      error: "无法读取浏览器里的旅行记录，已打开初始行程。原存储内容未删除。",
    };
  }
}

let snapshot = load();
/**
 * 读取供 React 订阅的当前内存快照。
 *
 * @returns 工作区及最近一次读写错误，引用保持到下次提交。
 */
export const getSnapshot = () => snapshot;
/**
 * 订阅工作区快照变化。
 *
 * @param listener - 每次提交后执行的通知回调。
 * @returns 取消订阅的清理函数。
 */
export function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * 一次写入全部项目；失败时仍保留内存数据并通知订阅者。
 *
 * @param workspace - 将替换当前工作区的完整数据。
 * @returns 是否成功写入浏览器本地存储。
 */
function commit(workspace: Workspace): boolean {
  let error: string | null = null;
  try {
    localStorage.setItem(key, JSON.stringify(workspace));
  } catch {
    error = "保存失败，当前内容仍保留在页面中，请重试保存。";
  }
  snapshot = { workspace, error };
  listeners.forEach((listener) => listener());
  return error === null;
}
/**
 * 将新项目放在工作区首位并保存。
 *
 * @param project - 待加入的完整旅行项目。
 */
export function addProject(project: PlanProject) {
  commit({ version: 2, projects: [project, ...snapshot.workspace.projects] });
}
/**
 * 更新指定项目、刷新修改时间并保存整个工作区。
 *
 * @param id - 待更新项目的标识。
 * @param update - 根据当前项目返回新项目的同步函数。
 * @returns 是否成功写入浏览器本地存储；失败时内存更新仍保留。
 */
export function updateProject(
  id: string,
  update: (project: PlanProject) => PlanProject,
) {
  return commit({
    version: 2,
    projects: snapshot.workspace.projects.map((project) =>
      project.id === id
        ? { ...update(project), updatedAt: new Date().toISOString() }
        : project,
    ),
  });
}
/**
 * 重试保存当前内存中的完整工作区。
 *
 * @returns 是否成功写入浏览器本地存储。
 */
export function retrySave() {
  return commit(snapshot.workspace);
}
/**
 * 为项目追加行程快照，由调用方负责持久化。
 *
 * @param project - 当前旅行项目。
 * @param title - 新版本的展示标题。
 * @param trip - 新版本的行程，默认使用项目当前行程。
 * @returns 追加版本并清除草稿标记的新项目。
 */
export function saveRevision(
  project: PlanProject,
  title: string,
  trip = project.trip,
): PlanProject {
  return {
    ...project,
    trip,
    draft: false,
    revisions: [
      ...project.revisions,
      {
        id: crypto.randomUUID(),
        number: project.revisions.length + 1,
        title,
        createdAt: new Date().toISOString(),
        trip: structuredClone(trip),
      },
    ],
  };
}
