// The small part of Markdown GIMPhoto's docs use in the text the site shows:
// paragraphs, bullet and numbered lists (nested by indentation), `code`,
// **bold**, *italics* and [links]. Built as React elements: no HTML is
// injected. Links relative to docs/features point at GitHub.
import type { ReactNode } from "react";
import { REPO_URL } from "@/lib/site";

const INLINE = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*\s][^*]*\*|\[[^\]]+\]\([^)\s]+\))/g;

function href(target: string): string {
  if (/^https?:\/\//.test(target) || target.startsWith("#")) return target;
  // relative to docs/features/<page>.md
  const clean = target.replace(/^\.\//, "");
  if (clean.startsWith("../../")) return `${REPO_URL}/blob/main/${clean.slice(6)}`;
  if (clean.startsWith("../")) return `${REPO_URL}/blob/main/docs/${clean.slice(3)}`;
  return `${REPO_URL}/blob/main/docs/features/${clean}`;
}

export function inline(text: string, key = "i"): ReactNode[] {
  return text.split(INLINE).filter(Boolean).map((part, i) => {
    const k = `${key}-${i}`;
    if (part.startsWith("`")) return <code key={k}>{part.slice(1, -1)}</code>;
    if (part.startsWith("**")) return <strong key={k}>{inline(part.slice(2, -2), k)}</strong>;
    if (part.startsWith("*") && part.length > 2) return <em key={k}>{inline(part.slice(1, -1), k)}</em>;
    const link = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(part);
    if (link) return <a key={k} href={href(link[2])}>{inline(link[1], k)}</a>;
    return part;
  });
}

type Item = { text: string; children: Item[] };
type Block = { kind: "p"; text: string } | { kind: "ul" | "ol"; items: Item[] };

const ITEM = /^(\s*)([-*]|\d+\.)\s+(.*)$/;

function parse(markdown: string): Block[] {
  const blocks: Block[] = [];
  const lines = markdown.replace(/\r/g, "").split("\n");
  let i = 0;
  while (i < lines.length) {
    if (!lines[i].trim()) { i++; continue; }
    const first = ITEM.exec(lines[i]);
    if (first) {
      const kind = /\d/.test(first[2]) ? "ol" : "ul";
      const base = first[1].length;
      const items: Item[] = [];
      const stack: { indent: number; item: Item }[] = [];
      while (i < lines.length && (lines[i].trim() || ITEM.test(lines[i + 1] ?? ""))) {
        const line = lines[i];
        const m = ITEM.exec(line);
        if (m && m[1].length >= base) {
          const item = { text: m[3], children: [] };
          while (stack.length && stack[stack.length - 1].indent >= m[1].length) stack.pop();
          (stack.length ? stack[stack.length - 1].item.children : items).push(item);
          stack.push({ indent: m[1].length, item });
        } else if (line.trim() && stack.length) {
          stack[stack.length - 1].item.text += ` ${line.trim()}`;
        }
        i++;
      }
      blocks.push({ kind, items });
      continue;
    }
    let text = lines[i].trim();
    i++;
    while (i < lines.length && lines[i].trim() && !ITEM.test(lines[i])) text += ` ${lines[i++].trim()}`;
    blocks.push({ kind: "p", text });
  }
  return blocks;
}

function List({ kind, items, k }: { kind: "ul" | "ol"; items: Item[]; k: string }) {
  const Tag = kind;
  return (
    <Tag>
      {items.map((item, i) => (
        <li key={`${k}-${i}`}>
          {inline(item.text, `${k}-${i}`)}
          {item.children.length > 0 && <List kind="ul" items={item.children} k={`${k}-${i}`} />}
        </li>
      ))}
    </Tag>
  );
}

export default function Markdown({ text, className }: { text: string; className?: string }) {
  return (
    <div className={className}>
      {parse(text).map((block, i) =>
        block.kind === "p" ? <p key={i}>{inline(block.text, `p${i}`)}</p> : <List key={i} kind={block.kind} items={block.items} k={`l${i}`} />,
      )}
    </div>
  );
}
