import type {
  AuthSession,
  ChatHistory,
  ChatThread,
  InsuranceCategory,
  PlanInterrupt,
  Product,
  UserSummary,
} from './types';

export const API_BASE = '/api/v1';

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/** 访问令牌与刷新令牌都已失效，需要重新登录。 */
export class SessionExpiredError extends Error {
  constructor() {
    super('登录状态已失效，请重新登录');
    this.name = 'SessionExpiredError';
  }
}

interface AuthResponse {
  access_token: string;
  token_type: string;
  user: UserSummary;
}

interface ApiErrorPayload {
  message?: string;
  detail?: unknown;
  errors?: Array<{ field?: string; message?: string }>;
}

// 访问令牌只保存在内存中，刷新页面后由 /auth/refresh 的 HttpOnly Cookie 恢复。
let accessToken: string | null = null;
// 多个请求同时 401 时只发起一次刷新，避免轮换后的 Cookie 被并发刷新覆盖。
let refreshing: Promise<AuthResponse> | null = null;

function setAccessToken(token: string | null): void {
  accessToken = token;
}

async function sendRequest(
  path: string,
  init: RequestInit | undefined,
  token: string | null,
): Promise<Response> {
  return fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
}

async function toApiError(
  response: Response,
  fallback = '请求失败，请稍后重试',
): Promise<ApiError> {
  const payload = (await response.json().catch(() => null)) as ApiErrorPayload | null;
  const validationMessage = response.status === 422 ? payload?.errors?.[0]?.message : undefined;
  const detail = typeof payload?.detail === 'string' ? payload.detail : undefined;
  return new ApiError(
    validationMessage ?? payload?.message ?? detail ?? fallback,
    response.status,
  );
}

/** 带令牌请求；遇到 401 时刷新令牌并重试一次，仍失败则判定会话过期。 */
async function sendAuthorized(path: string, init?: RequestInit): Promise<Response> {
  let response = await sendRequest(path, init, accessToken);
  if (response.status !== 401) return response;
  try {
    await refreshSession();
  } catch {
    throw new SessionExpiredError();
  }
  response = await sendRequest(path, init, accessToken);
  if (response.status === 401) {
    setAccessToken(null);
    throw new SessionExpiredError();
  }
  return response;
}

async function performRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await sendAuthorized(path, init);
  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

// 开发模式下 React StrictMode 会重放 effect；同一 URL 的并发 GET 复用同一个 Promise，
// 避免同一份数据被发送两次（否则先发的请求会被后发请求取消）。
const pendingGets = new Map<string, Promise<unknown>>();

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (init?.method && init.method !== 'GET') {
    return performRequest<T>(path, init);
  }
  const pending = pendingGets.get(path);
  if (pending) return pending as Promise<T>;
  const promise = performRequest<T>(path, init).finally(() => {
    pendingGets.delete(path);
  });
  pendingGets.set(path, promise);
  return promise;
}

async function submitAuth(
  path: string,
  body: Record<string, string>,
): Promise<AuthSession> {
  const response = await sendRequest(path, { method: 'POST', body: JSON.stringify(body) }, null);
  if (!response.ok) throw await toApiError(response);
  const data = (await response.json()) as AuthResponse;
  setAccessToken(data.access_token);
  return { user: data.user };
}

export function login(username: string, password: string): Promise<AuthSession> {
  return submitAuth('/auth/login', { username, password });
}

export function register(
  username: string,
  email: string,
  password: string,
): Promise<AuthSession> {
  return submitAuth('/auth/register', { username, email, password });
}

async function performRefresh(): Promise<AuthResponse> {
  try {
    const response = await sendRequest('/auth/refresh', { method: 'POST' }, null);
    if (!response.ok) throw await toApiError(response);
    const data = (await response.json()) as AuthResponse;
    setAccessToken(data.access_token);
    return data;
  } catch (reason) {
    accessToken = null;
    throw reason;
  }
}

export function refreshSession(): Promise<AuthResponse> {
  if (!refreshing) {
    refreshing = performRefresh().finally(() => {
      refreshing = null;
    });
  }
  return refreshing;
}

export async function logout(): Promise<void> {
  setAccessToken(null);
  // 注销以清理本地登录态为准，后端清 Cookie 失败不应阻塞用户退出。
  await sendRequest('/auth/logout', { method: 'POST' }, null).catch(() => undefined);
}

