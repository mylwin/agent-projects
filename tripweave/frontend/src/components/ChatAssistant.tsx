import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type Dispatch,
  type FormEvent,
  type SetStateAction,
} from "react";
import {
  ArrowDown,
  PanelRightClose,
  RefreshCw,
  Send,
  Sparkles,
  Square,
  UserRound,
} from "lucide-react";
import type { RevisionSummary } from "../api/projects";
import useProjectConversation from "../hooks/useProjectConversation";
import {
  isSendKey,
  nearConversationBottom,
  type ExecutionStep,
} from "../utils/chatConversation";
import ChatMarkdown from "./ChatMarkdown";
import ChatRevisionResult from "./ChatRevisionResult";

/** 仅展示此页实际收到的事件，工具完成更新同一 call_id，不伪造进度或推理。 */
function ExecutionDetails({ steps }: { steps: ExecutionStep[] }) {
  if (!steps.length) return null;
  return (
    <details className="chat-execution">
      <summary>本轮执行过程 · {steps.length} 项</summary>
      <ol>
        {steps.map((step, index) => (
          <li
            key={step.call_id ?? `${step.event}-${index}`}
            data-event={step.event}
          >
            <span>
              {step.message}
              {step.count > 1 && `（${step.count} 次）`}
            </span>
          </li>
        ))}
      </ol>
    </details>
  );
}

