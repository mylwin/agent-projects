import { Compass } from "lucide-react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./AuthProvider";

/**
 * 登录态确认期间展示的纸白加载页。
 *
 * @returns 品牌标记与等待提示。
 */
export function AuthLoading() {
  return (
    <div className="auth-loading" role="status" aria-live="polite">
      <div className="auth-loading-inner">
        <Compass size={36} strokeWidth={1.4} aria-hidden="true" />
        <span>正在打开旅行手账…</span>
      </div>
    </div>
  );
}

/**
 * 未登录时拦截受保护页面，并记住原本要去的地址。
 *
 * @returns 登录态确认页、登录跳转或受保护子路由。
 */
export function RequireAuth() {
  const { status, user } = useAuth();
  const location = useLocation();
  if (status === "checking") return <AuthLoading />;
  if (!user)
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: `${location.pathname}${location.search}` }}
      />
    );
  return <Outlet />;
}
