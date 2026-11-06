import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Check, History, MapPin } from "lucide-react";
import AccountChip from "../components/AccountChip";
import Brand from "../components/Brand";
import SavedPlanResult from "../components/SavedPlanResult";
import { useAuth } from "../auth/AuthProvider";
import {
  getSavedProject,
  getSavedRevision,
  getSavedTrace,
  ProjectsError,
  setSavedFinal,
  type ProjectDetail,
  type RevisionDetail,
  type RunTrace,
} from "../api/projects";

/** 展示服务端保存的计划版本和公开生成轨迹。 */
export default function SavedProjectPage() {
  const { id } = useParams();
  const { user, refreshSession } = useAuth();
  const projectId = Number(id);
  const [params, setParams] = useSearchParams();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [revision, setRevision] = useState<RevisionDetail | null>(null);
  const [trace, setTrace] = useState<RunTrace | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const invalidId = !Number.isSafeInteger(projectId) || projectId < 1;
  const selectedRevisionId =
    Number(params.get("revision")) ||
    project?.final_revision_id ||
    project?.revisions[0]?.id;

  useEffect(() => {
    if (invalidId) return;
    const controller = new AbortController();
    void getSavedProject(projectId, controller.signal)
      .then(setProject)
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          if (cause instanceof ProjectsError && cause.code === "unauthorized")
            void refreshSession();
          setError(cause instanceof Error ? cause.message : "无法读取计划。");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [projectId, user?.id, invalidId, refreshSession]);

  useEffect(() => {
    if (!project || !selectedRevisionId) return;
    const controller = new AbortController();
    void getSavedRevision(project.id, selectedRevisionId, controller.signal)
      .then(setRevision)
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          if (cause instanceof ProjectsError && cause.code === "unauthorized")
            void refreshSession();
          setError(cause instanceof Error ? cause.message : "无法读取版本。");
        }
      });
    return () => controller.abort();
  }, [project, selectedRevisionId, refreshSession]);

  const activeRevision = revision?.id === selectedRevisionId ? revision : null;

  async function chooseFinal() {
    if (
      !project ||
      !activeRevision ||
      activeRevision.id !== selectedRevisionId ||
      saving
    )
      return;
    setSaving(true);
    setNotice("");
    try {
      const updated = await setSavedFinal(project.id, activeRevision.id);
      setProject((current) => (current ? { ...current, ...updated } : current));
      setNotice(`已选定第 ${activeRevision.number} 版为最终方案`);
    } catch (cause) {
      if (cause instanceof ProjectsError && cause.code === "unauthorized")
        void refreshSession();
      setNotice(cause instanceof Error ? cause.message : "保存最终方案失败。");
    } finally {
      setSaving(false);
    }
  }

  async function showTrace() {
    if (
      !project ||
      !activeRevision?.generation_run_id ||
      activeRevision.id !== selectedRevisionId
    )
      return;
    setNotice("");
    try {
      setTrace(
        await getSavedTrace(project.id, activeRevision.generation_run_id),
      );
    } catch (cause) {
      if (cause instanceof ProjectsError && cause.code === "unauthorized")
        void refreshSession();
      setNotice(cause instanceof Error ? cause.message : "无法读取生成轨迹。");
    }
  }

  return (
    <div className="app-shell plans-shell saved-project-shell">
      <header className="topbar">
        <Brand />
        <span className="brand-divider" />
        <Link className="saved-back" to="/plans">
          <ArrowLeft size={16} /> 我的旅行计划
        </Link>
        <AccountChip />
      </header>
      <main className="plans-main saved-project-main">
        {invalidId && (
          <p className="saved-error" role="alert">
            计划 ID 无效。
          </p>
        )}
        {loading && !invalidId && <p role="status">正在读取已保存的计划…</p>}
        {error && (
          <p className="saved-error" role="alert">
            {error}
          </p>
        )}
        {!loading && project && (
          <>
            <div className="saved-heading">
              <div>
                <span className="saved-eyebrow">已保存的计划</span>
                <h1>{project.name}</h1>
                <p>
                  <MapPin size={16} /> {project.destination} ·{" "}
                  {project.revision_count} 个版本
                </p>
              </div>
              <Link className="button secondary" to="/plans">
                返回列表
              </Link>
            </div>
            <div className="saved-layout">
              <aside className="saved-revisions" aria-label="行程版本">
                <h2>
                  <History size={17} /> 行程版本
                </h2>
                {project.revisions.map((item) => (
                  <button
                    key={item.id}
                    className={item.id === selectedRevisionId ? "selected" : ""}
                    onClick={() => {
                      setRevision(null);
                      setTrace(null);
                      setError("");
                      setParams({ revision: String(item.id) });
                    }}
                    aria-pressed={item.id === selectedRevisionId}
                  >
                    <strong>
                      第 {item.number} 版 · {item.title}
                    </strong>
                    <small>
                      {new Date(item.created_at).toLocaleString("zh-CN")}
                    </small>
                    {item.id === project.final_revision_id && <em>最终方案</em>}
                  </button>
                ))}
                {!project.revisions.length && <p>暂无已保存版本。</p>}
              </aside>
              <section className="saved-content">
                {activeRevision?.id !== selectedRevisionId &&
                  !error &&
                  !!project.revisions.length && (
                    <p role="status">正在读取版本…</p>
                  )}
                {activeRevision && (
                  <>
                    <div className="saved-version-header">
                      <div>
                        <span className="saved-eyebrow">
                          第 {activeRevision.number} 版
                        </span>
                        <h2>{activeRevision.title}</h2>
                      </div>
                      <button
                        className="button primary"
                        disabled={
                          saving ||
                          project.final_revision_id === activeRevision.id
                        }
                        onClick={() => void chooseFinal()}
                      >
                        <Check size={16} />
                        {project.final_revision_id === activeRevision.id
                          ? "已设为最终方案"
                          : saving
                            ? "正在保存…"
                            : "设为最终方案"}
                      </button>
                    </div>
                    {notice && (
                      <p className="saved-notice" role="status">
                        {notice}
                      </p>
                    )}
                    <SavedPlanResult result={activeRevision.result} />
                    {activeRevision.generation_run_id && (
                      <button
                        className="saved-trace-button"
                        onClick={() => void showTrace()}
                      >
                        查看生成轨迹
                      </button>
                    )}
                    {trace &&
                      trace.run_id === activeRevision.generation_run_id && (
                        <section className="saved-trace" aria-label="生成轨迹">
                          <h3>
                            生成轨迹 · 第 {trace.run_id} 次运行 ·
                            {trace.status === "succeeded" ? "已完成" : "失败"}
                          </h3>
                          {trace.error_message && <p>{trace.error_message}</p>}
                          {trace.error_stage && (
                            <p>失败阶段：{trace.error_stage}</p>
                          )}
                          {trace.error_code && (
                            <p>错误码：{trace.error_code}</p>
                          )}
                          <p>调研资料与工具证据见上方“调研资料”。</p>
                          {trace.model_calls.map((call) => (
                            <details key={`${call.agent}-${call.call_index}`}>
                              <summary>
                                {call.agent} · 第 {call.call_index} 次调用 ·{" "}
                                {call.model_name}
                              </summary>
                              <p>
                                {new Date(call.started_at).toLocaleString(
                                  "zh-CN",
                                )}
                                {call.finished_at &&
                                  ` 至 ${new Date(call.finished_at).toLocaleString("zh-CN")}`}
                                {call.duration_ms !== null &&
                                  ` · ${call.duration_ms} 毫秒`}
                                {call.provider && ` · ${call.provider}`}
                              </p>
                              {call.content && <pre>{call.content}</pre>}
                              {call.reasoning && (
                                <>
                                  <strong>公开推理</strong>
                                  <pre>{call.reasoning}</pre>
                                </>
                              )}
                              {call.tool_calls &&
                                call.tool_calls.length > 0 && (
                                  <ul>
                                    {call.tool_calls.map((tool, index) => (
                                      <li key={`${tool.id}-${index}`}>
                                        工具调用：{tool.name}
                                        {tool.id && `（${tool.id}）`}
                                      </li>
                                    ))}
                                  </ul>
                                )}
                            </details>
                          ))}
                          {!trace.model_calls.length && (
                            <p>这次运行没有保存公开模型调用。</p>
                          )}
                        </section>
                      )}
                  </>
                )}
              </section>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
