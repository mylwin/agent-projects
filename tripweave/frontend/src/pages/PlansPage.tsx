import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowUpRight,
  CalendarDays,
  FolderOpen,
  MessageCircle,
  MapPin,
  Plus,
  Search,
  Sparkles,
  UsersRound,
  X,
} from "lucide-react";
import {
  ProjectsError,
  generateSavedPlan,
  listSavedProjects,
  type ProjectSummary,
  type GenerationProgress,
} from "../api/projects";
import { useAuth } from "../auth/AuthProvider";
import { useWorkspace } from "../hooks/useWorkspace";
import Brand from "../components/Brand";
import AccountChip from "../components/AccountChip";

/**
 * 展示服务端计划与本地草稿，并生成新的服务端计划。
 *
 * @returns 旅行计划列表及新建表单。
 */
export default function PlansPage() {
  const { workspace } = useWorkspace();
  const { user, refreshSession } = useAuth();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const [createPending, setCreatePending] = useState(false);
  const [createError, setCreateError] = useState("");
  const [progress, setProgress] = useState<GenerationProgress[]>([]);
  const generationController = useRef<AbortController | null>(null);
  const progressLog = useRef<HTMLOListElement>(null);
  useEffect(() => () => generationController.current?.abort(), []);
  useEffect(() => {
    if (progressLog.current) {
      progressLog.current.scrollTop = progressLog.current.scrollHeight;
      progressLog.current.scrollIntoView({ block: "nearest" });
    }
  }, [progress]);
  const [savedProjects, setSavedProjects] = useState<ProjectSummary[]>([]);
  const [savedOwnerId, setSavedOwnerId] = useState<number | null>(null);
  const [savedLoading, setSavedLoading] = useState(true);
  const [savedError, setSavedError] = useState("");
  const [reloadSaved, setReloadSaved] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void listSavedProjects(controller.signal)
      .then((projects) => {
        setSavedProjects(projects);
        setSavedOwnerId(user?.id ?? null);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          if (cause instanceof ProjectsError && cause.code === "unauthorized")
            void refreshSession();
          setSavedError(
            cause instanceof Error ? cause.message : "无法读取已保存的计划。",
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setSavedLoading(false);
      });
    return () => controller.abort();
  }, [user?.id, reloadSaved, refreshSession]);
  const visibleSavedProjects = savedOwnerId === user?.id ? savedProjects : [];
  const savedFiltered = visibleSavedProjects.filter((project) =>
    `${project.name} ${project.destination}`.includes(query.trim()),
  );
  const filtered = workspace.projects
    .filter((p) => `${p.name} ${p.trip.destination}`.includes(query.trim()))
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  /** 打开新建表单时清除上轮生成记录和错误。 */
  function openCreate() {
    setProgress([]);
    setCreateError("");
    setCreating(true);
  }
  /**
   * 从表单读取需求，调用生成接口并打开保存后的版本。
   *
   * @param event - 新建计划表单的提交事件。
   */
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (createPending || generationController.current) return;
    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") ?? "").trim();
    const destination = String(form.get("destination") ?? "").trim();
    const start = String(form.get("date") ?? "");
    const travelers = Number(form.get("travelers"));
    const budget = String(form.get("budget") ?? "");
    const count = Number(form.get("days"));
    if (!name || !destination) return;
    const controller = new AbortController();
    generationController.current = controller;
    setProgress([]);
    setCreatePending(true);
    setCreateError("");
    try {
      const result = await generateSavedPlan(
        {
          name,
          destination,
          start_date: start,
          day_count: count,
          travelers,
          budget,
          pace: "balanced",
          interests: [],
          instruction: String(form.get("instruction") ?? "").trim(),
        },
        (event) => setProgress((current) => [...current, event]),
        controller.signal,
      );
      navigate(
        `/saved-projects/${result.project_id}?revision=${result.revision_id}`,
      );
    } catch (cause) {
      if (controller.signal.aborted) return;
      if (cause instanceof ProjectsError && cause.code === "unauthorized")
        void refreshSession();
      setCreateError(
        cause instanceof Error ? cause.message : "生成失败，请稍后重试。",
      );
    } finally {
      generationController.current = null;
      setCreatePending(false);
    }
  }
  return (
    <div className="app-shell plans-shell">
      <header className="topbar">
        <Brand />
        <span className="brand-divider" />
        <span className="product-label">我的旅行计划</span>
        <span className="plans-top-note">把想去的地方，慢慢变成旅程。</span>
        <button className="button primary new-plan-button" onClick={openCreate}>
          <Plus size={17} />
          <span className="new-plan-label">新建计划</span>
        </button>
        <AccountChip />
      </header>
      <main className="plans-main">
        <div className="plans-intro">
          <div>
            <h1>我的旅行计划</h1>
            <p>每一趟旅程，一个专属文件夹。行程、调整结果和对话，都在这里。</p>
          </div>
          <span className="plan-count">
            {workspace.projects.length + visibleSavedProjects.length}{" "}
            <small>个旅行计划</small>
          </span>
        </div>
        <div className="plans-toolbar">
          <span>
            <FolderOpen size={18} />
            全部计划 <small>{filtered.length + savedFiltered.length}</small>
          </span>
          <label className="plan-search">
            <Search size={16} />
            <input
              aria-label="搜索旅行计划"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索计划或目的地"
            />
          </label>
        </div>
        <section
          className="saved-projects-section"
          aria-label="已保存到服务端的计划"
        >
          <div className="saved-section-heading">
            <h2>已保存的计划</h2>
            <span>{visibleSavedProjects.length} 个</span>
          </div>
          {savedLoading && <p role="status">正在读取已保存的计划…</p>}
          {savedError && (
            <p className="saved-error" role="alert">
              {savedError}{" "}
              <button
                onClick={() => {
                  setSavedLoading(true);
                  setSavedError("");
                  setReloadSaved((value) => value + 1);
                }}
              >
                重试
              </button>
            </p>
          )}
          {!savedLoading && !savedError && savedFiltered.length === 0 && (
            <p className="saved-empty">
              {query ? "没有匹配的已保存计划。" : "还没有保存到服务端的计划。"}
            </p>
          )}
          <div className="saved-card-grid">
            {savedFiltered.map((project) => (
              <Link
                className="saved-project-card"
                to={`/saved-projects/${project.id}`}
                key={project.id}
              >
                <span>
                  <FolderOpen size={19} /> 已保存 · {project.revision_count}{" "}
                  个版本
                </span>
                <strong>{project.name}</strong>
                <small>
                  <MapPin size={14} /> {project.destination}
                </small>
                <small>
                  {new Date(project.updated_at).toLocaleDateString("zh-CN")}{" "}
                  更新
                </small>
                {project.final_revision_id && <em>已选最终方案</em>}
                <ArrowUpRight className="saved-card-arrow" size={18} />
              </Link>
            ))}
          </div>
        </section>
        <div className="saved-section-heading">
          <h2>本地草稿</h2>
          <span>{workspace.projects.length} 个</span>
        </div>
        <div className="project-grid">
          {filtered.map((project) => {
            const final = project.revisions.find(
              (revision) => revision.id === project.finalRevisionId,
            );
            const cardTrip = final?.trip ?? project.trip;
            const planUrl = `/plans/${project.id}${final ? `?revision=${final.id}` : ""}`;
            const previews = project.revisions.slice(-2).reverse();
            return (
              <article className="project-card" key={project.id}>
                <Link
                  className="project-cover"
                  to={planUrl}
                  aria-label={`打开${project.name}`}
                >
                  <img src="/images/suzhou-garden.png" alt="江南园林与月洞门" />
                </Link>
                <div className="project-card-body">
                  <div className="project-status">
                    <span>
                      {project.pending
                        ? "有未完成的调整"
                        : final
                          ? `最终方案 · 第 ${final.number} 版`
                          : "尚未选定最终方案"}
                    </span>
                    <time>
                      {new Intl.DateTimeFormat("zh-CN", {
                        month: "numeric",
                        day: "numeric",
                      }).format(new Date(project.updatedAt))}{" "}
                      更新
                    </time>
                  </div>
                  <h2>
                    <Link to={planUrl}>{project.name}</Link>
                  </h2>
                  <div className="project-meta">
                    <span>
                      <MapPin size={14} />
                      {cardTrip.destination}
                    </span>
                    <span>
                      <CalendarDays size={14} />
                      {cardTrip.days.length} 天
                    </span>
                    <span>
                      <UsersRound size={14} />
                      {cardTrip.travelers} 人
                    </span>
                    <span>¥{cardTrip.budget.toLocaleString()}</span>
                  </div>
                  <div className="project-results">
                    <div>
                      <span>行程版本</span>
                      <small>{project.revisions.length} 个版本</small>
                    </div>
                    {previews.map((revision) => (
                      <Link
                        className="result-link"
                        to={`/plans/${project.id}?revision=${revision.id}`}
                        key={revision.id}
                      >
                        <span className="version-mark">
                          {String(revision.number).padStart(2, "0")}
                        </span>
                        <span>{revision.title}</span>
                        {revision.id === project.finalRevisionId && (
                          <span className="final-chip">最终</span>
                        )}
                        <ArrowUpRight size={14} />
                      </Link>
                    ))}
                  </div>
                  <div className="project-card-footer">
                    <span>
                      <MessageCircle size={14} />
                      {project.messages.length} 条对话
                    </span>
                    <div className="project-card-links">
                      {final && <Link to={planUrl}>查看方案</Link>}
                      <Link to={`/plans/${project.id}`}>
                        {final ? "继续规划" : "打开计划"}
                      </Link>
                    </div>
                  </div>
                </div>
              </article>
            );
          })}
          <button className="new-project-card" onClick={openCreate}>
            <span>
              <Plus size={26} strokeWidth={1.2} />
            </span>
            <strong>下一程，想去哪里？</strong>
            <small>新建计划</small>
          </button>
        </div>
        {!filtered.length && !!query && (
          <p className="empty-search">
            没有找到这个计划。
            <button onClick={() => setQuery("")}>查看全部计划</button>
          </p>
        )}
        <div className="plans-tip">
          <Sparkles size={16} />
          <p>
            进入计划后，可以与助手继续对话，也可以查看每次调整留下的行程版本。
          </p>
        </div>
      </main>
      <footer className="plans-footer">
        一份计划，收藏一路的期待。<span>TripWeave · 途织</span>
      </footer>
      {creating && (
        <div
          className="modal-backdrop"
          onClick={() => !createPending && setCreating(false)}
        >
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-title"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === "Escape" && !createPending) setCreating(false);
              if (e.key === "Tab") {
                const items = Array.from(
                  e.currentTarget.querySelectorAll<HTMLElement>(
                    "button,input,select,textarea",
                  ),
                );
                if (e.shiftKey && document.activeElement === items[0]) {
                  e.preventDefault();
                  items.at(-1)?.focus();
                } else if (
                  !e.shiftKey &&
                  document.activeElement === items.at(-1)
                ) {
                  e.preventDefault();
                  items[0]?.focus();
                }
              }
            }}
          >
            <div className="modal-heading">
              <h2 id="create-title">为下一程建个文件夹</h2>
              <button
                className="icon-button"
                aria-label="关闭新建计划"
                onClick={() => setCreating(false)}
                disabled={createPending}
              >
                <X />
              </button>
            </div>
            <form onSubmit={create}>
              <fieldset
                className="generation-fields"
                disabled={createPending}
                hidden={createPending}
              >
                <label>
                  计划名称
                  <input
                    name="name"
                    autoFocus
                    required
                    maxLength={40}
                    placeholder="例如：周末苏州慢游"
                  />
                </label>
                <label>
                  目的地
                  <input
                    name="destination"
                    required
                    maxLength={100}
                    placeholder="例如：成都"
                  />
                </label>
                <label>
                  出发日期
                  <input name="date" type="date" max="2100-12-28" required />
                </label>
                <div className="form-pair">
                  <label>
                    出游天数
                    <select name="days" defaultValue="3">
                      <option value="1">1 天</option>
                      <option value="2">2 天</option>
                      <option value="3">3 天</option>
                      <option value="4">4 天</option>
                      <option value="5">5 天</option>
                    </select>
                  </label>
                  <label>
                    同行人数
                    <input
                      name="travelers"
                      type="number"
                      min="1"
                      max="12"
                      defaultValue="2"
                      required
                    />
                  </label>
                </div>
                <label>
                  全团预算（元）
                  <input
                    name="budget"
                    type="number"
                    min="0.01"
                    max="1000000"
                    step="0.01"
                    defaultValue="3000"
                    required
                  />
                </label>
                <label>
                  补充要求（选填）
                  <textarea
                    name="instruction"
                    maxLength={500}
                    rows={3}
                    placeholder="例如：节奏轻松，想尝尝当地小吃"
                  />
                </label>
              </fieldset>
              {progress.length > 0 && (
                <section
                  className="generation-progress"
                  aria-label="行程生成进度"
                >
                  <p role="status">
                    {createPending
                      ? progress.at(-1)?.message
                      : "本次生成已结束"}
                  </p>
                  <ol
                    ref={progressLog}
                    role="log"
                    aria-label="实际生成记录"
                    aria-live="polite"
                    aria-relevant="additions"
                  >
                    {progress.map((event, index) => (
                      <li
                        key={index}
                        className={
                          event.event === "tool_error"
                            ? "generation-tool-error"
                            : ""
                        }
                      >
                        {event.message}
                      </li>
                    ))}
                  </ol>
                </section>
              )}
              {createError && (
                <p className="saved-error" role="alert">
                  {createError}
                </p>
              )}
              <button
                className="button primary create-plan-submit"
                type="submit"
                disabled={createPending}
              >
                <FolderOpen size={16} />
                {createPending ? "正在生成并保存行程…" : "生成并保存计划"}
              </button>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}
