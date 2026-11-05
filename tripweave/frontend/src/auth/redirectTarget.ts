/**
 * 从路由状态读取登录后应返回的站内地址。
 *
 * @param value - 受保护页面传入的原始地址。
 * @returns 安全的站内路径，缺失或非法时回到计划列表。
 */
export function redirectTarget(value: unknown): string {
  if (
    typeof value === "string" &&
    value.startsWith("/") &&
    !value.startsWith("//") &&
    value !== "/login"
  )
    return value;
  return "/plans";
}
