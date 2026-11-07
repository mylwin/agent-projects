import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import PlannerPage from "./PlannerPage";
import SavedPlanResult from "../components/SavedPlanResult";
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

/** 服务端数据容器：行程、编辑、版本、对话和证据统一使用既有工作区。 */
export default function SavedProjectPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const { refreshSession } = useAuth();
  const [params, setParams] = useSearchParams();
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
      .then(setProject)
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
    void getSavedRevision(projectId, selected, controller.signal)
      .then(setRevision)
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : "无法读取版本");
          if (cause instanceof ProjectsError && cause.code === "unauthorized")
            void refreshSession();
        }
      });
    return () => controller.abort();
  }, [projectId, selected, invalid, reload, refreshSession]);

  /** 成功提交后同步服务端摘要并回到最新版本，不写入浏览器草稿。 */
  async function refreshVersion(revisionId: number) {
    let detail: ProjectDetail;
    let saved: RevisionDetail;
    try {
      [detail, saved] = await Promise.all([
        getSavedProject(projectId),
        getSavedRevision(projectId, revisionId),
      ]);
    } catch {
      throw new Error("新版本已保存，但工作区刷新失败，请刷新页面查看。");
    }
    setProject(detail);
    setRevision(saved);
    setParams({});
    setTrace(null);
    setTraceError("");
  }
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
    setTraceLoading(true);
    setTraceError("");
    try {
      setTrace(await getSavedTrace(projectId, runId));
    } catch (cause) {
      setTraceError(
        cause instanceof Error ? cause.message : "无法读取生成轨迹",
      );
    } finally {
      setTraceLoading(false);
    }
  }

  const invalidRevision =
    revisionParam !== null &&
    (!Number.isSafeInteger(Number(revisionParam)) || Number(revisionParam) < 1);
  if (invalid || invalidRevision || error)
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
  if (!project || !revision || revision.id !== selected)
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
        revisions: project.revisions,
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
            {trace?.run_id === runId && (
              <section className="saved-trace">
                <h3>公开生成轨迹</h3>
                {trace.model_calls.map((call) => (
                  <details key={`${call.agent}-${call.call_index}`}>
                    <summary>
                      {call.agent} · 第 {call.call_index} 次调用
                    </summary>
                    {call.content && <pre>{call.content}</pre>}
                    {call.reasoning && <pre>{call.reasoning}</pre>}
                    {call.tool_calls?.map((tool, index) => (
                      <p key={index}>工具：{tool.name}</p>
                    ))}
                  </details>
                ))}
                {trace.model_calls.length === 0 && (
                  <p>本次没有保存公开模型调用。</p>
                )}
              </section>
            )}
          </details>
        ),
      }}
    />
  );
}
