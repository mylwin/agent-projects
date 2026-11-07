/** 渲染助手回复中的轻量 Markdown；全部通过 React 节点输出，不注入 HTML。 */

import type { ReactNode } from "react";
import {
  parseChatMarkdown,
  parseInline,
  type InlineToken,
} from "../utils/chatMarkdown";

/** 把行内片段渲染成 React 节点，链接只保留 http(s)。 */
function InlineText({ text }: { text: string }) {
  return <>{parseInline(text).map(renderToken)}</>;
}

/** 按片段类型输出文本、加粗、代码或外链。 */
function renderToken(token: InlineToken, index: number): ReactNode {
  switch (token.kind) {
    case "bold":
      return <strong key={index}>{token.text}</strong>;
    case "code":
      return <code key={index}>{token.text}</code>;
    case "link":
      return (
        <a key={index} href={token.href} target="_blank" rel="noreferrer">
          {token.text}
        </a>
      );
    default:
      return token.text;
  }
}

/**
 * 把助手正文渲染为段落、标题和列表。
 *
 * @param props.text 服务端保存的公开回复。
 * @returns 带结构的消息内容；空文本不渲染任何节点。
 */
export default function ChatMarkdown({ text }: { text: string }) {
  const blocks = parseChatMarkdown(text);
  return (
    <div className="chat-markdown">
      {blocks.map((block, index) => {
        if (block.kind === "heading") {
          return (
            <h3 className="chat-markdown-heading" key={index}>
              <InlineText text={block.text} />
            </h3>
          );
        }
        if (block.kind === "ordered-list") {
          return (
            <ol key={index}>
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex}>
                  <InlineText text={item} />
                </li>
              ))}
            </ol>
          );
        }
        if (block.kind === "unordered-list") {
          return (
            <ul key={index}>
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex}>
                  <InlineText text={item} />
                </li>
              ))}
            </ul>
          );
        }
        return (
          <p key={index}>
            <InlineText text={block.text} />
          </p>
        );
      })}
    </div>
  );
}
