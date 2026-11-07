/** 流式与已保存回复共用安全节点渲染，不注入 HTML。 */
import type { ReactNode } from "react";
import {
  parseChatMarkdown,
  parseInline,
  type ChatBlock,
  type InlineToken,
} from "../utils/chatMarkdown";

/** 将闭合的行内语法输出为 React 节点。 */
function InlineText({ text }: { text: string }) {
  return <>{parseInline(text).map(renderToken)}</>;
}

/** 链接仅来自解析器允许的 http(s) 协议。 */
function renderToken(token: InlineToken, index: number): ReactNode {
  switch (token.kind) {
    case "bold":
      return <strong key={index}>{token.text}</strong>;
    case "code":
      return <code key={index}>{token.text}</code>;
    case "link":
      return (
        <a
          key={index}
          href={token.href}
          target="_blank"
          rel="noopener noreferrer"
        >
          {token.text}
        </a>
      );
    default:
      return token.text;
  }
}

/** 递归渲染列表与表格，保留显式序号、对齐方式及未闭合代码围栏。 */
function renderBlock(block: ChatBlock, index: number): ReactNode {
  if (block.kind === "ordered-list" || block.kind === "unordered-list") {
    const items = block.items.map((item, itemIndex) => (
      <li key={itemIndex} value={item.number}>
        {item.blocks.map(renderBlock)}
      </li>
    ));
    return block.kind === "ordered-list" ? (
      <ol key={index} start={block.items[0]?.number}>
        {items}
      </ol>
    ) : (
      <ul key={index}>{items}</ul>
    );
  }
  if (block.kind === "table")
    return (
      <div className="chat-table" key={index}>
        <table
          style={{ minWidth: `${Math.min(block.header.length, 6) * 8.5}em` }}
        >
          <thead>
            <tr>
              {block.header.map((cell, column) => (
                <th
                  key={column}
                  scope="col"
                  style={{ textAlign: block.align[column] ?? "left" }}
                >
                  <InlineText text={cell} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, column) => (
                  <td
                    key={column}
                    style={{ textAlign: block.align[column] ?? "left" }}
                  >
                    <InlineText text={cell} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  if (block.kind === "code")
    return (
      <pre key={index}>
        <code>{block.text}</code>
      </pre>
    );
  if (block.kind === "literal")
    return (
      <p className="chat-literal" key={index}>
        {block.text}
      </p>
    );
  if (block.kind === "heading")
    return (
      <h3 className="chat-markdown-heading" key={index}>
        <InlineText text={block.text} />
      </h3>
    );
  return (
    <p key={index}>
      <InlineText text={block.text} />
    </p>
  );
}

/** 渲染公开正文；增量快照和最终回复采用完全相同的规则。 */
export default function ChatMarkdown({ text }: { text: string }) {
  return (
    <div className="chat-markdown">
      {parseChatMarkdown(text).map(renderBlock)}
    </div>
  );
}
