import { useEffect, useMemo, useState } from "react";
import { ArrowUpRight } from "lucide-react";
import {
  getSavedRevision,
  type RevisionDetail,
  type RevisionSummary,
} from "../api/projects";
import { compareRevisionTrips } from "../utils/revisionChanges";
import { HISTORY_TIMEOUT } from "../utils/chatConversation";

/** 仅由服务端成功轮次挂载；版本号及修改清单均来自保存后的读回数据。 */
export default function ChatRevisionResult({
  projectId,
  baseId,
  resultId,
  revisions,
  disabled,
  onRevision,
}: {
  projectId: number;
  baseId: number;
  resultId: number;
  revisions: RevisionSummary[];
  disabled: boolean;
  onRevision: (id: string) => void;
}) {
  const summary = revisions.find((revision) => revision.id === resultId);
  const [result, setResult] = useState<RevisionDetail | null>(null);
  const [base, setBase] = useState<RevisionDetail | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const needsResult = !result && (expanded || !summary);
  const needsBase = expanded && !base;
  const loading = (needsResult || needsBase) && !error;
  useEffect(() => {
    if (!needsResult && !needsBase) return;
    const aborter = new AbortController();
    let disposed = false;
    const timer = setTimeout(() => aborter.abort(), HISTORY_TIMEOUT);
    void Promise.all([
      needsResult
        ? getSavedRevision(projectId, resultId, aborter.signal)
        : null,
      needsBase ? getSavedRevision(projectId, baseId, aborter.signal) : null,
    ])
      .then(([savedResult, savedBase]) => {
        if (disposed) return;
        if (savedResult) setResult(savedResult);
        if (savedBase) setBase(savedBase);
      })
      .catch((cause: unknown) => {
        if (!disposed)
          setError(
            cause instanceof Error ? cause.message : "无法读取已保存版本",
          );
      })
      .finally(() => {
        clearTimeout(timer);
      });
    return () => {
      disposed = true;
      aborter.abort();
      clearTimeout(timer);
    };
  }, [projectId, baseId, resultId, needsResult, needsBase, retry]);
  const changes = useMemo(
    () =>
      base && result
        ? compareRevisionTrips(base.result.trip, result.result.trip)
        : null,
    [base, result],
  );
  const number = result?.number ?? summary?.number;
  return (
    <section className="chat-revision-result" aria-label="服务端保存的行程结果">
      <button
        className="message-result"
        disabled={disabled}
        onClick={() => onRevision(String(resultId))}
      >
        <span>
          <strong>
            {number === undefined
              ? "行程已保存 · 版本号待读取"
              : `第 ${number} 版已保存`}
          </strong>
          <span>查看此版行程</span>
        </span>
        <ArrowUpRight size={17} />
      </button>
      <details onToggle={(event) => setExpanded(event.currentTarget.open)}>
        <summary>查看实际修改</summary>
        {changes && (
          <>
            <p className="chat-meta">
              比较第 {base!.number} 版与第 {result!.number} 版的保存内容
            </p>
            {changes.length ? (
              <ul className="chat-change-list">
                {changes.map((change, index) => (
                  <li key={index}>
                    <strong>{change.label}</strong>
                    <span>原：{change.before}</span>
                    <span>现：{change.after}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p>行程字段没有变化。</p>
            )}
          </>
        )}
      </details>
      {loading && (
        <p className="chat-meta" role="status">
          正在读取保存内容…
        </p>
      )}
      {error && (
        <div className="chat-result-error" role="alert">
          <p>{error}</p>
          <button
            className="chat-retry"
            onClick={() => {
              setError("");
              setRetry((value) => value + 1);
            }}
          >
            重试读取版本
          </button>
        </div>
      )}
    </section>
  );
}
