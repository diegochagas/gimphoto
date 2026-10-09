// Every feature GIMPhoto has, read at build time from the repository: the
// README's feature table (name, Photoshop equivalent, where it lives, its
// page) and each docs/features/<slug>.md page (its before and after
// screenshots, its other screenshots, and how it is tested). Adding a
// feature to the README and docs puts it on the site.
import fs from "node:fs";
import path from "node:path";

export const REPO_ROOT = path.resolve(process.cwd(), "..");
const README = path.join(REPO_ROOT, "README.md");
const DOCS = path.join(REPO_ROOT, "docs", "features");
export const IMAGES = path.join(REPO_ROOT, "docs", "images");

export type Shot = { file: string; alt: string; caption?: string };

export type Feature = {
  slug: string;
  /** the feature's name, as the README's table writes it in bold */
  title: string;
  /** the README's description (markdown, inline) */
  summary: string;
  photoshop: string;
  where: string;
  ai: boolean;
  before: Shot | null;
  after: Shot | null;
  /** the page's other screenshots, in its order */
  gallery: Shot[];
  /** how the feature is tested, as its page says it (markdown blocks), or null */
  tests: string | null;
};

const IMAGE = /!\[([^\]]*)\]\(\.\.\/images\/([^)\s]+)\)/g;

function cells(row: string): string[] {
  return row
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split(/\s\|\s|\s\|$|^\|\s/)
    .map((cell) => cell.trim());
}

/** The README's feature rows, in their order. */
export function readmeRows(): { slug: string; title: string; summary: string; photoshop: string; where: string }[] {
  const lines = fs.readFileSync(README, "utf8").split("\n");
  const start = lines.findIndex((line) => /^## Features\b/.test(line));
  const rows = [];
  for (const line of lines.slice(start + 1)) {
    if (line.startsWith("## ")) break;
    if (!line.startsWith("| **")) continue;
    const [first, photoshop, where, docs] = cells(line);
    const title = /\*\*(.+?)\*\*/.exec(first)?.[1] ?? first;
    // after the name: an optional "(AI)" note and a colon or comma
    const summary = first.replace(/^\*\*.+?\*\*\s*(\([^)]*\))?[:,]?\s*/, "");
    const slug = /features\/([\w-]+)\.md/.exec(docs)?.[1];
    if (!slug) throw new Error(`README feature without a docs page: ${title}`);
    rows.push({ slug, title, summary, photoshop, where });
  }
  return rows;
}

function sections(markdown: string): { heading: string; body: string }[] {
  const out: { heading: string; body: string }[] = [{ heading: "", body: "" }];
  for (const line of markdown.split("\n")) {
    if (line.startsWith("## ")) out.push({ heading: line.slice(3).trim(), body: "" });
    else out[out.length - 1].body += `${line}\n`;
  }
  return out;
}

function images(markdown: string): Shot[] {
  return [...markdown.matchAll(IMAGE)].map((m) => ({ alt: m[1], file: m[2] }));
}

/** The first table in "Before and after" whose first row holds two
 * screenshots: before and after, captioned by its header. */
function beforeAfter(markdown: string): { before: Shot; after: Shot } | null {
  const section = sections(markdown).find((s) => /^before and after/i.test(s.heading));
  if (!section) return null;
  const lines = section.body.split("\n");
  for (let i = 0; i + 2 < lines.length; i++) {
    if (!lines[i].startsWith("|") || !/^\|[-|\s:]+\|$/.test(lines[i + 1].trim())) continue;
    const header = cells(lines[i]);
    const row = cells(lines[i + 2]).map((cell) => images(cell)[0]);
    if (header.length === 2 && row.length === 2 && row[0] && row[1]) {
      const strip = (text: string) => text.replace(/\*/g, "");
      return {
        before: { ...row[0], caption: strip(header[0]) },
        after: { ...row[1], caption: strip(header[1]) },
      };
    }
  }
  return null;
}

/** What the page says about its tests: a "Test"/"Tests" section, and any
 * paragraph (with its list) opening with **Tests:**, **Test:** or
 * **Smoke test**. */
export function testsOf(markdown: string): string | null {
  const blocks: string[] = [];
  for (const { heading, body } of sections(markdown)) {
    if (/^(tests?|how it (was|is) tested)$/i.test(heading)) {
      blocks.push(body.trim());
      continue;
    }
    const lines = body.split("\n");
    for (let i = 0; i < lines.length; i++) {
      // a list item "- **Tests:** ...": the item, its continuation lines and
      // nested items, de-indented
      const item = /^(\s*)[-*]\s+(\*\*(tests?|smoke tests?)\b[^*]*\*\*.*)$/i.exec(lines[i]);
      if (item) {
        const indent = item[1].length + 2;
        const block = [item[2]];
        const inItem = (line: string) => line.slice(0, indent).trim() === "" && line.trim() !== "";
        for (let j = i + 1; j < lines.length; j++) {
          if (inItem(lines[j])) block.push(lines[j].slice(indent));
          else if (lines[j].trim() === "" && inItem(lines[j + 1] ?? "")) block.push("");
          else break;
        }
        blocks.push(block.join("\n").trim());
        continue;
      }
      if (!/^\*\*(tests?|smoke tests?)\b[^*]*\*\*/i.test(lines[i])) continue;
      const block = [lines[i]];
      for (let j = i + 1; j < lines.length; j++) {
        const line = lines[j];
        const next = lines[j + 1] ?? "";
        if (line.trim() === "" && !/^\s*([-*]|\d+\.)\s|^\s{2,}\S/.test(next)) break;
        block.push(line);
      }
      blocks.push(block.join("\n").trim());
    }
  }
  return blocks.length ? blocks.join("\n\n") : null;
}

const AI = /\(AI\b|\bAI\)|local AI|ComfyUI/i;

let parsed: Feature[] | null = null;

/** Every feature (read once per build). */
export function catalogue(): Feature[] {
  parsed ??= readmeRows().map((row) => {
    const markdown = fs.readFileSync(path.join(DOCS, `${row.slug}.md`), "utf8");
    const pair = beforeAfter(markdown);
    const used = new Set([pair?.before.file, pair?.after.file]);
    const seen = new Set<string>();
    const gallery = images(markdown).filter((shot) => {
      if (used.has(shot.file) || seen.has(shot.file)) return false;
      seen.add(shot.file);
      return true;
    });
    return {
      ...row,
      ai: AI.test(row.title) || AI.test(row.summary) || AI.test(row.where),
      before: pair?.before ?? null,
      after: pair?.after ?? null,
      gallery,
      tests: testsOf(markdown),
    };
  });
  return parsed;
}

/** A PNG's width and height, from its header. */
export function pngSize(file: string): { width: number; height: number } {
  const header = Buffer.alloc(24);
  const fd = fs.openSync(path.join(IMAGES, file), "r");
  try {
    fs.readSync(fd, header, 0, 24, 0);
  } finally {
    fs.closeSync(fd);
  }
  return { width: header.readUInt32BE(16), height: header.readUInt32BE(20) };
}

const area = (shot: Shot) => {
  const { width, height } = pngSize(shot.file);
  return width * height;
};

/** The screenshot that stands for the feature on its card: the after shot
 * when it is a window-sized picture, else the page's largest (a menu or a
 * button strip would be blown up beyond reading). */
export function cover(feature: Feature): Shot | null {
  if (feature.after && pngSize(feature.after.file).width >= 900) return feature.after;
  const shots = [feature.after, ...feature.gallery].filter((s): s is Shot => s !== null);
  return shots.sort((a, b) => area(b) - area(a))[0] ?? null;
}
