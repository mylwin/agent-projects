import { useRef, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  CircleAlert,
  Compass,
  Eye,
  EyeOff,
  Loader2,
  LockKeyhole,
  UserRound,
} from "lucide-react";
import { AuthError } from "../api/auth";
import { useAuth } from "../auth/AuthProvider";
import { redirectTarget } from "../auth/redirectTarget";

type Mode = "login" | "register";
type Field = "username" | "password" | "confirm";

/**
 * 展示用户名密码登录与注册表单。
 *
 * @returns 旅行手账扉页式登录页面。
 */
export default function LoginPage() {
  const { login, register, serviceIssue, refreshSession } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState("");
  const [errorField, setErrorField] = useState<Field | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const usernameRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const confirmRef = useRef<HTMLInputElement>(null);

  const registerMode = mode === "register";
  const copy = registerMode
    ? {
        eyebrow: "NEW TRAVELER",
        title: "开始一本新手账",
        lead: "取一个用户名，把下一程收进自己的手账。",
        idle: "创建账号",
        busy: "正在创建…",
      }
    : {
        eyebrow: "WELCOME BACK",
        title: "回到你的旅行手账",
        lead: "输入用户名和密码，继续上次的旅程。",
        idle: "登录",
        busy: "正在登录…",
      };
  const target = redirectTarget(
    (location.state as { from?: unknown } | null)?.from,
  );

  /**
   * 把焦点移到校验失败的字段。
   *
   * @param field - 需要聚焦的输入框。
   */
  function focusField(field: Field) {
    if (field === "username") usernameRef.current?.focus();
    else if (field === "password") passwordRef.current?.focus();
    else confirmRef.current?.focus();
  }

  /**
   * 清除上一次提交留下的错误。
   */
  function clearError() {
    if (!error) return;
    setError("");
    setErrorField(null);
  }

  /**
   * 在登录与注册之间切换，保留已输入的用户名。
   */
  function switchMode() {
    setMode((current) => (current === "login" ? "register" : "login"));
    setError("");
    setErrorField(null);
    setPassword("");
    setConfirm("");
    setVisible(false);
  }

  /**
   * 校验表单并提交登录或注册。
   *
   * @param event - 表单提交事件。
   */
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    const name = username.trim();
    let problem: { message: string; field: Field } | null = null;
    if (!name) problem = { message: "请填写用户名。", field: "username" };
    else if (registerMode) {
      if (name.length > 50)
        problem = { message: "用户名不能超过 50 个字符。", field: "username" };
      else if (password.length < 8)
        problem = { message: "密码至少需要 8 个字符。", field: "password" };
      else if (password.length > 128)
        problem = { message: "密码不能超过 128 个字符。", field: "password" };
      else if (password !== confirm)
        problem = { message: "两次输入的密码不一致。", field: "confirm" };
    } else if (!password)
      problem = { message: "请填写密码。", field: "password" };

    if (problem) {
      setError(problem.message);
      setErrorField(problem.field);
      focusField(problem.field);
      return;
    }

    setError("");
    setErrorField(null);
    setSubmitting(true);
    try {
      if (registerMode) await register(name, password);
      else await login(name, password);
      navigate(target, { replace: true });
    } catch (error) {
      setError(
        error instanceof AuthError
          ? error.message
          : "登录服务暂时不可用，请稍后重试。",
      );
      setErrorField(null);
    } finally {
      setSubmitting(false);
    }
  }

  /**
   * 重新确认登录服务与当前登录态。
   */
  async function retrySession() {
    setRetrying(true);
    try {
      await refreshSession();
    } finally {
      setRetrying(false);
    }
  }

  return (
    <div className="auth-shell">
      <section className="auth-cover" aria-label="途织旅行手账">
        <img
          className="auth-cover-image"
          src="/images/suzhou-garden.png"
          alt=""
          aria-hidden="true"
        />
        <div className="auth-cover-shade" aria-hidden="true" />
        <header className="auth-cover-top">
          <span className="auth-wordmark">
            <Compass size={27} strokeWidth={1.5} aria-hidden="true" />
            TripWeave
          </span>
          <span className="auth-cover-kicker">旅行计划手账</span>
        </header>
        <div className="auth-cover-copy">
          <p className="eyebrow">YOUR TRAVEL JOURNAL</p>
          <h1>
            把想去的地方，
            <br />
            慢慢织成旅程。
          </h1>
          <p>计划、调整结果和每一次对话，都收在属于你的旅行文件夹里。</p>
        </div>
        <footer className="auth-cover-foot">
          <span>苏州 · 园林与水巷</span>
          <span>扉页 / 01</span>
        </footer>
      </section>

      <main className="auth-panel">
        <div className="auth-form-column">
          <p className="eyebrow">{copy.eyebrow}</p>
          <h2>{copy.title}</h2>
          <p className="auth-lead">{copy.lead}</p>

          {serviceIssue && (
            <div className="auth-service" role="status">
              <CircleAlert size={16} aria-hidden="true" />
              <p>{serviceIssue}</p>
              <button type="button" disabled={retrying} onClick={retrySession}>
                {retrying ? "重试中…" : "重试连接"}
              </button>
            </div>
          )}

          <form className="auth-form" onSubmit={submit} noValidate>
            <div className="auth-field">
              <label htmlFor="login-username">用户名</label>
              <span
                className={`auth-input${errorField === "username" ? " invalid" : ""}`}
              >
                <UserRound size={17} strokeWidth={1.5} aria-hidden="true" />
                <input
                  ref={usernameRef}
                  id="login-username"
                  name="username"
                  autoComplete="username"
                  autoFocus
                  maxLength={50}
                  value={username}
                  onChange={(event) => {
                    setUsername(event.target.value);
                    clearError();
                  }}
                  placeholder="输入你的用户名"
                  aria-invalid={errorField === "username"}
                  aria-describedby={error ? "auth-error" : undefined}
                />
              </span>
            </div>

            <div className="auth-field">
              <label htmlFor="login-password">密码</label>
              <span
                className={`auth-input${errorField === "password" ? " invalid" : ""}`}
              >
                <LockKeyhole size={17} strokeWidth={1.5} aria-hidden="true" />
                <input
                  ref={passwordRef}
                  id="login-password"
                  name="password"
                  type={visible ? "text" : "password"}
                  autoComplete={registerMode ? "new-password" : "current-password"}
                  maxLength={128}
                  value={password}
                  onChange={(event) => {
                    setPassword(event.target.value);
                    clearError();
                  }}
                  placeholder={registerMode ? "至少 8 个字符" : "输入你的密码"}
                  aria-invalid={errorField === "password"}
                  aria-describedby={error ? "auth-error" : undefined}
                />
                <button
                  type="button"
                  className="auth-reveal"
                  aria-label={visible ? "隐藏密码" : "显示密码"}
                  onClick={() => setVisible((current) => !current)}
                >
                  {visible ? (
                    <EyeOff size={17} strokeWidth={1.5} />
                  ) : (
                    <Eye size={17} strokeWidth={1.5} />
                  )}
                </button>
              </span>
            </div>

            {registerMode && (
              <div className="auth-field auth-confirm">
                <label htmlFor="login-confirm">确认密码</label>
                <span
                  className={`auth-input${errorField === "confirm" ? " invalid" : ""}`}
                >
                  <LockKeyhole size={17} strokeWidth={1.5} aria-hidden="true" />
                  <input
                    ref={confirmRef}
                    id="login-confirm"
                    name="confirm"
                    type={visible ? "text" : "password"}
                    autoComplete="new-password"
                    maxLength={128}
                    value={confirm}
                    onChange={(event) => {
                      setConfirm(event.target.value);
                      clearError();
                    }}
                    placeholder="再输入一次密码"
                    aria-invalid={errorField === "confirm"}
                    aria-describedby={error ? "auth-error" : undefined}
                  />
                </span>
              </div>
            )}

            {error && (
              <p className="auth-error" id="auth-error" role="alert">
                <CircleAlert size={15} aria-hidden="true" />
                {error}
              </p>
            )}

            <button
              className="button primary auth-submit"
              type="submit"
              disabled={submitting}
              aria-busy={submitting}
            >
              <span>{submitting ? copy.busy : copy.idle}</span>
              {submitting ? (
                <Loader2 className="auth-spin" size={18} aria-hidden="true" />
              ) : (
                <ArrowRight size={18} strokeWidth={1.6} aria-hidden="true" />
              )}
            </button>
          </form>

          <p className="auth-toggle">
            {registerMode ? "已经有账号？" : "还没有账号？"}
            <button type="button" onClick={switchMode}>
              {registerMode ? "直接登录" : "创建账号"}
            </button>
          </p>
          <p className="auth-note">
            登录用于区分你的旅行文件夹；计划内容仍保存在当前浏览器。
          </p>
        </div>

        <footer className="auth-panel-foot">
          <span>TRIPWEAVE · 途织</span>
          <span>一场旅程，一页手账</span>
        </footer>
      </main>
    </div>
  );
}
