import type { ConversationTurn, GenerationProgress } from "../api/projects";

export const MAX_EXECUTION_STEPS = 24;
export const HISTORY_POLL_LIMIT = 12;
export const HISTORY_POLL_DELAY = 5000;
export const HISTORY_TIMEOUT = 15000;

export interface ExecutionStep extends GenerationProgress {
  count: number;
}

export interface SubmittedMessage {
  text: string;
  draft: string;
  draftVersion: number;
  cleared: boolean;
  baseRevisionId: number;
  dayId: number;
  generate: boolean;
  knownIds: number[];
}

/** 工具仅按真实 call_id 配对；没有标识的事件按类型和原文合并，不推断调用关系。 */
export function aggregateExecution(
  steps: ExecutionStep[],
  event: GenerationProgress,
): ExecutionStep[] {
  if (event.event === "reply") return steps;
  const family = event.event.startsWith("tool_") ? "tool_" : "model_";
  const index = steps.findIndex((step) =>
    event.call_id
      ? step.call_id === event.call_id && step.event.startsWith(family)
      : !step.call_id &&
        step.event === event.event &&
        step.message === event.message,
  );
  if (index < 0)
    return [...steps, { ...event, count: 1 }].slice(-MAX_EXECUTION_STEPS);
  return steps.map((step, position) =>
    position === index
      ? { ...event, count: step.event === event.event ? step.count + 1 : 1 }
      : step,
  );
}

/** 只与发送前尚不存在、上下文和原文完全一致的新轮次对账，避免旧的同文消息误判。 */
export function findSubmittedTurn(
  turns: ConversationTurn[],
  submission: SubmittedMessage,
) {
  return turns.find(
    (turn) =>
      !submission.knownIds.includes(turn.id) &&
      turn.user_text === submission.text &&
      turn.base_revision_id === submission.baseRevisionId &&
      turn.day_id === submission.dayId &&
      turn.generate === submission.generate,
  );
}

/** 仅同步未处理过的服务端成功结果；多轮同时结束时采用最后一轮，不跳回旧版本。 */
export function newestResult(
  turns: ConversationTurn[],
  seen: Set<number>,
): number | null {
  const results = turns.filter(
    (turn) =>
      turn.status === "succeeded" &&
      turn.result_revision_id !== null &&
      !seen.has(turn.result_revision_id),
  );
  for (const turn of results) seen.add(turn.result_revision_id!);
  return results.sort((a, b) => b.id - a.id)[0]?.result_revision_id ?? null;
}

/** 自动跟随只在距底部不超过 72px 时启用。 */
export function nearConversationBottom(
  scrollHeight: number,
  scrollTop: number,
  clientHeight: number,
) {
  return scrollHeight - scrollTop - clientHeight <= 72;
}

/** 中文输入法确认键不发送，Shift+Enter 始终保留换行。 */
export function isSendKey(
  key: string,
  shiftKey: boolean,
  composing: boolean,
  keyCode: number,
) {
  return key === "Enter" && !shiftKey && !composing && keyCode !== 229;
}
