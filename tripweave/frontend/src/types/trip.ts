/** 单项活动的展示数据。 */
export interface Activity {
  /** 活动唯一标识。 */
  id: string;
  /** 活动开始时间，格式 HH:MM。 */
  time: string;
  /** 活动标题。 */
  title: string;
  /** 活动说明。 */
  description: string;
  /** 地点展示文本。 */
  location: string;
  /** 活动类别，用于选择图标。 */
  kind: string;
  /** 活动费用，未知时为 null。 */
  cost: number | null;
  /** 示意图 SVG 像素坐标，未知时为 null，不是经纬度。 */
  point: number[] | null;
}

/** 单日行程与活动集合。 */
export interface TripDay {
  /** 行程序号，也用于切换日期。 */
  id: number;
  /** 当日日期，格式 YYYY-MM-DD。 */
  date: string;
  /** 第 N 天的展示标签。 */
  label: string;
  /** 单日主题。 */
  title: string;
  /** 单日说明。 */
  description: string;
  /** 路程展示文本，未核实时为“待核实”。 */
  distance: string;
  /** 当日活动列表。 */
  activities: Activity[];
}

/** 浏览器保存和展示的旅行行程。 */
export interface Trip {
  /** 持久化结构版本，当前使用 1。 */
  schemaVersion: number;
  /** 行程所属项目的标识。 */
  id: string;
  /** 旅行目的地。 */
  destination: string;
  /** 全团人数。 */
  travelers: number;
  /** 全团预算，不含往返大交通。 */
  budget: number;
  /** 货币代码，当前样例使用 CNY。 */
  currency: string;
  /** 按日期排列的每日行程。 */
  days: TripDay[];
}

/** 项目内保存的对话消息。 */
export interface Message {
  /** 消息唯一标识。 */
  id: string;
  /** 消息角色，助手或用户。 */
  role: "assistant" | "user";
  /** 消息正文。 */
  content: string;
  /** 消息时间的展示文本。 */
  time: string;
  /** 可选的关联行程版本 ID。 */
  revisionId?: string;
}

/** 可恢复查看的行程版本快照。 */
export interface PlanRevision {
  /** 版本唯一标识。 */
  id: string;
  /** 从 1 开始的版本序号。 */
  number: number;
  /** 本次调整的展示标题。 */
  title: string;
  /** 创建时间，ISO 日期时间字符串。 */
  createdAt: string;
  /** 创建版本时复制的行程快照。 */
  trip: Trip;
}

/** 浏览器本地旅行项目，包含行程、对话与版本。 */
export interface PlanProject {
  /** 项目唯一标识。 */
  id: string;
  /** 项目展示名称。 */
  name: string;
  /** 创建时间，ISO 日期时间字符串。 */
  createdAt: string;
  /** 最近修改时间，ISO 日期时间字符串。 */
  updatedAt: string;
  /** 当前行程。 */
  trip: Trip;
  /** 项目内的对话记录。 */
  messages: Message[];
  /** 尚待处理的调整清单，dayId 指定日期，text 为要求正文。 */
  requests: { dayId: number; text: string }[];
  /** 已保存的行程版本列表。 */
  revisions: PlanRevision[];
  /** 当前行程是否含有尚未保存为版本的修改。 */
  draft: boolean;
  /** 用户选定的最终版本 ID，未选定时为 null。 */
  finalRevisionId: string | null;
  /** 中断后可恢复的本地调整要求；text 为正文，dayId 为目标日期。 */
  pending: { text: string; dayId: number } | null;
}
