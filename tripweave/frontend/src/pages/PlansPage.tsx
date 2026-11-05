import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowUpRight,
  CalendarDays,
  FolderOpen,
  MessageCircle,
  Plus,
  Search,
  Sparkles,
  UsersRound,
  X,
} from "lucide-react";
import fixture from "../data/trip.json";
import { addProject, newProject } from "../api/workspaceStore";
import { useWorkspace } from "../hooks/useWorkspace";
import Brand from "../components/Brand";

export default function PlansPage() {
  const { workspace } = useWorkspace();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const filtered = workspace.projects
    .filter((p) => `${p.name} ${p.trip.destination}`.includes(query.trim()))
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") ?? "").trim();
    if (!name) return;
    const start = String(form.get("date"));
    const travelers = Number(form.get("travelers"));
    const budget = Number(form.get("budget"));
    const count = Number(form.get("days"));
    if (
      !Number.isFinite(Date.parse(start)) ||
      !Number.isInteger(travelers) ||
      travelers < 1 ||
      travelers > 12 ||
      !Number.isFinite(budget) ||
      budget < 100 ||
      count < 1 ||
      count > 3
    )
      return;
    const trip = structuredClone({
      schemaVersion: fixture.schemaVersion,
      id: fixture.id,
      destination: fixture.destination,
      travelers: fixture.travelers,
      budget: fixture.budget,
      currency: fixture.currency,
      days: fixture.days,
    });
    trip.travelers = travelers;
    trip.budget = budget;
    trip.days = trip.days.slice(0, count).map((day, index) => {
      const date = new Date(`${start}T12:00:00`);
      date.setDate(date.getDate() + index);
      return {
        ...day,
        date: `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`,
        activities: day.activities.map((activity) => ({
          ...activity,
          cost: Math.round((activity.cost / 2) * travelers),
        })),
      };
    });
    const project = newProject(name, trip);
    addProject(project);
    navigate(`/plans/${project.id}`);
  }
  return (
    <div className="app-shell plans-shell">
      <header className="topbar">
        <Brand />
        <span className="brand-divider" />
        <span className="product-label">我的旅行计划</span>
        <span className="plans-top-note">把想去的地方，慢慢变成旅程。</span>
        <button
          className="button primary new-plan-button"
          onClick={() => setCreating(true)}
        >
          <Plus size={17} />
          新建计划
        </button>
      </header>
      <main className="plans-main">
        <div className="plans-intro">
          <div>
            <p className="eyebrow">YOUR TRAVEL JOURNAL</p>
            <h1>我的旅行计划</h1>
            <p>每一趟旅程，一个专属文件夹。行程、调整结果和对话，都在这里。</p>
          </div>
          <span className="plan-count">
            {workspace.projects.length} <small>个旅行计划</small>
          </span>
        </div>
        <div className="plans-toolbar">
          <span>
            <FolderOpen size={18} />
            全部计划 <small>{filtered.length}</small>
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
                  <span className="folder-badge">
                    <FolderOpen size={15} />
                    {cardTrip.destination}
                  </span>
                  <span className="cover-arrow">
                    <ArrowUpRight size={20} />
                  </span>
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
                      <span>已制定的结果</span>
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
                    {previews.length === 1 && (
                      <div className="result-spacer" aria-hidden="true" />
                    )}
                  </div>
                  <div className="project-card-footer">
                    <span>
                      <MessageCircle size={14} />
                      {project.messages.length} 条对话
                    </span>
                    <div className="project-card-links">
                      {final && (
                        <Link to={planUrl}>
                          查看方案 <ArrowUpRight size={14} />
                        </Link>
                      )}
                      <Link to={`/plans/${project.id}`}>
                        {final ? "继续规划" : "打开计划"}
                        <ArrowUpRight size={14} />
                      </Link>
                    </div>
                  </div>
                </div>
              </article>
            );
          })}
          <button
            className="new-project-card"
            onClick={() => setCreating(true)}
          >
            <span>
              <Plus size={26} strokeWidth={1.2} />
            </span>
            <strong>下一程，想去哪里？</strong>
            <small>新建一个旅行计划</small>
          </button>
        </div>
        {!filtered.length && (
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
        <div className="modal-backdrop" onClick={() => setCreating(false)}>
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-title"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === "Escape") setCreating(false);
              if (e.key === "Tab") {
                const items = Array.from(
                  e.currentTarget.querySelectorAll<HTMLElement>(
                    "button,input,select",
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
              >
                <X />
              </button>
            </div>
            <form onSubmit={create}>
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
              <p className="new-plan-city">目的地：苏州 · 从园林与水巷开始</p>
              <label>
                出发日期
                <input
                  name="date"
                  type="date"
                  defaultValue="2027-03-12"
                  min="2026-01-01"
                  max="2100-12-28"
                  required
                />
              </label>
              <div className="form-pair">
                <label>
                  出游天数
                  <select name="days" defaultValue="3">
                    <option value="1">1 天</option>
                    <option value="2">2 天</option>
                    <option value="3">3 天</option>
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
                  min="100"
                  max="1000000"
                  defaultValue="3000"
                  required
                />
              </label>
              <button
                className="button primary create-plan-submit"
                type="submit"
              >
                <FolderOpen size={16} />
                创建旅行计划
              </button>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}
