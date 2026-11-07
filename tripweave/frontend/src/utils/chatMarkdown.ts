/** 把助手回复中的轻量 Markdown 解析成可直接渲染的数据，不生成 HTML。 */

export type InlineToken =
  | { kind: "text"; text: string }
  | { kind: "bold"; text: string }
  | { kind: "code"; text: string }
  | { kind: "link"; text: string; href: string };

export type ChatBlock =
  | { kind: "paragraph"; text: string }
  | { kind: "heading"; text: string }
  | { kind: "unordered-list"; items: string[] }
  | { kind: "ordered-list"; items: string[] };

/** 只匹配模型常用的行内语法；未闭合标记按普通文本保留。 */
const INLINE_PATTERN =
  /(\*\*[^*\n]+\*\*|`[^`\n]+`|\[[^\]\n]+\]\(https?:\/\/[^\s)]+\))/g;
const HEADING_PATTERN = /^\s{0,3}(#{1,6})\s+(.*)$/;
const UNORDERED_PATTERN = /^\s*[-*+]\s+(.*)$/;
const ORDERED_PATTERN = /^\s*\d+[.)]\s+(.*)$/;

/**
 * 解析一行中的加粗、行内代码和 http(s) 链接。
 *
 * @param text 单行或单段文本。
 * @returns 按出现顺序排列的行内片段；普通文本默认合并为 text 片段。
 */
export function parseInline(text: string): InlineToken[] {
  const tokens: InlineToken[] = [];
  let lastIndex = 0;
  for (const match of text.matchAll(INLINE_PATTERN)) {
    const index = match.index ?? 0;
    if (index > lastIndex) {
      tokens.push({ kind: "text", text: text.slice(lastIndex, index) });
    }
    const raw = match[1];
    if (raw.startsWith("**")) {
      tokens.push({ kind: "bold", text: raw.slice(2, -2) });
    } else if (raw.startsWith("`")) {
      tokens.push({ kind: "code", text: raw.slice(1, -1) });
    } else {
      const link = /^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/.exec(raw);
      tokens.push(
        link
          ? { kind: "link", text: link[1], href: link[2] }
          : { kind: "text", text: raw },
      );
    }
    lastIndex = index + raw.length;
  }
  if (lastIndex < text.length) {
    tokens.push({ kind: "text", text: text.slice(lastIndex) });
  }
  return tokens;
}

/**
 * 把助手回复拆成段落、标题和列表块。
 *
 * 空白行分隔块；列表项支持 -、*、+ 和数字序号，列表中的换行会拼回同一项。
 *
 * @param text 助手返回的公开正文。
 * @returns 保留原始顺序的块列表；空文本返回空数组。
 */
export function parseChatMarkdown(text: string): ChatBlock[] {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const blocks: ChatBlock[] = [];
  let paragraph: string[] = [];
  let list: { kind: "unordered-list" | "ordered-list"; items: string[] } | null =
    null;

  /** 把累积的普通行落成段落。 */
  function flushParagraph() {
    if (!paragraph.length) return;
    blocks.push({ kind: "paragraph", text: paragraph.join("\n") });
    paragraph = [];
  }

  /** 把累积的列表落成块。 */
  function flushList() {
    if (!list) return;
    blocks.push(list);
    list = null;
  }

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }
    const heading = HEADING_PATTERN.exec(line);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({ kind: "heading", text: heading[2].trim() });
      continue;
    }
    const unordered = UNORDERED_PATTERN.exec(line);
    if (unordered) {
      flushParagraph();
      if (list?.kind !== "unordered-list") {
        flushList();
        list = { kind: "unordered-list", items: [] };
      }
      list.items.push(unordered[1].trim());
      continue;
    }
    const ordered = ORDERED_PATTERN.exec(line);
    if (ordered) {
      flushParagraph();
      if (list?.kind !== "ordered-list") {
        flushList();
        list = { kind: "ordered-list", items: [] };
      }
      list.items.push(ordered[1].trim());
      continue;
    }
    if (list) {
      list.items[list.items.length - 1] += ` ${line.trim()}`;
      continue;
    }
    paragraph.push(line);
  }
  flushParagraph();
  flushList();
  return blocks;
}
