import { useSyncExternalStore } from "react";
import { getSnapshot, subscribe } from "../api/workspaceStore";

/**
 * 订阅浏览器本地工作区，提交后触发组件更新。
 *
 * @returns 当前工作区及读写错误信息。
 */
export function useWorkspace() {
  return useSyncExternalStore(subscribe, getSnapshot);
}
