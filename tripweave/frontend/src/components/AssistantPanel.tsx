import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowUpRight, Send, Sparkles, Square, UserRound } from "lucide-react";
import type { PlanProject } from "../types/trip";
import { saveRevision, updateProject } from "../api/workspaceStore";
import { examples, planLocally } from "../utils/localPlanner";

interface Props {
  project: PlanProject;
  dayId: number;
  active: boolean;
  readOnly: boolean;
  onRevision: (id: string) => void;
  onBusy: (busy: boolean) => void;
}
function delay(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const abort = () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, ms);
    signal.addEventListener("abort", abort, { once: true });
  });
}

export default function AssistantPanel({
  project,
  dayId,
  active,
  readOnly,
  onRevision,
  onBusy,
}: Props) {
  const [input, setInput] = useState("");
  const [phase, setPhase] = useState<
    "idle" | "thinking" | "planning" | "typing"
  >("idle");
  const [stream, setStream] = useState("");
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const busy = phase !== "idle";
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "nearest", behavior: "instant" });
  }, [project.messages.length, stream, phase, active]);

  async function run(text: string, resume = false) {
    if (
      busy ||
      readOnly ||
      (controller.current && !controller.current.signal.aborted)
    )
      return;
    const aborter = new AbortController();
    controller.current = aborter;
    const targetDay = resume && project.pending ? project.pending.dayId : dayId;
    const time = () =>
      new Intl.DateTimeFormat("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(new Date());
    if (!resume)
      updateProject(project.id, (p) => ({
        ...p,
        pending: { text, dayId: targetDay },
        requests: [...p.requests, { dayId: targetDay, text }],
        messages: [
          ...p.messages,
          {
            id: crypto.randomUUID(),
            role: "user",
            content: `第 ${targetDay} 天 · ${text}`,
            time: time(),
          },
        ],
      }));
    setInput("");
    setError("");
    setPhase("thinking");
    onBusy(true);
    try {
      await delay(650, aborter.signal);
      setPhase("planning");
      await delay(700, aborter.signal);
      const result = planLocally(project.trip, targetDay, text);
      setPhase("typing");
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches)
        setStream(result.reply);
      else
        for (let count = 4; count < result.reply.length + 4; count += 4) {
          setStream(result.reply.slice(0, count));
          await delay(24, aborter.signal);
        }
      if (aborter.signal.aborted) return;
      updateProject(project.id, (p) => {
        const next = result.changed
          ? saveRevision(p, result.title, result.trip)
          : p;
        const revisionId = result.changed
          ? next.revisions.at(-1)?.id
          : undefined;
        return {
          ...next,
          pending: null,
          requests: result.changed
            ? p.requests.filter(
                (r) => !(r.dayId === targetDay && r.text === text),
              )
            : p.requests,
          messages: [
            ...p.messages,
            {
              id: crypto.randomUUID(),
              role: "assistant",
              content: result.reply,
              time: time(),
              revisionId,
            },
          ],
        };
      });
    } catch (caught) {
      if (!aborter.signal.aborted)
        setError(
          caught instanceof Error
            ? `本次调整未完成：${caught.message}`
            : "本次调整未完成，请重试。",
        );
    } finally {
      if (controller.current === aborter) {
        controller.current = null;
        setPhase("idle");
        setStream("");
        onBusy(false);
      }
    }
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (text) void run(text);
  }
  return (
    <>
      <div className="assistant-heading">
        <h2>
          <Sparkles size={22} strokeWidth={1.5} />
          旅行助手
        </h2>
        <span>
          <i />
          {busy ? "正在整理行程" : "这个计划的专属对话"}
        </span>
      </div>
      <div className="conversation-project">
        <span>{project.name}</span>
        <small>
          {project.messages.length} 条对话 · {project.revisions.length} 个版本
        </small>
      </div>
      <div className="messages" aria-label="当前计划的对话历史">
        {project.messages.map((message) => (
          <div key={message.id} className={`message from-${message.role}`}>
            <span className="message-avatar">
              {message.role === "assistant" ? (
                <Sparkles size={17} strokeWidth={1.5} />
              ) : (
                <UserRound size={17} strokeWidth={1.5} />
              )}
            </span>
            <div className="message-body">
              <div className="message-bubble">
                {message.content}
                {message.revisionId && (
                  <button
                    className="message-result"
                    onClick={() => onRevision(message.revisionId!)}
                  >
                    <span>查看此版行程</span>
                    <ArrowUpRight size={15} />
                  </button>
                )}
              </div>
              <time>{message.time}</time>
            </div>
          </div>
        ))}
        {busy && (
          <div className="message from-assistant processing-message">
            <span className="message-avatar">
              <Sparkles size={17} />
            </span>
            <div className="message-body">
              {phase === "typing" ? (
                <div className="message-bubble streamed-text">
                  {stream}
                  <span className="typing-cursor" />
                </div>
              ) : (
                <div className="thinking-state" role="status">
                  <span className="thinking-dots">
                    <i />
                    <i />
                    <i />
                  </span>
                  <span>
                    {phase === "thinking"
                      ? "正在整理你的想法"
                      : "正在调整当天的安排"}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}
        {!busy && project.pending && (
          <div className="resume-request">
            <span>上次调整尚未完成，对话已保留。</span>
            <button
              onClick={() => void run(project.pending!.text, true)}
              disabled={readOnly}
            >
              继续调整
            </button>
          </div>
        )}
        {error && (
          <p className="assistant-error" role="alert">
            {error}
          </p>
        )}
        <div ref={bottom} />
      </div>
      <div className="assistant-examples" aria-label="调整示例">
        {examples.map((example) => (
          <button
            type="button"
            key={example.id}
            disabled={busy || readOnly}
            onClick={() => {
              setInput(example.prompt);
              inputRef.current?.focus();
            }}
          >
            {example.label}
          </button>
        ))}
      </div>
      <form className="composer compact-composer" onSubmit={submit}>
        <label className="sr-only" htmlFor="edit-request">
          告诉助手你的调整要求
        </label>
        <input
          ref={inputRef}
          id="edit-request"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          maxLength={500}
          disabled={busy || readOnly}
          placeholder={
            readOnly ? "返回当前计划后继续对话" : "想怎么调整这趟旅程？"
          }
          autoComplete="off"
        />
        {busy ? (
          <button
            type="button"
            className="send-message"
            aria-label="停止调整"
            onClick={() => controller.current?.abort()}
          >
            <Square size={15} />
          </button>
        ) : (
          <button
            className="send-message"
            type="submit"
            aria-label="发送调整要求"
            disabled={!input.trim() || readOnly}
          >
            <Send size={17} />
          </button>
        )}
      </form>
      <p className="assistant-footer">对话和结果，都会留在这个计划里。</p>
    </>
  );
}
