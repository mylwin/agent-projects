/** 解析轻量 Markdown 为数据树；不生成 HTML，也不补全流中尚未闭合的语法。 */
export type InlineToken =
  | { kind: "text"; text: string }
  | { kind: "bold"; text: string }
  | { kind: "code"; text: string }
  | { kind: "link"; text: string; href: string };

export type TableAlign = "left" | "center" | "right" | null;

export type ChatBlock =
  | { kind: "paragraph" | "heading" | "literal" | "code"; text: string }
  | { kind: "unordered-list"; items: ChatListItem[] }
  | { kind: "ordered-list"; items: ChatListItem[] }
  | { kind: "table"; header: string[]; align: TableAlign[]; rows: string[][] };

export interface ChatListItem {
  number?: number;
  blocks: ChatBlock[];
}

const INLINE_PATTERN =
  /(\*\*[^*\n]+\*\*|`[^`\n]+`|\[[^\]\n]+\]\(https?:\/\/[^\s)<>]+\))/gi;
const HEADING_PATTERN = /^\s{0,3}#{1,6}\s+(\S.*)$/;
const LIST_PATTERN = /^( *)(?:([-*+])|(\d{1,9})[.)]) +(\S.*)$/;
const FENCE_PATTERN = /^\s{0,3}(`{3,}|~{3,})/;
const ALIGN_PATTERN = /^:?-+:?$/;

/** 只解析闭合的行内语法；不支持的链接协议与原始 HTML 始终作为文字。 */
export function parseInline(text: string): InlineToken[] {
  const tokens: InlineToken[] = [];
  let lastIndex = 0;
  for (const match of text.matchAll(INLINE_PATTERN)) {
    const index = match.index;
    if (index > lastIndex)
      tokens.push({ kind: "text", text: text.slice(lastIndex, index) });
    const raw = match[0];
    if (raw.startsWith("**")) {
      tokens.push({ kind: "bold", text: raw.slice(2, -2) });
    } else if (raw.startsWith("`")) {
      tokens.push({ kind: "code", text: raw.slice(1, -1) });
    } else {
      const link = /^\[([^\]]+)\]\((https?:\/\/[^\s)<>]+)\)$/i.exec(raw)!;
      try {
        const url = new URL(link[2]);
        tokens.push(
          url.hostname && ["https:", "http:"].includes(url.protocol)
            ? { kind: "link", text: link[1], href: link[2] }
            : { kind: "text", text: raw },
        );
      } catch {
        tokens.push({ kind: "text", text: raw });
      }
    }
    lastIndex = index + raw.length;
  }
  if (lastIndex < text.length)
    tokens.push({ kind: "text", text: text.slice(lastIndex) });
  return tokens;
}

/** 拆分表格行；转义竖线属于单元格内容，首尾竖线可省略。 */
function splitCells(line: string): string[] {
  const text = line.trim();
  const start = text.startsWith("|") ? 1 : 0;
  const end =
    text.endsWith("|") && !text.endsWith("\\|") ? text.length - 1 : text.length;
  const cells: string[] = [];
  let cell = "";
  for (let index = start; index < end; index += 1) {
    if (text[index] === "\\" && text[index + 1] === "|") {
      cell += "|";
      index += 1;
    } else if (text[index] === "|") {
      cells.push(cell.trim());
      cell = "";
    } else {
      cell += text[index];
    }
  }
  cells.push(cell.trim());
  return cells;
}

