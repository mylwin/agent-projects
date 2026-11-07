/** 已保存项目接口；所有请求由浏览器携带登录 Cookie。 */

import type { Trip } from "../types/trip";

type ApiSuccess<T> = { success: true; data: T };
type ApiFailure = { success: false; error: { code: string; message: string } };

export class ProjectsError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ProjectsError";
  }
}

export interface ProjectSummary {
  id: number;
  name: string;
  destination: string;
  updated_at: string;
  final_revision_id: number | null;
  revision_count: number;
}

export interface RevisionSummary {
  id: number;
  number: number;
  title: string;
  created_at: string;
  generation_run_id: number | null;
}

export interface ProjectDetail extends ProjectSummary {
  revisions: RevisionSummary[];
}

export interface RevisionDetail extends RevisionSummary {
  project_id: number;
  result: SavedPlanResult;
}

export interface SavedPlace {
  id: string;
  name: string;
  address: string;
  longitude: number;
  latitude: number;
  coordinate_system: "GCJ-02" | "BD-09";
  source: "amap" | "baidu";
  fetched_at: string;
}

export interface ToolEvidence {
  tool: string;
  content: string;
  structured_content: Record<string, unknown> | null;
  fetched_at: string;
}

export interface ResearchReport {
  topic: "attractions" | "weather" | "hotels";
  summary: string;
  warnings: string[];
  evidence: ToolEvidence[];
}

export interface SavedPlanResult {
  trip: Trip;
  places: SavedPlace[];
  warnings: string[];
  reply: string;
  research: ResearchReport[];
}

export interface RunTrace {
  run_id: number;
  project_id: number;
  status: string;
  error_stage: string | null;
  error_code: string | null;
  error_message: string | null;
  research: ResearchReport[];
  model_calls: {
    agent: string;
    call_index: number;
    model_name: string;
    provider: string | null;
    reasoning: string | null;
    content: string | null;
    tool_calls: { name: string; id: string }[] | null;
    started_at: string;
    finished_at: string | null;
    duration_ms: number | null;
  }[];
}

export interface GeneratePlanInput {
  name: string;
  destination: string;
  start_date: string;
  day_count: number;
  travelers: number;
  budget: string;
  pace: "relaxed" | "balanced" | "packed";
  interests: string[];
  instruction: string;
}

export interface GeneratedPlan extends SavedPlanResult {
  project_id: number;
  revision_id: number;
  run_id: number;
}

/** 读取统一响应；服务失败时保留后端错误码与说明。 */
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      credentials: "include",
      ...init,
      headers: {
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...init.headers,
      },
    });
  } catch {
    throw new ProjectsError("network_error", "无法连接计划服务，请稍后重试。");
  }
  let body: ApiSuccess<T> | ApiFailure;
  try {
    body = await response.json();
  } catch {
    throw new ProjectsError(
      `http_${response.status}`,
      "计划服务返回了无效数据。",
    );
  }
  if (!response.ok || body.success !== true) {
    const error = body.success === false ? body.error : null;
    throw new ProjectsError(
      error?.code ?? `http_${response.status}`,
      error?.message ?? "计划服务暂时不可用，请稍后重试。",
    );
  }
  return body.data;
}

/** 读取全部已保存项目，按后端分页逐页获取。 */
export async function listSavedProjects(
  signal?: AbortSignal,
): Promise<ProjectSummary[]> {
  const items: ProjectSummary[] = [];
  let page = 1;
  let total = 0;
  do {
    const result = await request<{
      items: ProjectSummary[];
      total: number;
      page: number;
      page_size: number;
    }>(`/api/projects?page=${page}&pageSize=100`, { signal });
    items.push(...result.items);
    total = result.total;
    if (result.items.length === 0) break;
    page += 1;
  } while (items.length < total);
  return items;
}

export function getSavedProject(id: number, signal?: AbortSignal) {
  return request<ProjectDetail>(`/api/projects/${id}`, { signal });
}

export function getSavedRevision(
  projectId: number,
  revisionId: number,
  signal?: AbortSignal,
) {
  return request<RevisionDetail>(
    `/api/projects/${projectId}/revisions/${revisionId}`,
    { signal },
  );
}

export function setSavedFinal(projectId: number, revisionId: number) {
  return request<ProjectSummary>(`/api/projects/${projectId}/final`, {
    method: "POST",
    body: JSON.stringify({ revision_id: revisionId }),
  });
}

export function getSavedTrace(
  projectId: number,
  runId: number,
  signal?: AbortSignal,
) {
  return request<RunTrace>(`/api/projects/${projectId}/runs/${runId}/trace`, {
    signal,
  });
}

/** 规划期间由服务端真实回调产生的进度，不包含工具原始参数。 */
export interface GenerationProgress {
  event:
    | "started"
    | "progress"
    | "model_start"
    | "model_end"
    | "tool_start"
    | "tool_end"
    | "tool_error";
  message: string;
  call_id?: string;
}

/** 生成并保存行程；逐帧处理 SSE，只有持久化成功才兑现最终结果。 */
export async function generateSavedPlan(
  input: GeneratePlanInput,
  onProgress: (event: GenerationProgress) => void,
  signal: AbortSignal,
): Promise<GeneratedPlan> {
  let response: Response;
  try {
    response = await fetch("/api/plans/generate", {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(input),
      signal,
    });
  } catch (cause) {
    if (signal.aborted) throw cause;
    throw new ProjectsError("network_error", "无法连接计划服务，请稍后重试。");
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as ApiFailure | null;
    throw new ProjectsError(
      body?.error?.code ?? `http_${response.status}`,
      body?.error?.message ?? "无法开始生成，请稍后重试。",
    );
  }
  if (
    !response.headers.get("content-type")?.includes("text/event-stream") ||
    !response.body
  ) {
    throw new ProjectsError("invalid_stream", "计划服务未返回有效的进度流。");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      // 服务端使用 LF；同时接受 CRLF，兼容代理和测试中的分帧。
      buffer = buffer.replace(/\r\n/g, "\n");
      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const data = frame
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n");
        if (!data) continue; // 心跳注释不表示进度。
        const event = JSON.parse(data) as
          | GenerationProgress
          | { event: "complete"; data: GeneratedPlan }
          | { event: "error"; error: { code: string; message: string } };
        if (event.event === "error")
          throw new ProjectsError(event.error.code, event.error.message);
        if (event.event === "complete") return event.data;
        onProgress(event);
      }
      if (done)
        throw new ProjectsError(
          "stream_interrupted",
          "生成连接已中断，尚未收到保存成功的确认。请检查计划列表后再重试。",
        );
    }
  } catch (cause) {
    if (signal.aborted || cause instanceof ProjectsError) throw cause;
    throw new ProjectsError(
      "stream_interrupted",
      "生成连接异常，尚未收到保存成功的确认。请检查计划列表后再重试。",
    );
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
