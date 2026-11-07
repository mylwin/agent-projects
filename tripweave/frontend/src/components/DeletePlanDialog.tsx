import { useEffect, useRef, useState } from "react";
import { Trash2, X } from "lucide-react";
import { deleteSavedProject, ProjectsError } from "../api/projects";
import { deleteLocalProject } from "../api/workspaceStore";
import { useAuth } from "../auth/AuthProvider";

/** 删除以整个计划为单位，来源决定使用服务端或浏览器存储。 */
export type DeletePlanTarget = {
  name: string;
  revisionCount: number;
} & ({ source: "saved"; id: number } | { source: "local"; id: string });

/** 确认完整删除范围，失败时保留弹窗和计划供用户重试。 */
export default function DeletePlanDialog({
  target,
  onClose,
  onDeleted,
}: {
  target: DeletePlanTarget;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const { refreshSession } = useAuth();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const submitting = useRef(false);
  const cancelButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previous = document.activeElement;
    cancelButton.current?.focus();
    return () => {
      if (previous instanceof HTMLElement && previous.isConnected)
        previous.focus();
    };
  }, []);

  /** 删除成功后通知列表移除项目，不把服务失败当成已删除。 */
  async function remove() {
    if (submitting.current) return;
    submitting.current = true;
    setPending(true);
    setError("");
    try {
      if (target.source === "saved") await deleteSavedProject(target.id);
      else if (!deleteLocalProject(target.id))
        throw new Error("无法删除本地计划，请检查浏览器存储后重试。");
      onDeleted();
    } catch (cause) {
      if (cause instanceof ProjectsError && cause.code === "unauthorized")
        void refreshSession();
      setError(cause instanceof Error ? cause.message : "删除失败，请重试。");
    } finally {
      submitting.current = false;
      setPending(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={() => !pending && onClose()}>
      <section
        className="modal delete-plan-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="delete-plan-title"
        aria-describedby="delete-plan-description"
        aria-busy={pending}
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.stopPropagation();
            if (!pending) onClose();
          }
          if (event.key !== "Tab") return;
          const buttons = Array.from(
            event.currentTarget.querySelectorAll<HTMLButtonElement>(
              "button:not(:disabled)",
            ),
          );
          if (!buttons.length) {
            event.preventDefault();
            return;
          }
          if (event.shiftKey && document.activeElement === buttons[0]) {
            event.preventDefault();
            buttons.at(-1)?.focus();
          } else if (
            !event.shiftKey &&
            document.activeElement === buttons.at(-1)
          ) {
            event.preventDefault();
            buttons[0]?.focus();
          }
        }}
      >
        <div className="modal-heading">
          <h2 id="delete-plan-title">删除整个计划？</h2>
          <button
            className="icon-button"
            aria-label="关闭删除确认"
            disabled={pending}
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </div>
        <p id="delete-plan-description">
          将永久删除“{target.name}”及其全部 {target.revisionCount}{" "}
          个版本、行程和关联记录，无法恢复。
        </p>
        {error && (
          <p className="saved-error" role="alert">
            {error}
          </p>
        )}
        <div className="modal-actions">
          <button
            ref={cancelButton}
            className="button secondary"
            disabled={pending}
            onClick={onClose}
          >
            取消
          </button>
          <button
            className="button primary"
            disabled={pending}
            onClick={() => void remove()}
          >
            <Trash2 size={16} />
            {pending ? "正在删除…" : "删除整个计划"}
          </button>
        </div>
      </section>
    </div>
  );
}
