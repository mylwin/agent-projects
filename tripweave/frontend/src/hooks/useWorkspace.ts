import { useSyncExternalStore } from "react";
import { getSnapshot, subscribe } from "../api/workspaceStore";

export function useWorkspace() {
  return useSyncExternalStore(subscribe, getSnapshot);
}
