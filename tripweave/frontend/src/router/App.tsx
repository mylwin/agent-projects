import {
  createBrowserRouter,
  RouterProvider,
  Outlet,
  Navigate,
  Link,
  useLocation,
  useParams,
} from "react-router-dom";
import { useWorkspace } from "../hooks/useWorkspace";
import { retrySave } from "../api/workspaceStore";
import { AuthProvider, useAuth } from "../auth/AuthProvider";
import { AuthLoading, RequireAuth } from "../auth/RequireAuth";
import { redirectTarget } from "../auth/redirectTarget";
import PlannerPage from "../pages/PlannerPage";
import PlansPage from "../pages/PlansPage";
import LoginPage from "../pages/LoginPage";

/**
 * 根据路由中的项目 ID 展示行程或缺失提示。
 *
 * @returns 当前项目详情或未找到页面。
 */
function PlanRoute() {
  const { id } = useParams();
  const { workspace } = useWorkspace();
  const project = workspace.projects.find((entry) => entry.id === id);
  if (!project)
    return (
      <main className="not-found">
        <h1>没有找到这个旅行计划</h1>
        <p>它可能属于其他浏览器，或链接已失效。</p>
        <Link className="button primary" to="/plans">
          返回我的旅行计划
        </Link>
      </main>
    );
  return <PlannerPage key={project.id} project={project} />;
}

/**
 * 为子路由展示存储错误及重试入口。
 *
 * @returns 存储状态提示与当前子路由。
 */
function WorkspaceRoutes() {
  const { error } = useWorkspace();
  return (
    <>
      {error && (
        <div className="storage-warning" role="alert">
          <span>{error}</span>
          <button onClick={retrySave}>重试保存</button>
        </div>
      )}
      <Outlet />
    </>
  );
}

/**
 * 已登录用户访问登录页时回到原本要去的页面。
 *
 * @returns 登录页、加载页或站内跳转。
 */
function LoginRoute() {
  const { status, user } = useAuth();
  const location = useLocation();
  if (status === "checking") return <AuthLoading />;
  if (user)
    return (
      <Navigate
        to={redirectTarget((location.state as { from?: unknown } | null)?.from)}
        replace
      />
    );
  return <LoginPage />;
}

const router = createBrowserRouter([
  { path: "/login", element: <LoginRoute /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <WorkspaceRoutes />,
        children: [
          { path: "/", element: <Navigate to="/plans" replace /> },
          { path: "/plans", element: <PlansPage /> },
          { path: "/plans/:id", element: <PlanRoute /> },
          { path: "*", element: <Navigate to="/plans" replace /> },
        ],
      },
    ],
  },
]);

/**
 * 挂载登录态与旅行项目的浏览器路由。
 *
 * @returns 应用路由入口。
 */
export default function App() {
  return (
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  );
}
