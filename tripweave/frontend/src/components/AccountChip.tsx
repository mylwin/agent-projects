import { LogOut, UserRound } from "lucide-react";
import { useAuth } from "../auth/AuthProvider";

/**
 * 展示当前登录用户，并提供退出入口。
 *
 * @returns 顶栏账号胶囊；未登录时不渲染。
 */
export default function AccountChip() {
  const { user, logout } = useAuth();
  if (!user) return null;
  return (
    <div className="account-chip">
      <UserRound size={15} strokeWidth={1.5} aria-hidden="true" />
      <span className="account-name">{user.username}</span>
      <span className="account-divider" aria-hidden="true" />
      <button
        className="account-logout"
        onClick={() => void logout()}
        aria-label="退出登录"
        title="退出登录"
      >
        <LogOut size={15} strokeWidth={1.5} aria-hidden="true" />
      </button>
    </div>
  );
}
