import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ReactNode } from "react";

export function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="markdown-content">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h2: ({ children, node: _node, ...props }) => (
            <h2 {...props} id={headingSlug(children)}>{children}</h2>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export function headingSlug(children: ReactNode): string {
  const text = flattenText(children)
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s-]/gu, "")
    .trim()
    .replace(/\s+/g, "-");
  return text || "lesson-section";
}

function flattenText(children: ReactNode): string {
  if (typeof children === "string" || typeof children === "number") {
    return String(children);
  }
  if (Array.isArray(children)) return children.map(flattenText).join("");
  return "";
}
