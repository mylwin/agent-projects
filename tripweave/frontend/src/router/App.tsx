import {
  createBrowserRouter,
  RouterProvider,
  Outlet,
  Navigate,
  Link,
  useParams,
} from "react-router-dom";
import { useWorkspace } from "../hooks/useWorkspace";
import { retrySave } from "../api/workspaceStore";
import PlannerPage from "../pages/PlannerPage";
import PlansPage from "../pages/PlansPage";

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

const router = createBrowserRouter([
  {
    element: <WorkspaceRoutes />,
    children: [
      { path: "/", element: <Navigate to="/plans" replace /> },
      { path: "/plans", element: <PlansPage /> },
      { path: "/plans/:id", element: <PlanRoute /> },
      { path: "*", element: <Navigate to="/plans" replace /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
