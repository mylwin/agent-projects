import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  AuthError,
  fetchSession,
  login as loginRequest,
  logout as logoutRequest,
  register as registerRequest,
  type AuthUser,
} from "../api/auth";

type AuthStatus = "checking" | "ready";

type AuthContextValue = {
  user: AuthUser | null;
  status: AuthStatus;
  serviceIssue: string | null;
  login: (username: string, password: string) => Promise<void>;
  register: (
    username: string,
    password: string,
    confirmPassword: string,
  ) => Promise<void>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * 在应用启动时确认登录态，并向页面提供登录、注册和退出操作。
 *
 * @param props - 组件属性。
 * @param props.children - 需要读取登录态的子树。
 * @returns 登录态上下文提供者。
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>("checking");
  const [serviceIssue, setServiceIssue] = useState<string | null>(null);

  const readSession = useCallback(async () => {
    try {
      return { user: await fetchSession(), issue: null };
    } catch (error) {
      return {
        user: null,
        issue:
          error instanceof AuthError
            ? error.message
            : "无法连接登录服务，请稍后重试。",
      };
    }
  }, []);

  useEffect(() => {
    let active = true;
    void readSession().then((result) => {
      if (!active) return;
      setUser(result.user);
      setServiceIssue(result.issue);
      setStatus("ready");
    });
    return () => {
      active = false;
    };
  }, [readSession]);

  const refreshSession = useCallback(async () => {
    const result = await readSession();
    setUser(result.user);
    setServiceIssue(result.issue);
    setStatus("ready");
  }, [readSession]);

  const login = useCallback(async (username: string, password: string) => {
    const session = await loginRequest(username, password);
    setUser(session);
    setServiceIssue(null);
  }, []);

  const register = useCallback(
    async (username: string, password: string, confirmPassword: string) => {
      const session = await registerRequest(
        username,
        password,
        confirmPassword,
      );
      setUser(session);
      setServiceIssue(null);
    },
    [],
  );

  const logout = useCallback(async () => {
    try {
      await logoutRequest();
    } catch {
      // 服务不可达时仍清除页面登录态，避免用户卡在无法退出的状态。
    } finally {
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({
      user,
      status,
      serviceIssue,
      login,
      register,
      logout,
      refreshSession,
    }),
    [user, status, serviceIssue, login, register, logout, refreshSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/**
 * 读取登录态与登录操作。
 *
 * @returns 当前用户、检查状态和服务可用性提示。
 * @throws Error 在 AuthProvider 之外调用时抛出。
 */
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth 必须在 AuthProvider 内使用");
  return context;
}
