import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
} from "react";
import {
  BookOpen,
  CalendarDays,
  Check,
  CircleAlert,
  ChevronLeft,
  ChevronRight,
  ArrowLeft,
  Info,
  CircleCheck,
  History,
  PanelRightOpen,
  Coffee,
  Flower2,
  Footprints,
  Hotel,
  Landmark,
  MapPin,
  Map,
  Image,
  MessageCircle,
  Pencil,
  Utensils,
  X,
  type LucideIcon,
} from "lucide-react";
import { Link, useBlocker, useSearchParams } from "react-router-dom";
import type { Activity, PlanProject, Trip } from "../types/trip";
import RouteMap from "../components/RouteMap";
import AssistantPanel from "../components/AssistantPanel";
import Brand from "../components/Brand";
import { saveRevision, updateProject } from "../api/workspaceStore";

const icons: Record<string, LucideIcon> = {
  breakfast: Coffee,
  garden: Landmark,
  food: Utensils,
  museum: BookOpen,
  walk: Footprints,
  lotus: Flower2,
  hotel: Hotel,
};
/**
 * 展示项目行程、历史版本和本地调整助手。
 *
 * @param props - 页面属性。
 * @param props.project - 当前旅行项目及其行程、对话和历史版本。
 * @returns 可编辑的行程详情页面。
 */
