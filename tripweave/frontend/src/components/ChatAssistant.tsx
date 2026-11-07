import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ArrowUpRight,
  PanelRightClose,
  RefreshCw,
  Send,
  Sparkles,
  Square,
  UserRound,
} from "lucide-react";
import {
  getProjectMessages,
  sendProjectMessage,
  ProjectsError,
  type ConversationTurn,
} from "../api/projects";
import { useAuth } from "../auth/AuthProvider";
import ChatMarkdown from "./ChatMarkdown";

/** 同一工作区内的真实聊天；当前日期和依据版本随每轮明确发送。 */
export default function ChatAssistant({
  projectId,
  name,
  revisionId,
  dayId,
  active,
  historical,
  onBusy,
  onRevision,
  onSaved,
  onCollapse,
}: {
  projectId: number;
  name: string;
  revisionId: number;
  dayId: number;
  active: boolean;
  historical: boolean;
  onBusy: (busy: boolean) => void;
  onRevision: (id: string) => void;
  onSaved: (revisionId: number) => Promise<void>;
  onCollapse: () => void;
}) {
  const { refreshSession } = useAuth();
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [reload, setReload] = useState(0);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState("");
  const [live, setLive] = useState("");
  const [phase, setPhase] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const aborter = new AbortController();
    void getProjectMessages(projectId, aborter.signal)
      .then((data) => {
        if (!aborter.signal.aborted) {
          setTurns(data);
          setLoadFailed(false);
        }
      })
      .catch((cause: unknown) => {
        if (!aborter.signal.aborted) {
          setError(cause instanceof Error ? cause.message : "无法读取对话");
          setLoadFailed(true);
          if (cause instanceof ProjectsError && cause.code === "unauthorized")
            void refreshSession();
        }
      })
      .finally(() => {
        if (!aborter.signal.aborted) setLoading(false);
      });
    return () => aborter.abort();
  }, [projectId, reload, refreshSession]);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "nearest" });
  }, [turns, live, phase, pending, active]);

  /** 逐帧展示公开回复；只有服务端确认的新版本才刷新行程。 */
  async function run(generate: boolean) {
    const text =
      input.trim() || (generate ? "请基于当前需求重新生成整趟行程" : "");
    if (
      !text ||
      controller.current ||
      loading ||
      loadFailed ||
      (generate && historical)
    )
      return;
    const aborter = new AbortController();
    controller.current = aborter;
    setBusy(true);
    onBusy(true);
    setError("");
    setInput("");
    setPending(text);
    setLive("");
    setPhase("正在连接旅行助手");
    try {
      const turn = await sendProjectMessage(
        projectId,
        { text, base_revision_id: revisionId, day_id: dayId, generate },
        (event) => {
          if (aborter.signal.aborted) return;
          if (event.event === "reply") setLive(event.message);
          else setPhase(event.message);
        },
        aborter.signal,
      );
      setTurns((current) => [
        ...current.filter((entry) => entry.id !== turn.id),
        turn,
      ]);
      if (turn.result_revision_id) await onSaved(turn.result_revision_id);
    } catch (cause) {
      setError(
        aborter.signal.aborted
          ? "已停止本轮请求。"
          : cause instanceof Error
            ? cause.message
            : "对话未完成，请重试。",
      );
      if (cause instanceof ProjectsError && cause.code === "unauthorized")
        void refreshSession();
      // 服务端保留失败或中断轮次，重新读取后可继续对话。
      try {
        setTurns(await getProjectMessages(projectId));
      } catch {
        setLoadFailed(true);
      }
    } finally {
      if (controller.current === aborter) {
        controller.current = null;
        setBusy(false);
        onBusy(false);
        setPending("");
        setLive("");
        setPhase("");
      }
    }
  }
  /** 发送普通消息；回车不会隐式触发整趟规划。 */
  function submit(event: FormEvent) {
    event.preventDefault();
    void run(false);
  }
  return (
    <>
      <div className="assistant-heading">
        <h2>
          <Sparkles size={22} strokeWidth={1.5} />
          旅行助手
        </h2>
        <button
          className="assistant-collapse-button icon-button"
          aria-label="收起旅行助手"
          onClick={onCollapse}
        >
          <PanelRightClose size={19} />
        </button>
      </div>
      <div className="conversation-project">
        <span>当前计划：{name}</span>
        <small>自动保存</small>
      </div>
      <div className="messages" aria-label="当前计划的对话历史">
        {loading && <p role="status">正在读取对话…</p>}
        {!loading && !turns.length && (
          <p className="chat-welcome">
            可以聊聊旅行想法、问我为什么这样安排，或让我调整某一天已有活动的安排。当前选中第{" "}
            {dayId} 天。
          </p>
        )}
        {turns.map((turn) => (
          <div className="chat-turn" key={turn.id}>
            <div className="message from-user">
              <span className="message-avatar">
                <UserRound size={17} />
              </span>
              <div className="message-body">
                <div className="message-bubble">{turn.user_text}</div>
                <small>
                  第 {turn.day_id} 天 ·{" "}
                  <button
                    disabled={busy}
                    className="chat-basis"
                    onClick={() => onRevision(String(turn.base_revision_id))}
                  >
                    查看依据行程
                  </button>
                </small>
              </div>
            </div>
            <div className="message from-assistant">
              <span className="message-avatar">
                <Sparkles size={17} />
              </span>
              <div className="message-body">
                <div className="message-bubble">
                  {turn.assistant_text ? (
                    <ChatMarkdown text={turn.assistant_text} />
                  ) : turn.status === "running" ? (
                    "本轮请求仍在处理。"
                  ) : (
                    "本轮没有生成完整回复。"
                  )}
                  {turn.result_revision_id && (
                    <button
                      className="message-result"
                      onClick={() =>
                        onRevision(String(turn.result_revision_id))
                      }
                    >
                      {turn.generate ? "查看此版行程" : "查看调整后的行程"}
                      <ArrowUpRight size={15} />
                    </button>
                  )}
                </div>
                {turn.status !== "succeeded" && (
                  <small>
                    {turn.status === "cancelled"
                      ? "已停止"
                      : turn.status === "failed"
                        ? "本轮未完成，可以继续发送消息"
                        : "处理中"}
                  </small>
                )}
              </div>
            </div>
          </div>
        ))}
        {pending && (
          <>
            <div className="message from-user">
              <span className="message-avatar">
                <UserRound size={17} />
              </span>
              <div className="message-body">
                <div className="message-bubble">{pending}</div>
              </div>
            </div>
            <div className="message from-assistant">
              <span className="message-avatar">
                <Sparkles size={17} />
              </span>
              <div className="message-body">
                <div className="message-bubble chat-live" aria-live="polite">
                  {live || phase}
                </div>
                {live && <small role="status">{phase}</small>}
              </div>
            </div>
          </>
        )}
        {error && (
          <p className="assistant-error" role="alert">
            {error}
          </p>
        )}
        {loadFailed && (
          <button
            className="chat-retry"
            disabled={busy}
            onClick={() => {
              setLoading(true);
              setError("");
              setReload((value) => value + 1);
            }}
          >
            重新读取对话
          </button>
        )}
        <div ref={bottom} />
      </div>
      <form className="composer compact-composer" onSubmit={submit}>
        <label className="sr-only" htmlFor="chat-message">
          告诉助手你的旅行想法
        </label>
        <input
          id="chat-message"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          maxLength={2000}
          disabled={busy || loading || loadFailed}
          placeholder="问问安排，或说“第 2 天下午轻松一点”"
          autoComplete="off"
        />
        {busy ? (
          <button
            type="button"
            className="send-message"
            aria-label="停止回复"
            onClick={() => controller.current?.abort()}
          >
            <Square size={15} />
          </button>
        ) : (
          <button
            className="send-message"
            aria-label="发送消息"
            disabled={!input.trim() || loading || loadFailed}
          >
            <Send size={17} />
          </button>
        )}
      </form>
      <button
        className="chat-generate"
        disabled={busy || loading || loadFailed || historical}
        onClick={() => void run(true)}
      >
        <RefreshCw size={14} />
        重新规划整趟
      </button>
      <p className="assistant-footer">
        {historical
          ? "正在查看历史版本，只能讨论；返回当前计划后才能调整。"
          : "对话自动保存；可以说“第 2 天下午轻松一点”做局部调整，重新规划整趟会创建新版本。"}
      </p>
    </>
  );
}