export function listProducts(category: InsuranceCategory | 'all'): Promise<Product[]> {
  const params = new URLSearchParams();
  if (category !== 'all') {
    params.set('category', category);
  }
  const query = params.toString();
  return request<Product[]>(`/products${query ? `?${query}` : ''}`);
}

export function markPlanItemInsured(planId: string, itemId: string): Promise<unknown> {
  return request<unknown>(
    `/insurance-plans/${encodeURIComponent(planId)}/items/${encodeURIComponent(itemId)}/insured`,
    { method: 'PATCH' },
  );
}

export function getInsurancePlan(planId: string): Promise<unknown> {
  return request<unknown>(`/insurance-plans/${encodeURIComponent(planId)}`);
}

export function listChatThreads(): Promise<ChatThread[]> {
  return request<ChatThread[]>('/chat-threads');
}

export function createChatThread(title = '保险咨询'): Promise<ChatThread> {
  return request<ChatThread>('/chat-threads', {
    method: 'POST',
    body: JSON.stringify({ title }),
  });
}

export function getChatHistory(threadId: string): Promise<ChatHistory> {
  return request<ChatHistory>(`/chat-threads/${threadId}/messages`);
}

export function renameChatThread(threadId: string, title: string): Promise<ChatThread> {
  return request<ChatThread>(`/chat-threads/${threadId}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  });
}

export async function deleteChatThread(threadId: string): Promise<void> {
  await request<void>(`/chat-threads/${threadId}`, {
    method: 'DELETE',
  });
}

export async function streamChat(
  threadId: string,
  input: { message?: string; decision?: Record<string, unknown> },
  handlers: {
    onMessage: (chunk: string) => void;
    onAdditionalInfo?: (info: unknown) => void;
    onInterrupt?: (interrupt: PlanInterrupt) => void;
  },
): Promise<void> {
  const response = await sendAuthorized('/chat', {
    method: 'POST',
    body: JSON.stringify({ thread_id: threadId, ...input }),
  });
  if (!response.ok || !response.body) {
    throw await toApiError(response, '消息发送失败，请稍后重试');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split(/\r?\n\r?\n/);
    buffer = parts.pop() ?? '';
    parts.forEach((eventText) => handleSseEvent(eventText, handlers));
  }
  if (buffer.trim()) {
    handleSseEvent(buffer, handlers);
  }
}

function handleSseEvent(
  eventText: string,
  handlers: {
    onMessage: (chunk: string) => void;
    onAdditionalInfo?: (info: unknown) => void;
    onInterrupt?: (interrupt: PlanInterrupt) => void;
  },
) {
  const lines = eventText.split(/\r?\n/);
  const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim();
  const data = lines
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n');
  if (!data) return;
  if (event === 'message') {
    handlers.onMessage(parseSseMessage(data));
    return;
  }
  if (event === 'interrupt') {
    const interrupt = parseInterrupt(data);
    if (interrupt) handlers.onInterrupt?.(interrupt);
    return;
  }
  if (event === 'additional_info') {
    handlers.onAdditionalInfo?.(parseJsonLike(data) ?? data);
  }
}

function parseSseMessage(data: string): string {
  try {
    const value = JSON.parse(data) as unknown;
    return typeof value === 'string' ? value : JSON.stringify(value);
  } catch {
    return data;
  }
}

function parseInterrupt(data: string): PlanInterrupt | null {
  const parsed = parseJsonLike(data);
  const value = Array.isArray(parsed) ? parsed[0] : parsed;
  if (!value || typeof value !== 'object') return null;
  const candidate = value as Partial<PlanInterrupt>;
  if (!('plan' in candidate) || typeof candidate.confirm_info !== 'string') return null;
  return {
    plan: candidate.plan,
    confirm_info: candidate.confirm_info,
    action: Array.isArray(candidate.action)
      ? candidate.action.filter((item): item is 'approve' | 'reject' =>
          item === 'approve' || item === 'reject',
        )
      : ['approve', 'reject'],
  };
}

function parseJsonLike(data: string): unknown {
  try {
    return JSON.parse(data);
  } catch {
    return null;
  }
}