/** 分隔行单元格数与表头一致才认作表格；流中未写完的分隔行仍按原文保留。 */
function matchTable(
  lines: string[],
  index: number,
): { block: ChatBlock; end: number } | null {
  const headerLine = lines[index];
  if (!headerLine?.includes("|") || LIST_PATTERN.test(headerLine)) return null;
  const delimiter = lines[index + 1];
  if (!delimiter?.includes("-")) return null;
  const align: TableAlign[] = [];
  for (const cell of splitCells(delimiter)) {
    if (!ALIGN_PATTERN.test(cell)) return null;
    align.push(
      cell.startsWith(":")
        ? cell.endsWith(":")
          ? "center"
          : "left"
        : cell.endsWith(":")
          ? "right"
          : null,
    );
  }
  const header = splitCells(headerLine);
  if (header.length !== align.length) return null;
  const rows: string[][] = [];
  let end = index + 2;
  while (end < lines.length) {
    const line = lines[end];
    if (
      !line.trim() ||
      !line.includes("|") ||
      HEADING_PATTERN.test(line) ||
      FENCE_PATTERN.test(line)
    )
      break;
    const cells = splitCells(line);
    rows.push(header.map((_, column) => cells[column] ?? ""));
    end += 1;
  }
  return { block: { kind: "table", header, align, rows }, end };
}

/** 按缩进解析子列表；空行不重置同级有序编号，非缩进正文不吞进列表。 */
function parseBlocks(lines: string[], depth: number): ChatBlock[] {
  if (depth > 12) return [{ kind: "literal", text: lines.join("\n") }];
  const blocks: ChatBlock[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }
    const fence = /^\s{0,3}(`{3,}|~{3,})[^`]*$/.exec(line);
    if (fence) {
      const start = index++;
      const closing = new RegExp(
        `^\\s{0,3}${fence[1][0]}{${fence[1].length},}\\s*$`,
      );
      while (index < lines.length && !closing.test(lines[index])) index += 1;
      const closed = index < lines.length;
      blocks.push({
        kind: closed ? "code" : "literal",
        text: lines.slice(closed ? start + 1 : start, index).join("\n"),
      });
      if (closed) index += 1;
      continue;
    }
    const heading = HEADING_PATTERN.exec(line);
    if (heading) {
      blocks.push({ kind: "heading", text: heading[1] });
      index += 1;
      continue;
    }
    const first = LIST_PATTERN.exec(line);
    if (first) {
      const indent = first[1].length;
      const ordered = !!first[3];
      const items: ChatListItem[] = [];
      while (index < lines.length) {
        const match = LIST_PATTERN.exec(lines[index]);
        if (!match || match[1].length !== indent || !!match[3] !== ordered)
          break;
        const contentIndent = lines[index].length - match[4].length;
        const content = [match[4]];
        index += 1;
        while (index < lines.length) {
          if (!lines[index].trim()) {
            let next = index + 1;
            while (next < lines.length && !lines[next].trim()) next += 1;
            const nextItem = LIST_PATTERN.exec(lines[next] ?? "");
            if (nextItem && nextItem[1].length === indent) {
              index = next;
              break;
            }
            if (
              next === lines.length ||
              (lines[next].match(/^ */)?.[0].length ?? 0) < contentIndent
            )
              break;
            content.push("");
            index += 1;
            continue;
          }
          const nextIndent = lines[index].match(/^ */)![0].length;
          if (nextIndent < contentIndent) break;
          content.push(lines[index].slice(contentIndent));
          index += 1;
        }
        items.push({
          ...(ordered ? { number: Number(match[3]) } : {}),
          blocks: parseBlocks(content, depth + 1),
        });
      }
      blocks.push({ kind: ordered ? "ordered-list" : "unordered-list", items });
      continue;
    }
    const table = matchTable(lines, index);
    if (table) {
      blocks.push(table.block);
      index = table.end;
      continue;
    }
    const paragraph = [line];
    index += 1;
    while (
      index < lines.length &&
      lines[index].trim() &&
      !LIST_PATTERN.test(lines[index]) &&
      !HEADING_PATTERN.test(lines[index]) &&
      !FENCE_PATTERN.test(lines[index]) &&
      !matchTable(lines, index)
    )
      paragraph.push(lines[index++]);
    blocks.push({ kind: "paragraph", text: paragraph.join("\n") });
  }
  return blocks;
}

/** 解析公开回复；制表符统一为四空格，限制嵌套深度以约束资源使用。 */
export function parseChatMarkdown(text: string): ChatBlock[] {
  return parseBlocks(
    text.replace(/\r\n?/g, "\n").replace(/\t/g, "    ").split("\n"),
    0,
  );
}
