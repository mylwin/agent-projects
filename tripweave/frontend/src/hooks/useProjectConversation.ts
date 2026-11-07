import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type RefObject,
  type SetStateAction,
} from "react";
import {
  getProjectMessages,
  sendProjectMessage,
  ProjectsError,
  type ConversationTurn,
} from "../api/projects";
import { useAuth } from "../auth/AuthProvider";
import {
  aggregateExecution,
  findSubmittedTurn,
  newestResult,
  HISTORY_POLL_DELAY,
  HISTORY_POLL_LIMIT,
  HISTORY_TIMEOUT,
  type ExecutionStep,
  type SubmittedMessage,
} from "../utils/chatConversation";

interface ConversationOptions {
  projectId: number;
  revisionIds: number[];
  draft: string;
  draftEdits: RefObject<number>;
  setDraft: Dispatch<SetStateAction<string>>;
  onSaved: (revisionId: number, signal?: AbortSignal) => Promise<void>;
}

/** 管理本地流、历史轮询和提交对账；暂存文本不写入浏览器存储。 */
export default function useProjectConversation(options: ConversationOptions) {
  const { projectId } = options;
  const { refreshSession } = useAuth();
  const callbacks = useRef(options);
  useEffect(() => {
    callbacks.current = options;
  }, [options]);
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const history = useRef<ConversationTurn[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetching, setFetching] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [reload, setReload] = useState(0);
  const [paused, setPaused] = useState(false);
  const [pollState, setPollState] = useState<
    "idle" | "watching" | "limit" | "error"
  >("idle");
  const [localBusy, setLocalBusy] = useState(false);
  const [pending, setPending] = useState("");
  const [pendingDayId, setPendingDayId] = useState(1);
  const [live, setLive] = useState("");
  const [phase, setPhase] = useState("");
  const [error, setError] = useState("");
  const [unsent, setUnsent] = useState("");
  const [process, setProcess] = useState<{
    turnId: number | null;
    steps: ExecutionStep[];
  }>({ turnId: null, steps: [] });
  const submission = useRef<SubmittedMessage | null>(null);
  const stream = useRef<AbortController | null>(null);
  const historyRequest = useRef<AbortController | null>(null);
  const syncRequest = useRef<AbortController | null>(null);
  const seenRevisions = useRef(new Set(options.revisionIds));
  const [syncFailed, setSyncFailed] = useState<number | null>(null);
  const [syncing, setSyncing] = useState(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      stream.current?.abort();
      historyRequest.current?.abort();
      syncRequest.current?.abort();
      submission.current = null;
    };
  }, []);
  useEffect(() => {
    options.revisionIds.forEach((id) => seenRevisions.current.add(id));
  }, [options.revisionIds]);

  /** 结果刷新单独重试，不能把“刷新失败”当成“消息未提交”重新发送。 */
  const syncResult = useCallback(async (id: number) => {
    syncRequest.current?.abort();
    const aborter = new AbortController();
    syncRequest.current = aborter;
    setSyncing(true);
    setSyncFailed(null);
    const timer = setTimeout(() => aborter.abort(), HISTORY_TIMEOUT);
    try {
      await callbacks.current.onSaved(id, aborter.signal);
    } catch {
      if (mounted.current && syncRequest.current === aborter) setSyncFailed(id);
    } finally {
      clearTimeout(timer);
      if (mounted.current && syncRequest.current === aborter) {
        syncRequest.current = null;
        setSyncing(false);
      }
    }
  }, []);

  /** 用服务端记录消除乐观消息；对账失败前不允许重发，防止同一输入重复落盘。 */
  const acceptHistory = useCallback(
    (data: ConversationTurn[]) => {
      const sent = submission.current;
      if (sent) {
        const stored = findSubmittedTurn(data, sent);
        if (stored) {
          if (
            !sent.cleared &&
            callbacks.current.draftEdits.current === sent.draftVersion
          ) {
            callbacks.current.setDraft("");
            sent.cleared = true;
          }
          setProcess((current) => ({ ...current, turnId: stored.id }));
          setUnsent("");
          if (stored.status === "succeeded") setError("");
          else if (stored.status === "cancelled") setError("本轮已停止。");
        } else if (!callbacks.current.draft) {
          callbacks.current.setDraft(sent.draft || sent.text);
        } else if (callbacks.current.draft !== sent.draft) {
          setUnsent(sent.draft || sent.text);
        }
        submission.current = null;
      }
      const completed = data.find(
        (turn) =>
          turn.status !== "running" &&
          history.current.some(
            (previous) =>
              previous.id === turn.id && previous.status === "running",
          ),
      );
      if (completed)
        setError(
          completed.status === "succeeded"
            ? ""
            : completed.status === "cancelled"
              ? "本轮已停止。"
              : "本轮未完成，可继续编辑后发送。",
        );
      history.current = data;
      setTurns(data);
      const result = newestResult(data, seenRevisions.current);
      if (result !== null) void syncResult(result);
    },
    [syncResult],
  );

  useEffect(() => {
    if (localBusy || paused) return;
    let disposed = false;
    let attempts = 0;
    let nextTimer: ReturnType<typeof setTimeout> | undefined;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    let aborter: AbortController | undefined;
    /** 串行读取，最多十二轮；每次请求设超时，失败后交还给手动刷新。 */
    async function readHistory() {
      aborter = new AbortController();
      historyRequest.current = aborter;
      attempts += 1;
      setFetching(true);
      timeout = setTimeout(() => aborter?.abort(), HISTORY_TIMEOUT);
      try {
        const data = await getProjectMessages(projectId, aborter.signal);
        if (disposed) return;
        acceptHistory(data);
        setLoadFailed(false);
        if (data.some((turn) => turn.status === "running")) {
          setPollState(attempts < HISTORY_POLL_LIMIT ? "watching" : "limit");
          if (attempts < HISTORY_POLL_LIMIT)
            nextTimer = setTimeout(
              () => void readHistory(),
              HISTORY_POLL_DELAY,
            );
        } else setPollState("idle");
      } catch (cause) {
        if (disposed) return;
        setLoadFailed(true);
        setPollState("error");
        setError(
          cause instanceof Error
            ? cause.message
            : "无法读取对话，请刷新状态后再发送。",
        );
        if (cause instanceof ProjectsError && cause.code === "unauthorized")
          void refreshSession();
      } finally {
        clearTimeout(timeout);
        if (!disposed) {
          historyRequest.current = null;
          setFetching(false);
          setLoading(false);
        }
      }
    }
    void readHistory();
    return () => {
      disposed = true;
      aborter?.abort();
      clearTimeout(nextTimer);
      clearTimeout(timeout);
      historyRequest.current = null;
    };
  }, [projectId, localBusy, reload, paused, acceptHistory, refreshSession]);

  const running = turns.some((turn) => turn.status === "running");
  const blocked =
    localBusy ||
    running ||
    loading ||
    loadFailed ||
    syncing ||
    !!unsent ||
    syncFailed !== null;

  /** 只有收到服务端事件才清空原草稿；新编辑的下一条草稿始终保留。 */
  async function run(revisionId: number, dayId: number, generate: boolean) {
    const draft = callbacks.current.draft;
    const text =
      draft.trim() || (generate ? "请基于当前需求重新生成整趟行程" : "");
    if (!text || stream.current || blocked || historyRequest.current) return;
    const aborter = new AbortController();
    stream.current = aborter;
    const sent = {
      text,
      draft,
      draftVersion: callbacks.current.draftEdits.current,
      cleared: false,
      baseRevisionId: revisionId,
      dayId,
      generate,
      knownIds: history.current.map((turn) => turn.id),
    };
    submission.current = sent;
    setLocalBusy(true);
    setError("");
    setPending(text);
    setPendingDayId(dayId);
    setLive("");
    setPhase("正在连接旅行助手");
    setProcess({ turnId: null, steps: [] });
    try {
      const turn = await sendProjectMessage(
        projectId,
        {
          text,
          base_revision_id: revisionId,
          day_id: dayId,
          generate,
        },
        (event) => {
          if (aborter.signal.aborted || !mounted.current) return;
          if (
            !sent.cleared &&
            callbacks.current.draftEdits.current === sent.draftVersion
          ) {
            callbacks.current.setDraft("");
            sent.cleared = true;
          }
          if (event.event === "reply") setLive(event.message);
          else {
            setPhase(event.message);
            setProcess((current) => ({
              ...current,
              steps: aggregateExecution(current.steps, event),
            }));
          }
        },
        aborter.signal,
      );
      if (!mounted.current || aborter.signal.aborted) return;
      const data = [
        ...history.current.filter((entry) => entry.id !== turn.id),
        turn,
      ];
      acceptHistory(data);
    } catch (cause) {
      if (!mounted.current) return;
      setError(
        aborter.signal.aborted
          ? "已停止本地回复，正在核对服务端状态。"
          : cause instanceof Error
            ? cause.message
            : "连接中断，正在核对是否已保存。",
      );
      if (cause instanceof ProjectsError && cause.code === "unauthorized")
        void refreshSession();
    } finally {
      if (stream.current === aborter) {
        stream.current = null;
        if (mounted.current) {
          // 先撤销临时正文，再由无本地流的历史读取完成对账。
          setPending("");
          setLive("");
          setPhase("");
          setPaused(false);
          setLocalBusy(false);
        }
      }
    }
  }

  /** 手动刷新重新开启一组有限轮询，不与本地流并发。 */
  function refresh() {
    if (stream.current) return;
    setPaused(false);
    setError("");
    setReload((value) => value + 1);
  }

  return {
    turns,
    loading,
    fetching,
    loadFailed,
    localBusy,
    running,
    blocked,
    pending,
    pendingDayId,
    live,
    phase,
    error,
    unsent,
    process,
    pollState,
    paused,
    syncFailed,
    syncing,
    run,
    refresh,
    stop: () => stream.current?.abort(),
    pausePolling: () => {
      setPaused(true);
      setFetching(false);
    },
    retrySync: () => {
      if (syncFailed !== null) void syncResult(syncFailed);
    },
    restoreUnsent: () => {
      callbacks.current.draftEdits.current += 1;
      callbacks.current.setDraft((current) =>
        current && current !== unsent ? `${current}\n${unsent}` : unsent,
      );
      setUnsent("");
    },
    discardUnsent: () => setUnsent(""),
  };
}
