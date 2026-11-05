import fixture from "../data/trip.json";
import type { Message, PlanProject, Trip } from "../types/trip";

const key = "tripweave:workspace:v2";
const listeners = new Set<() => void>();
type Workspace = { version: 2; projects: PlanProject[] };
const isRecord = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object";

/** 校验持久化结构，避免损坏的草稿阻止页面打开。 */
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

/** 新工作区首次打开时迁移旧单行程存储，旧键保留用于恢复。 */
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
export const getSnapshot = () => snapshot;
export function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** 单次原子写入全部项目；失败时仍保留内存数据供重试。 */
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
export function addProject(project: PlanProject) {
  commit({ version: 2, projects: [project, ...snapshot.workspace.projects] });
}
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
export function retrySave() {
  return commit(snapshot.workspace);
}
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
