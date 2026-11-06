/**
 * 登录接口客户端。登录态由服务端签名 Cookie 维持，前端只缓存当前用户。
 *
 * 接口约定见 docs/07-api-reference.md：
 * - GET  /api/auth/me       已登录返回 {success:true,data:{id,username}}，未登录返回 401。
 * - POST /api/auth/login    提交 {username,password}，成功后建立登录态。
 * - POST /api/auth/register 提交 {username,password,confirm_password}，成功即建立登录态。
 * - POST /api/auth/logout   清除登录态，返回 {success:true,data:null}。
 */

export type AuthUser = { id: number; username: string };

type ApiSuccess<T> = { success: true; data: T };

const networkMessage = "无法连接登录服务，请确认后端已启动后重试。";
const serviceMessage = "登录服务暂时不可用，请稍后重试。";
const invalidMessage = "登录服务返回了无法识别的结果，请稍后重试。";

/**
 * 携带稳定错误码的登录失败，页面据此区分账号错误与服务故障。
 */
export class AuthError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "AuthError";
    this.code = code;
  }
}

/**
 * 判断值是否为非空对象。
 *
 * @param value - 待检查的外部数据。
 * @returns 是否可按键读取对象字段。
 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object";
}

/**
 * 发送请求并统一处理网络不可达。
 *
 * @param path - 以 /api 开头的接口路径。
 * @param init - 额外的 fetch 配置。
 * @returns 原始响应，由调用方决定如何读取。
 * @throws AuthError 网络请求未到达服务端时抛出。
 */
async function send(path: string, init: RequestInit = {}): Promise<Response> {
  try {
    return await fetch(path, {
      credentials: "include",
      ...init,
      headers: {
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...init.headers,
      },
    });
  } catch {
    throw new AuthError("network_error", networkMessage);
  }
}

/**
 * 按统一成功/失败结构读取响应。
 *
 * @param response - 接口原始响应。
 * @returns 成功响应中的 data。
 * @throws AuthError 响应不是约定结构或接口返回失败时抛出。
 */
async function read<T>(response: Response): Promise<T> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new AuthError(
      `http_${response.status}`,
      response.ok ? invalidMessage : serviceMessage,
    );
  }
  if (!response.ok || !isRecord(body) || body.success !== true) {
    const error = isRecord(body) && isRecord(body.error) ? body.error : null;
    const code =
      typeof error?.code === "string" ? error.code : `http_${response.status}`;
    const message =
      typeof error?.message === "string" ? error.message : serviceMessage;
    throw new AuthError(code, message);
  }
  return (body as ApiSuccess<T>).data;
}

/**
 * 读取当前登录用户。
 *
 * @returns 已登录用户；未登录时为 null。
 * @throws AuthError 无法确认登录态时抛出。
 */
export async function fetchSession(): Promise<AuthUser | null> {
  const response = await send("/api/auth/me", { cache: "no-store" });
  if (response.status === 401) return null;
  return read<AuthUser>(response);
}

/**
 * 使用用户名和密码登录。
 *
 * @param username - 已去除首尾空白的用户名。
 * @param password - 原始密码，不做裁剪。
 * @returns 登录成功的用户。
 * @throws AuthError 凭据不正确或服务不可用时抛出。
 */
export async function login(
  username: string,
  password: string,
): Promise<AuthUser> {
  const response = await send("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  return read<AuthUser>(response);
}

/**
 * 注册新用户并直接进入登录态。
 *
 * @param username - 已去除首尾空白的用户名。
 * @param password - 原始密码，不做裁剪。
 * @param confirmPassword - 再次输入的密码，不做裁剪。
 * @returns 注册后登录的用户。
 * @throws AuthError 用户名已被占用或服务不可用时抛出。
 */
export async function register(
  username: string,
  password: string,
  confirmPassword: string,
): Promise<AuthUser> {
  const response = await send("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({
      username,
      password,
      confirm_password: confirmPassword,
    }),
  });
  return read<AuthUser>(response);
}

/**
 * 清除服务端登录态。
 *
 * @throws AuthError 服务不可达或返回失败时抛出。
 */
export async function logout(): Promise<void> {
  const response = await send("/api/auth/logout", { method: "POST" });
  if (response.status === 401 || response.status === 204) return;
  await read<unknown>(response);
}