/** 项目对话视图；草稿由项目页持有，版本切换和折叠不销毁输入。 */
export default function ChatAssistant({
  projectId,
  name,
  revisionId,
  revisionNumber,
  revisions,
  draft,
  setDraft,
  dayId,
  active,
  historical,
  workspaceLoading,
  onBusy,
  onStatus,
  onRevision,
  onSaved,
  onCollapse,
}: {
  projectId: number;
  name: string;
  revisionId: number;
  revisionNumber: number;
  revisions: RevisionSummary[];
  draft: string;
  setDraft: Dispatch<SetStateAction<string>>;
  dayId: number;
  active: boolean;
  historical: boolean;
  workspaceLoading: boolean;
  onBusy: (busy: boolean) => void;
  onStatus: (status: string) => void;
  onRevision: (id: string) => void;
  onSaved: (revisionId: number, signal?: AbortSignal) => Promise<void>;
  onCollapse: () => void;
}) {
  const draftEdits = useRef(0);
  const chat = useProjectConversation({
    projectId,
    revisionIds: revisions.map((revision) => revision.id),
    draft,
    draftEdits,
    setDraft,
    onSaved,
  });
  const busy =
    chat.localBusy ||
    chat.running ||
    chat.syncing ||
    chat.loading ||
    chat.loadFailed ||
    chat.syncFailed !== null;
  const blocked = chat.blocked || workspaceLoading || chat.fetching;
  const status =
    chat.loadFailed || chat.syncFailed !== null || chat.unsent
      ? "待恢复"
      : busy
        ? "处理中"
        : draft
          ? "有草稿"
          : "";
  useEffect(() => {
    onBusy(busy);
  }, [busy, onBusy]);
  useEffect(() => {
    onStatus(status);
  }, [status, onStatus]);
  const messages = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const composing = useRef(false);
  const following = useRef(true);
  const [away, setAway] = useState(false);
  const [hasNew, setHasNew] = useState(false);

  useLayoutEffect(() => {
    const field = textarea.current;
    if (!field) return;
    field.style.height = "auto";
    field.style.height = `${Math.min(field.scrollHeight, 104)}px`;
  }, [draft, active]);

  useLayoutEffect(() => {
    const pane = messages.current;
    if (!pane?.clientHeight) return;
    if (following.current) pane.scrollTop = pane.scrollHeight;
    else setHasNew(true);
  }, [chat.turns, chat.live, chat.phase, chat.pending, chat.process]);

  useEffect(() => {
    const pane = messages.current;
    const body = content.current;
    if (!pane || !body) return;
    // 展开修改清单、切换移动标签和宽度变化也可能改变高度；不能因此抢走历史位置。
    const observer = new ResizeObserver(() => {
      if (pane.clientHeight && following.current)
        pane.scrollTop = pane.scrollHeight;
    });
    observer.observe(pane);
    observer.observe(body);
    return () => observer.disconnect();
  }, []);

  /** 只滚动对话容器；用户手动返回底部时才使用可关闭的平滑动效。 */
  function jumpToBottom() {
    following.current = true;
    setAway(false);
    setHasNew(false);
    const pane = messages.current;
    pane?.scrollTo({
      top: pane.scrollHeight,
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
    });
  }
  /** 普通消息从表单提交，整趟重新规划必须通过独立按钮授权。 */
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!blocked) void chat.run(revisionId, dayId, false);
  }
  const refreshLabel = chat.fetching
    ? "正在刷新…"
    : chat.loadFailed
      ? "重试读取对话"
      : "刷新状态";
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
        <span title={name}>当前计划：{name}</span>
      </div>
      <div className="conversation-scroll-shell">
        <div
          className="messages conversation-messages"
          tabIndex={0}
          ref={messages}
          aria-label="当前计划的对话历史"
          onScroll={() => {
            const pane = messages.current!;
            following.current = nearConversationBottom(
              pane.scrollHeight,
              pane.scrollTop,
              pane.clientHeight,
            );
            setAway(!following.current);
            if (following.current) setHasNew(false);
          }}
        >
          <div ref={content} className="conversation-content">
            {chat.loading && (
              <p className="chat-meta" role="status">
                正在读取对话…
              </p>
            )}
            {!chat.loading && !chat.turns.length && !chat.pending && (
              <p className="chat-welcome">
                聊聊旅行想法，问问安排，或告诉我哪一天想调整。
              </p>
            )}
            {chat.turns.map((turn) => {
              const basis = revisions.find(
                (revision) => revision.id === turn.base_revision_id,
              );
              return (
                <div className="chat-turn" key={turn.id}>
                  <div className="message from-user">
                    <div className="chat-message-heading">
                      <UserRound size={15} />
                      <span>你 · 第 {turn.day_id} 天</span>
                      <button
                        disabled={busy || workspaceLoading}
                        className="chat-basis"
                        onClick={() =>
                          onRevision(String(turn.base_revision_id))
                        }
                      >
                        {basis ? `依据第 ${basis.number} 版` : "查看依据行程"}
                      </button>
                    </div>
                    <div className="message-body">
                      <div className="message-bubble">{turn.user_text}</div>
                    </div>
                  </div>
                  <div className="message from-assistant">
                    <div className="chat-message-heading">
                      <Sparkles size={16} />
                      <span>旅行助手</span>
                    </div>
                    <div className="message-body">
                      {turn.assistant_text ? (
                        <div className="message-bubble">
                          <ChatMarkdown text={turn.assistant_text} />
                        </div>
                      ) : (
                        <p className="chat-meta">
                          {turn.status === "running"
                            ? "服务端仍在处理本轮请求。"
                            : "本轮没有生成完整回复。"}
                        </p>
                      )}
                      {turn.status === "succeeded" &&
                        turn.result_revision_id !== null && (
                          <ChatRevisionResult
                            key={turn.result_revision_id}
                            projectId={projectId}
                            baseId={turn.base_revision_id}
                            resultId={turn.result_revision_id}
                            revisions={revisions}
                            disabled={busy || workspaceLoading}
                            onRevision={onRevision}
                          />
                        )}
                      {turn.status !== "succeeded" && (
                        <p className="chat-meta">
                          {turn.status === "cancelled"
                            ? "本轮已停止，可继续编辑下一条消息。"
                            : turn.status === "failed"
                              ? "本轮未完成，可继续编辑后发送。"
                              : "处理中，草稿仍可编辑。"}
                        </p>
                      )}
                      {chat.process.turnId === turn.id && (
                        <ExecutionDetails steps={chat.process.steps} />
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
            {chat.pending && (
              <div className="chat-turn">
                <div className="message from-user">
                  <div className="chat-message-heading">
                    <UserRound size={15} />
                    <span>你 · 第 {chat.pendingDayId} 天</span>
                  </div>
                  <div className="message-body">
                    <div className="message-bubble">{chat.pending}</div>
                  </div>
                </div>
                <div className="message from-assistant">
                  <div className="chat-message-heading">
                    <Sparkles size={16} />
                    <span>旅行助手</span>
                  </div>
                  <div className="message-body">
                    {chat.live && (
                      <div className="message-bubble chat-live">
                        <ChatMarkdown text={chat.live} />
                      </div>
                    )}
                    <p className="chat-phase" role="status">
                      {chat.phase || "正在接收回复…"}
                    </p>
                    <ExecutionDetails steps={chat.process.steps} />
                  </div>
                </div>
              </div>
            )}
            {!chat.pending && chat.process.turnId === null && (
              <ExecutionDetails steps={chat.process.steps} />
            )}
          </div>
        </div>
        {away && (
          <button type="button" className="chat-jump" onClick={jumpToBottom}>
            <ArrowDown size={15} />
            {hasNew ? "有新内容 · 回到底部" : "回到底部"}
          </button>
        )}
      </div>
      <div className="chat-status-area">
        {chat.error && (
          <p className="assistant-error" role="alert">
            {chat.error}
          </p>
        )}
        {chat.unsent && (
          <div className="chat-recovery">
            <p>还有一条未提交的输入，当前草稿未被覆盖。</p>
            <button onClick={chat.restoreUnsent}>将未提交内容放回输入框</button>
            <button onClick={chat.discardUnsent}>舍弃未提交内容</button>
          </div>
        )}
        {chat.syncFailed !== null && (
          <div className="chat-recovery" role="alert">
            <p>新版本已保存，但工作区同步失败。无需重新发送。</p>
            <button onClick={chat.retrySync}>重试同步工作区</button>
          </div>
        )}
        {chat.syncing && (
          <p className="chat-meta" role="status">
            正在同步已保存版本…
          </p>
        )}
        {chat.running && !chat.localBusy && (
          <p className="chat-meta" role="status">
            {chat.paused
              ? "已暂停自动刷新，服务端请求并未停止。"
              : chat.pollState === "limit"
                ? "自动刷新已结束，本轮仍在处理；可手动刷新状态。"
                : chat.loadFailed
                  ? "暂时无法确认处理结果，请重试读取。"
                  : "正在跟进服务端请求；完成前暂不能重复发送。"}
          </p>
        )}
        {(chat.running || chat.loadFailed || chat.error) && (
          <div className="chat-history-actions">
            <button
              disabled={chat.localBusy || chat.fetching}
              onClick={chat.refresh}
            >
              <RefreshCw size={13} />
              {refreshLabel}
            </button>
            {chat.running &&
              !chat.localBusy &&
              !chat.paused &&
              chat.pollState === "watching" && (
                <button onClick={chat.pausePolling}>暂停自动刷新</button>
              )}
          </div>
        )}
      </div>
      <form
        className="composer compact-composer chat-composer"
        onSubmit={submit}
      >
        <label className="chat-composer-context" htmlFor="chat-message">
          {workspaceLoading
            ? "正在读取行程依据…"
            : `依据第 ${revisionNumber} 版 · 第 ${dayId} 天`}
          {historical && " · 历史版本仅讨论"}
        </label>
        <div className="chat-input-row">
          <textarea
            id="chat-message"
            ref={textarea}
            rows={1}
            value={draft}
            onChange={(event) => {
              draftEdits.current += 1;
              setDraft(event.target.value);
            }}
            maxLength={2000}
            placeholder="说说你想调整的安排…"
            autoComplete="off"
            aria-label="告诉助手你的旅行想法"
            onCompositionStart={() => {
              composing.current = true;
            }}
            onCompositionEnd={() => {
              composing.current = false;
            }}
            onKeyDown={(event) => {
              if (
                isSendKey(
                  event.key,
                  event.shiftKey,
                  composing.current || event.nativeEvent.isComposing,
                  event.nativeEvent.keyCode,
                )
              ) {
                event.preventDefault();
                if (!blocked) void chat.run(revisionId, dayId, false);
              }
            }}
          />
          {chat.localBusy ? (
            <button
              type="button"
              className="send-message"
              aria-label="停止回复"
              onClick={chat.stop}
            >
              <Square size={15} />
            </button>
          ) : (
            <button
              className="send-message"
              aria-label="发送消息"
              disabled={!draft.trim() || blocked}
            >
              <Send size={17} />
            </button>
          )}
        </div>
        <span className="chat-input-hint">Enter 发送 · Shift+Enter 换行</span>
      </form>
      <div className="chat-generate-area">
        <button
          className="chat-generate"
          disabled={blocked || historical}
          onClick={() => void chat.run(revisionId, dayId, true)}
        >
          <RefreshCw size={14} />
          重新规划整趟
        </button>
        <p>
          {historical ? "返回当前计划后可重新规划" : "创建新版本，保留原方案"}
        </p>
      </div>
    </>
  );
}
