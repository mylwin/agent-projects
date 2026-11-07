import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import PlannerPage from "./PlannerPage";
import SavedPlanResult from "../components/SavedPlanResult";
import ChatMarkdown from "../components/ChatMarkdown";
import { useAuth } from "../auth/AuthProvider";
import {
  getSavedProject,
  getSavedRevision,
  getSavedTrace,
  saveProjectRevision,
  setSavedFinal,
  ProjectsError,
  type ProjectDetail,
  type RevisionDetail,
  type RunTrace,
} from "../api/projects";
import type { PlanProject, Trip } from "../types/trip";

const agentNames: Record<string, string> = {
  attractions: "景点与活动",
  weather: "天气调研",
  hotels: "住宿调研",
  planner: "行程安排",
};
const toolNames: Record<string, string> = {
  maps_text_search: "地点查询",
  map_search_places: "地点查询",
  maps_search_detail: "地点详情",
  map_place_details: "地点详情",
  maps_geo: "地址查询",
  map_geocode: "地址查询",
  maps_weather: "天气查询",
  map_weather: "天气查询",
  TravelDraft: "行程整理",
};

/** 按调研主题呈现已保存的调用，空正文不占位，同类工具只展示次数。 */
function GenerationTrace({ trace }: { trace: RunTrace }) {
  const groups = new Map<string, RunTrace["model_calls"]>();
  for (const call of trace.model_calls) {
    const calls = groups.get(call.agent) ?? [];
    calls.push(call);
    groups.set(call.agent, calls);
  }
  return (
    <section className="saved-trace">
      <h3>生成轨迹</h3>
      {Array.from(groups, ([agent, calls]) => (
        <details className="saved-trace-group" key={agent}>
          <summary>
            <strong>{agentNames[agent] ?? "其他记录"}</strong>
            <span>{calls.length} 轮记录</span>
          </summary>
          <ol className="saved-trace-steps">
            {calls.map((call) => {
              const content = call.content?.trim();
              const reasoning = call.reasoning?.trim();
              const tools = new Map<string, number>();
              for (const tool of call.tool_calls ?? []) {
                const label = toolNames[tool.name] ?? "资料查询";
                tools.set(label, (tools.get(label) ?? 0) + 1);
              }
              return (
                <li key={call.call_index}>
                  <div className="saved-trace-step-heading">
                    第 {call.call_index} 轮
                  </div>
                  {tools.size > 0 && (
                    <ul className="saved-tool-tags">
                      {Array.from(tools, ([label, count]) => (
                        <li key={label}>
                          {label}
                          <span>{count} 次</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {content && <ChatMarkdown text={content} />}
                  {reasoning && (
                    <details className="saved-trace-notes">
                      <summary>模型附加说明</summary>
                      <ChatMarkdown text={reasoning} />
                    </details>
                  )}
                  {!content && !reasoning && tools.size === 0 && (
                    <p className="saved-empty">本轮没有保存正文或查询操作。</p>
                  )}
                </li>
              );
            })}
          </ol>
        </details>
      ))}
      {trace.model_calls.length === 0 && (
        <p className="saved-empty">本次没有保存公开模型调用。</p>
      )}
    </section>
  );
}

/** 服务端数据容器；同一项目的版本切换不销毁对话草稿。 */
export default function SavedProjectPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const { refreshSession } = useAuth();
  const [params, setParams] = useSearchParams();
  const [draft, setDraft] = useState("");
  const revisionRequest = useRef<AbortController | null>(null);
  const refreshRequest = useRef<AbortController | null>(null);
  const traceRequest = useRef<AbortController | null>(null);
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [revision, setRevision] = useState<RevisionDetail | null>(null);
  const [trace, setTrace] = useState<RunTrace | null>(null);
  const [traceLoading, setTraceLoading] = useState(false);
  const [error, setError] = useState("");
  const [traceError, setTraceError] = useState("");
  const [reload, setReload] = useState(0);
  const invalid = !Number.isSafeInteger(projectId) || projectId < 1;
  const revisionParam = params.get("revision");
  const selected = revisionParam
    ? Number(revisionParam)
    : project?.revisions[0]?.id;
  useEffect(() => {
    if (invalid) return;
    const controller = new AbortController();
    void getSavedProject(projectId, controller.signal)
      .then((detail) => {
        if (!controller.signal.aborted) setProject(detail);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : "无法读取计划");
          if (cause instanceof ProjectsError && cause.code === "unauthorized")
            void refreshSession();
        }
      });
    return () => controller.abort();
  }, [projectId, invalid, reload, refreshSession]);
  useEffect(() => {
    if (!selected || invalid) return;
    const controller = new AbortController();
    revisionRequest.current = controller;
    void getSavedRevision(projectId, selected, controller.signal)
      .then((saved) => {
        if (!controller.signal.aborted) {
          setRevision(saved);
          setError("");
        }
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : "无法读取版本");
          if (cause instanceof ProjectsError && cause.code === "unauthorized")
            void refreshSession();
        }
      });
    return () => controller.abort();
  }, [projectId, selected, invalid, reload, refreshSession]);

  useEffect(
    () => () => {
      refreshRequest.current?.abort();
      traceRequest.current?.abort();
    },
    [],
  );

  /** 读回成功版本；独立取消信号防止离页或旧请求覆盖当前工作区。 */
  const refreshVersion = useCallback(
    async (revisionId: number, signal?: AbortSignal) => {
      refreshRequest.current?.abort();
      const controller = new AbortController();
      refreshRequest.current = controller;
      const abort = () => controller.abort();
      signal?.addEventListener("abort", abort, { once: true });
      if (signal?.aborted) controller.abort();
      try {
        const detail = await getSavedProject(projectId, controller.signal);
        // 若别处又保存了更新版本，当前计划应指向服务端最新摘要，而非退回旧结果。
        const latestId = detail.revisions[0]?.id ?? revisionId;
        const saved = await getSavedRevision(
          projectId,
          latestId,
          controller.signal,
        );
        if (controller.signal.aborted) throw new Error("读取已取消");
        revisionRequest.current?.abort();
        traceRequest.current?.abort();
        setTraceLoading(false);
        setProject(detail);
        setRevision(saved);
        setParams({});
        setError("");
        setTrace(null);
        setTraceError("");
      } catch {
        throw new Error("新版本已保存，但工作区刷新失败，请重试同步。");
      } finally {
        signal?.removeEventListener("abort", abort);
        if (refreshRequest.current === controller)
          refreshRequest.current = null;
      }
    },
    [projectId, setParams],
  );
  /** 保存活动编辑；版本冲突交给界面提示，原输入保留供用户处理。 */
  async function saveTrip(trip: Trip) {
    if (!revision) return;
    const saved = await saveProjectRevision(projectId, revision.id, trip);
    await refreshVersion(saved.id);
  }
  /** 最终方案写回服务端，跨设备可读。 */
  async function chooseFinal(revisionId: number) {
    const summary = await setSavedFinal(projectId, revisionId);
    setProject((current) => (current ? { ...current, ...summary } : current));
  }
  /** 仅请求当前版本关联的公开轨迹，避免旧请求覆盖新版本。 */
  async function showTrace(runId: number) {
    if (traceLoading) return;
    const controller = new AbortController();
    traceRequest.current?.abort();
    traceRequest.current = controller;
    setTraceLoading(true);
    setTraceError("");
    try {
      const saved = await getSavedTrace(projectId, runId, controller.signal);
      if (!controller.signal.aborted) setTrace(saved);
    } catch (cause) {
      if (!controller.signal.aborted)
        setTraceError(
          cause instanceof Error ? cause.message : "无法读取生成轨迹",
        );
    } finally {
      if (traceRequest.current === controller) {
        traceRequest.current = null;
        setTraceLoading(false);
      }
    }
  }

  const invalidRevision =
    revisionParam !== null &&
    (!Number.isSafeInteger(Number(revisionParam)) || Number(revisionParam) < 1);
  if (invalid || invalidRevision || (error && (!project || !revision)))
    return (
      <main className="not-found">
        <h1>
          {invalid ? "计划 ID 无效" : invalidRevision ? "版本 ID 无效" : error}
        </h1>
        <button
          className="button secondary"
          onClick={() => {
            setError("");
            setReload((value) => value + 1);
          }}
        >
          重新读取
        </button>
        <Link className="button primary" to="/plans">
          返回全部计划
        </Link>
      </main>
    );
  if (!project || !revision)
    return (
      <main className="not-found" role="status">
        正在读取行程工作区…
      </main>
    );
  const view: PlanProject = {
    id: `saved-${project.id}`,
    name: project.name,
    createdAt: revision.created_at,
    updatedAt: project.updated_at,
    trip: revision.result.trip,
    messages: [],
    requests: [],
    pending: null,
    draft: false,
    finalRevisionId:
      project.final_revision_id === null
        ? null
        : String(project.final_revision_id),
    revisions: [
      {
        id: String(revision.id),
        number: revision.number,
        title: revision.title,
        createdAt: revision.created_at,
        trip: revision.result.trip,
      },
    ],
  };
  const runId = revision.generation_run_id;
  return (
    <PlannerPage
      project={view}
      server={{
        projectId,
        revisionId: revision.id,
        revisionNumber: revision.number,
        revisions: project.revisions,
        draft,
        setDraft,
        loading: revision.id !== selected || !!error,
        status: (revision.id !== selected || error) && (
          <div
            className="workspace-load-status"
            role={error ? "alert" : "status"}
          >
            <span>
              {error || "正在读取所选版本，暂时显示上一版；对话草稿会保留。"}
            </span>
            {error && (
              <button
                onClick={() => {
                  setError("");
                  setReload((value) => value + 1);
                }}
              >
                重试读取版本
              </button>
            )}
          </div>
        ),
        saveTrip,
        chooseFinal,
        onGenerated: refreshVersion,
        evidence: (
          <details className="workspace-evidence">
            <summary>地点来源、研究证据与生成轨迹</summary>
            <SavedPlanResult result={revision.result} evidenceOnly />
            {runId && (
              <button
                className="saved-trace-button"
                disabled={traceLoading}
                onClick={() => void showTrace(runId)}
              >
                {traceLoading ? "正在读取轨迹…" : "查看生成轨迹"}
              </button>
            )}
            {traceError && (
              <p className="saved-error" role="alert">
                {traceError}
              </p>
            )}
            {trace?.run_id === runId && <GenerationTrace trace={trace} />}
          </details>
        ),
      }}
    />
  );
}