export default function PlannerPage({ project }: { project: PlanProject }) {
  const [params, setParams] = useSearchParams();
  const viewedRevision = project.revisions.find(
    (revision) => revision.id === params.get("revision"),
  );
  const trip = viewedRevision?.trip ?? project.trip;
  const [dayId, setDayId] = useState(trip.days.length > 1 ? 2 : 1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState<Activity | null>(null);
  const [showInfo, setShowInfo] = useState(false);
  const [leaveError, setLeaveError] = useState("");
  const [mobileTab, setMobileTab] = useState<"trip" | "assistant">("trip");
  const [collapsed, setCollapsed] = useState(false);
  const [visualView, setVisualView] = useState<"map" | "photo">("map");
  const [busy, setBusy] = useState(false);
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const finalRevision = project.revisions.find(
    (revision) => revision.id === project.finalRevisionId,
  );
  const displayedRevision =
    viewedRevision ?? (!project.draft ? project.revisions.at(-1) : undefined);
  const isFinal =
    !!displayedRevision && displayedRevision.id === project.finalRevisionId;
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      !isFinal && currentLocation.pathname !== nextLocation.pathname,
  );
  const leaving = blocker.state === "blocked";
  const requests = project.requests;
  /**
   * 更新当前行程，内容变化时追加手动调整版本。
   *
   * @param next - 新行程或从当前行程计算新值的同步函数。
   * @returns 是否成功写入浏览器本地存储。
   */
  function setTrip(next: Trip | ((current: Trip) => Trip)) {
    return updateProject(project.id, (current) => {
      const trip = typeof next === "function" ? next(current.trip) : next;
      if (JSON.stringify(trip) === JSON.stringify(current.trip)) return current;
      return saveRevision(current, "手动调整行程", trip);
    });
  }
  /**
   * 将当前查看的版本写入 URL 查询参数。
   *
   * @param id - 要查看的历史版本 ID。
   */
  function viewRevision(id: string) {
    setParams({ revision: id });
  }
  /**
   * 清除侧栏的悬停定时器。
   */
  function cancelHover() {
    if (hoverTimer.current) {
      clearTimeout(hoverTimer.current);
      hoverTimer.current = null;
    }
  }
  /**
   * 切换助手侧栏折叠状态并恢复移动端行程标签。
   */
  function toggleAssistant() {
    cancelHover();
    setCollapsed((value) => !value);
    setMobileTab("trip");
  }
  const day = trip.days.find((entry) => entry.id === dayId) ?? trip.days[0];
  const date = new Date(`${day.date}T12:00:00`);
  const dayDate = new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
  }).format(date);
  const weekday = new Intl.DateTimeFormat("zh-CN", { weekday: "long" }).format(
    date,
  );
  /**
   * 将行程日期格式化为中文展示文本。
   *
   * @param value - YYYY-MM-DD 格式的行程日期。
   * @param year - 是否显示年份，默认 false。
   * @returns 按中文区域格式显示的日期。
   */
  const formatTripDate = (value: string, year = false) =>
    new Intl.DateTimeFormat("zh-CN", {
      ...(year ? { year: "numeric" as const } : {}),
      month: "long",
      day: "numeric",
    }).format(new Date(`${value}T12:00:00`));
  const hasUnknownCost = trip.days.some((entry) =>
    entry.activities.some((activity) => activity.cost === null),
  );
  const activityCost = trip.days.reduce(
    (total, entry) =>
      total +
      entry.activities.reduce(
        (cost, activity) => cost + (activity.cost ?? 0),
        0,
      ),
    0,
  );
  const dayRequests = requests.filter((request) => request.dayId === dayId);

  useEffect(
    () => () => {
      if (noticeTimer.current) clearTimeout(noticeTimer.current);
      if (hoverTimer.current) clearTimeout(hoverTimer.current);
    },
    [],
  );
  useEffect(() => {
    if (!editing && !showInfo && !leaving) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]');
    const focusables = () =>
      Array.from(
        dialog?.querySelectorAll<HTMLElement>(
          'button, input, textarea, [tabindex="0"]',
        ) ?? [],
      ).filter((element) => !element.hasAttribute("disabled"));
    focusables()[0]?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    /**
     * 处理弹窗 Escape 关闭与 Tab 焦点循环。
     *
     * @param event - 文档键盘事件。
     */
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setEditing(null);
        setShowInfo(false);
        if (blocker.state === "blocked") blocker.reset();
        setLeaveError("");
      }
      if (event.key !== "Tab") return;
      const elements = focusables();
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("keydown", handleKey);
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, [editing, showInfo, leaving, blocker]);

  /**
   * 显示短暂通知并替换已有的通知定时器。
   *
   * @param text - 需要展示的通知内容。
   */
  function inform(text: string) {
    setNotice(text);
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    noticeTimer.current = setTimeout(() => setNotice(""), 4500);
  }

  /**
   * 将当前查看版本设为最终方案并保存。
   *
   * @returns 是否成功写入浏览器本地存储。
   */
  function chooseFinal() {
    let number = 0;
    const success = updateProject(project.id, (current) => {
      const next =
        !viewedRevision && current.draft
          ? saveRevision(current, "此前的手动调整")
          : current;
      const chosen = viewedRevision
        ? next.revisions.find((revision) => revision.id === viewedRevision.id)
        : next.revisions.at(-1);
      if (!chosen) return current;
      number = chosen.number;
      return { ...next, finalRevisionId: chosen.id };
    });
    inform(
      success
        ? `已选定第 ${number} 版为最终方案`
        : "保存失败，当前选择仍保留在页面中",
    );
    return success;
  }

  /**
   * 取消离页导航并清除离页错误提示。
   */
  function stayOnPlan() {
    if (blocker.state === "blocked") blocker.reset();
    setLeaveError("");
  }

  /**
   * 保存最终方案，成功后继续被阻止的导航。
   */
  function finalizeAndLeave() {
    if (blocker.state !== "blocked" || busy) return;
    if (chooseFinal()) blocker.proceed();
    else setLeaveError("未能保存到浏览器，请重试。当前选择和行程仍在页面中。");
  }

  /**
   * 切换行程日期并清除活动选择。
   *
   * @param id - 要查看的日期 ID。
   */
  function switchDay(id: number) {
    setDayId(id);
    setSelectedId(null);
  }

  /**
   * 选中活动并滚动到对应卡片。
   *
   * @param id - 活动标识，同时作为卡片 DOM ID。
   */
  function selectActivity(id: string) {
    setSelectedId(id);
    setVisualView("map");
    document
      .getElementById(id)
      ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  /**
   * 读取活动编辑表单并保存新的行程版本。
   *
   * @param event - 活动编辑表单的提交事件。
   */
  function updateActivity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing) return;
    const form = new FormData(event.currentTarget);
    const title = String(form.get("title") ?? "").trim();
    const description = String(form.get("description") ?? "").trim();
    const time = String(form.get("time") ?? "").trim();
    if (!title || !time) return;
    if (
      title === editing.title &&
      time === editing.time &&
      description === editing.description
    ) {
      setEditing(null);
      return;
    }
    const success = setTrip((current) => ({
      ...current,
      days: current.days.map((entry) =>
        entry.id !== dayId
          ? entry
          : {
              ...entry,
              activities: entry.activities.map((activity) =>
                activity.id !== editing.id
                  ? activity
                  : { ...activity, title, description, time },
              ),
            },
      ),
    }));
    setEditing(null);
    inform(
      success
        ? "活动已更新，已自动记录一个新版本"
        : "保存失败，修改仍保留在页面中，请重试",
    );
  }

  return (
    <div className="app-shell planner-shell">
      <header className="topbar">
        <Brand />
        <span className="brand-divider" aria-hidden="true" />
        <span className="product-label">旅行计划</span>
        <div className="detail-nav-actions">
          <button
            className="detail-info-button"
            aria-label="查看出行信息"
            onClick={() => setShowInfo(true)}
          >
            <Info size={17} />
            出行信息
          </button>
        </div>
      </header>

      <nav className="mobile-nav" aria-label="工作区切换">
        <button
          className={mobileTab === "trip" ? "active" : ""}
          onClick={() => setMobileTab("trip")}
        >
          我的行程
        </button>
        <button
          className={mobileTab === "assistant" ? "active" : ""}
          onClick={() => {
            setMobileTab("assistant");
            setCollapsed(false);
          }}
        >
          旅行助手{requests.length > 0 && <span>{requests.length}</span>}
        </button>
      </nav>

      <main
        className={`workspace plan-workspace ${collapsed ? "assistant-collapsed" : ""}`}
      >
        <section
          className={`journal ${mobileTab === "trip" ? "mobile-visible" : ""}`}
          aria-label="旅行行程"
        >
          <div className="journal-scroll">
            {viewedRevision && (
              <div className="revision-notice">
                <History size={15} />
                <span>
                  正在查看第 {viewedRevision.number} 版：{viewedRevision.title}
                </span>
                <button onClick={() => setParams({})}>返回当前计划</button>
              </div>
            )}
            <nav className="project-breadcrumb" aria-label="计划导航">
              <Link className="plans-back" to="/plans">
                <ArrowLeft size={18} />
                返回全部计划
              </Link>
              <span className="plan-kind">旅行计划</span>
            </nav>
            <div className="journal-heading">
              <h1>{project.name}</h1>
              {isFinal && <span className="draft-status">最终方案</span>}
            </div>
            <p className="plan-trip-summary">
              <span>
                <MapPin size={15} />
                目的地：{trip.destination}
              </span>
              <span>
                {trip.days.length} 天游 · {trip.travelers} 人
              </span>
              <span>预算 ¥{trip.budget.toLocaleString("zh-CN")}</span>
            </p>
            <div
              className="day-tabs"
              role="tablist"
              aria-label="选择旅行日期"
              style={{ "--day-count": trip.days.length } as CSSProperties}
            >
              <div
                className="tab-indicator"
                style={{ transform: `translateX(${(dayId - 1) * 100}%)` }}
              />
              {trip.days.map((entry) => (
                <button
                  key={entry.id}
                  id={`day-tab-${entry.id}`}
                  role="tab"
                  aria-selected={dayId === entry.id}
                  aria-controls="day-panel"
                  className={dayId === entry.id ? "active" : ""}
                  onClick={() => switchDay(entry.id)}
                >
                  <span>第 {entry.id} 天</span>
                  <small>{entry.label}</small>
                </button>
              ))}
            </div>
            <div
              id="day-panel"
              className="day-panel"
              role="tabpanel"
              aria-labelledby={`day-tab-${dayId}`}
            >
              <div className="day-intro">
                <div>
                  <p className="eyebrow">DAY {day.id}</p>
                  <h2>{day.title}</h2>
                  <p className="day-description">{day.description}</p>
                </div>
                <div className="date-stamp">
                  <span>
                    {weekday} · 第 {day.id} 天
                  </span>
                  <span>
                    <CalendarDays size={15} />
                    {dayDate}
                  </span>
                </div>
              </div>
              <div className="day-content">
                <ol className="timeline">
                  {day.activities.map((activity) => {
                    const Icon = icons[activity.kind] ?? MapPin;
                    return (
                      <li
                        id={activity.id}
                        key={activity.id}
                        className={`timeline-item ${selectedId === activity.id ? "selected" : ""}`}
                      >
                        <span className="activity-icon">
                          <Icon size={20} strokeWidth={1.4} />
                        </span>
                        <span className="activity-time">{activity.time}</span>
                        <div className="activity-content">
                          <button
                            className="activity-title"
                            onClick={() => {
                              if (viewedRevision || busy) {
                                inform(
                                  "请返回当前计划，或等待当前调整完成后再编辑",
                                );
                                return;
                              }
                              setSelectedId(activity.id);
                              setEditing(activity);
                            }}
                          >
                            {activity.title}
                            <Pencil size={12} />
                          </button>
                          <p>{activity.description}</p>
                          <button
                            className="location-link"
                            onClick={() => selectActivity(activity.id)}
                          >
                            <MapPin size={13} />
                            {activity.location}
                          </button>
                        </div>
                      </li>
                    );
                  })}
                </ol>
                <aside className="visual-column" aria-label="目的地与路线">
                  <div
                    className="visual-switch"
                    role="group"
                    aria-label="目的地视图"
                  >
                    <button
                      aria-pressed={visualView === "map"}
                      aria-controls="destination-map"
                      onClick={() => setVisualView("map")}
                    >
                      <Map size={16} />
                      路线地图
                    </button>
                    <button
                      aria-pressed={visualView === "photo"}
                      aria-controls="destination-photo"
                      onClick={() => setVisualView("photo")}
                    >
                      <Image size={16} />
                      目的地照片
                    </button>
                  </div>
                  <div
                    className="visual-pane"
                    hidden={visualView !== "map"}
                    id="destination-map"
                  >
                    <div className="map-heading">
                      <h3>当日路线</h3>
                      <span>
                        {
                          day.activities.filter((activity) => activity.point)
                            .length
                        }{" "}
                        个地点
                      </span>
                    </div>
                    <div className="map-frame">
                      <RouteMap
                        activities={day.activities}
                        selectedId={selectedId}
                        onSelect={selectActivity}
                      />
                      <div className="map-legend">
                        <span>
                          <i />
                          当日动线（
                          {day.distance === "待核实"
                            ? "里程待核实"
                            : `约 ${day.distance} 公里`}
                          ）
                        </span>
                        <span>
                          <Footprints size={13} />
                          步行为主 · 慢慢逛
                        </span>
                      </div>
                    </div>
                    <p className="route-caption">
                      路线为示意，出发前请核实具体位置。
                    </p>
                  </div>
                  <figure
                    className="garden-photo visual-pane"
                    hidden={visualView !== "photo"}
                    id="destination-photo"
                  >
                    <img
                      src="/images/suzhou-garden.png"
                      alt="白墙黛瓦的月洞门框住一院春色与水中倒影"
                    />
                    <figcaption>
                      <span>园林一隅 · 框住一院江南</span>
                      <span>江南 · 春日</span>
                    </figcaption>
                  </figure>
                </aside>
              </div>
              {dayRequests.length > 0 && (
                <section className="request-list">
                  <h3>
                    <MessageCircle size={16} />
                    当天的调整清单 <small>待处理</small>
                  </h3>
                  {dayRequests.map((request, index) => (
                    <p key={index}>
                      {request.text}
                      <button
                        aria-label={`移除调整要求：${request.text}`}
                        disabled={!!viewedRevision || busy}
                        onClick={() => {
                          updateProject(project.id, (current) => ({
                            ...current,
                            requests: current.requests.filter(
                              (entry) => entry !== request,
                            ),
                          }));
                        }}
                      >
                        <X size={14} />
                      </button>
                    </p>
                  ))}
                </section>
              )}
            </div>
          </div>
          <div className="journal-footnote final-selection-bar">
            <div className="version-control">
              <label className="revision-picker">
                <History size={17} />
                <span className="sr-only">行程版本</span>
                <select
                  aria-label="行程版本"
                  value={viewedRevision?.id ?? ""}
                  disabled={busy}
                  onChange={(event) =>
                    event.target.value
                      ? viewRevision(event.target.value)
                      : setParams({})
                  }
                >
                  <option value="">
                    当前计划 · {project.revisions.length} 个版本
                  </option>
                  {project.revisions
                    .slice()
                    .reverse()
                    .map((revision) => (
                      <option key={revision.id} value={revision.id}>
                        第 {revision.number} 版 · {revision.title}
                      </option>
                    ))}
                </select>
              </label>
              <span
                className={isFinal ? "final-label selected" : "final-label"}
              >
                {isFinal ? (
                  <>
                    <CircleCheck size={15} />
                    这是选定的最终方案
                  </>
                ) : finalRevision ? (
                  `最终方案：第 ${finalRevision.number} 版`
                ) : (
                  "挑选满意的版本，作为最终方案"
                )}
              </span>
            </div>
            <button
              className="choose-final-button"
              onClick={chooseFinal}
              disabled={isFinal || busy}
            >
              {isFinal ? (
                <>
                  <Check size={14} />
                  已选定
                </>
              ) : (
                "选为最终方案"
              )}
            </button>
          </div>
        </section>

        <div
          className={`assistant-slot ${mobileTab === "assistant" ? "mobile-visible" : ""}`}
          onPointerEnter={(event) => {
            if (event.pointerType === "mouse" && collapsed) {
              cancelHover();
              hoverTimer.current = setTimeout(() => {
                setCollapsed(false);
                hoverTimer.current = null;
              }, 1000);
            }
          }}
          onPointerLeave={cancelHover}
        >
          <button
            className="sidebar-toggle"
            aria-label={collapsed ? "展开旅行助手" : "收起旅行助手"}
            aria-expanded={!collapsed}
            aria-controls="plan-assistant"
            onClick={toggleAssistant}
          >
            {collapsed ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
          </button>
          {collapsed && (
            <button
              className="assistant-rail"
              aria-label="展开旅行助手"
              onClick={() => {
                cancelHover();
                setCollapsed(false);
              }}
            >
              <PanelRightOpen size={21} />
              <span>旅行助手</span>
              {busy && <i className="rail-working" />}
            </button>
          )}
          <aside
            id="plan-assistant"
            className="assistant mobile-visible"
            aria-label="当前计划的旅行助手"
            inert={collapsed}
          >
            <AssistantPanel
              project={project}
              dayId={dayId}
              active={mobileTab === "assistant"}
              readOnly={!!viewedRevision}
              onRevision={viewRevision}
              onBusy={setBusy}
            />
          </aside>
        </div>
      </main>
      <div
        className={`toast ${notice ? "visible" : ""}`}
        role="status"
        aria-live="polite"
      >
        {notice && (
          <>
            {notice.startsWith("保存失败") ? (
              <CircleAlert size={17} />
            ) : (
              <Check size={17} />
            )}
            {notice}
          </>
        )}
      </div>
      {editing && (
        <div className="modal-backdrop" onClick={() => setEditing(null)}>
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="activity-dialog-title"
            onClick={(event) => event.stopPropagation()}
            onKeyDown={(event) => {
              if (event.key === "Escape") setEditing(null);
            }}
          >
            <div className="modal-heading">
              <h2 id="activity-dialog-title">编辑这一站</h2>
              <button
                className="icon-button"
                aria-label="关闭编辑"
                onClick={() => setEditing(null)}
              >
                <X />
              </button>
            </div>
            <form onSubmit={updateActivity}>
              <label>
                活动名称
                <input
                  name="title"
                  defaultValue={editing.title}
                  required
                  maxLength={45}
                  autoFocus
                />
              </label>
              <label>
                时间安排
                <input
                  name="time"
                  defaultValue={editing.time}
                  required
                  maxLength={35}
                />
              </label>
              <label>
                旅行笔记
                <textarea
                  name="description"
                  defaultValue={editing.description}
                  maxLength={180}
                />
              </label>
              <div className="modal-actions">
                <button
                  type="button"
                  className="button secondary"
                  onClick={() => setEditing(null)}
                >
                  取消
                </button>
                <button className="button primary" type="submit">
                  更新活动
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
      {leaving && (
        <div className="modal-backdrop" onClick={stayOnPlan}>
          <section
            className="modal leave-plan-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="leave-plan-title"
            aria-describedby="leave-plan-description"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-heading">
              <h2 id="leave-plan-title">返回前，选定这一版？</h2>
              <button
                className="icon-button"
                aria-label="继续查看计划"
                onClick={stayOnPlan}
              >
                <X size={20} />
              </button>
            </div>
            <p id="leave-plan-description">
              将正在查看的行程设为最终方案，下次打开就能直接查看。
            </p>
            <div className="leave-plan-preview">
              <span className="leave-version">
                第 {displayedRevision?.number ?? project.revisions.length + 1}{" "}
                版
              </span>
              <strong>{project.name}</strong>
              <span>{displayedRevision?.title ?? "当前手动调整"}</span>
            </div>
            <p className="leave-plan-note">
              {busy
                ? "助手仍在调整中。现在返回会暂停调整，可下次继续。"
                : finalRevision
                  ? `当前最终方案为第 ${finalRevision.number} 版；也可以保留原选择。`
                  : "也可以稍后再选，行程和对话都会保留。"}
            </p>
            {leaveError && (
              <p className="leave-plan-error" role="alert">
                {leaveError}
              </p>
            )}
            <div className="modal-actions">
              <button
                className="button secondary leave-without-final"
                onClick={() => blocker.proceed()}
              >
                {finalRevision ? "保留原方案，返回" : "稍后选择，返回"}
              </button>
              <button
                className="button primary finalize-and-leave"
                disabled={busy}
                onClick={finalizeAndLeave}
              >
                选定并返回
              </button>
            </div>
          </section>
        </div>
      )}
      {showInfo && (
        <div className="modal-backdrop" onClick={() => setShowInfo(false)}>
          <section
            className="modal trip-info"
            role="dialog"
            aria-modal="true"
            aria-labelledby="trip-info-title"
            onClick={(event) => event.stopPropagation()}
            onKeyDown={(event) => {
              if (event.key === "Escape") setShowInfo(false);
            }}
          >
            <div className="modal-heading">
              <div>
                <h2 id="trip-info-title">出行信息</h2>
                <p className="trip-info-project">{project.name}</p>
              </div>
              <button
                autoFocus
                className="icon-button"
                aria-label="关闭出行信息"
                onClick={() => setShowInfo(false)}
              >
                <X />
              </button>
            </div>
            <div className="trip-info-destination">
              <span>
                <MapPin size={17} />
                目的地
              </span>
              <div>
                <strong>{trip.destination}</strong>
                <p>
                  {trip.days.length} 天 {Math.max(0, trip.days.length - 1)} 晚{" "}
                  <span>·</span> {trip.travelers} 人同行
                </p>
              </div>
            </div>
            <section className="trip-info-dates" aria-label="旅行日期">
              <span>
                <CalendarDays size={17} />
                旅行日期
              </span>
              <p>
                {formatTripDate(trip.days[0].date)} <span>—</span>{" "}
                {formatTripDate(trip.days.at(-1)!.date)}
              </p>
              <small>
                {trip.days[0].date.slice(0, 4)} 年
                {trip.days[0].date.slice(0, 4) !==
                trip.days.at(-1)!.date.slice(0, 4)
                  ? ` — ${trip.days.at(-1)!.date.slice(0, 4)} 年`
                  : ""}
              </small>
            </section>
            <dl className="trip-info-budget">
              <div>
                <dt>全团预算</dt>
                <dd>
                  <span>¥</span>
                  {trip.budget.toLocaleString()}
                </dd>
                <p>不含往返大交通</p>
              </div>
              <div>
                <dt>活动费用估计</dt>
                <dd>
                  {!hasUnknownCost && <span>¥</span>}
                  {hasUnknownCost ? "待核实" : activityCost.toLocaleString()}
                </dd>
                <p>不含住宿与未列项目</p>
              </div>
            </dl>
            <div className="trip-info-notes">
              <h3>出发前确认</h3>
              <ul>
                <li>景点预约、开放时间与门票价格</li>
                <li>地点间的实际路线与交通安排</li>
              </ul>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
