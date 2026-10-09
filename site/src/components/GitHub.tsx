"use client";
// Live numbers from GitHub's public API, fetched by the visitor's browser
// (the page is static) and kept for ten minutes in sessionStorage. Until
// GitHub answers, or if it does not, the page's own values stay.
import { useEffect, useState } from "react";
import { type Lang, t } from "@/lib/i18n";
import { FALLBACK_RELEASE, REPO, ROADMAP_PARENT } from "@/lib/site";

type Issue = { number: number; title: string; url: string; votes: number };
type Data = { stars?: number; release?: string; roadmap?: Issue[] | "offline" };

const CACHE_MS = 10 * 60 * 1000;
let pending: Promise<Data> | null = null;

async function cached<T>(path: string): Promise<T> {
  const key = `gimphoto-site-gh:${path}`;
  try {
    const hit = JSON.parse(sessionStorage.getItem(key) ?? "null");
    if (hit && Date.now() - hit.at < CACHE_MS) return hit.data as T;
  } catch { /* no storage: fetch */ }
  const response = await fetch(`https://api.github.com/${path}`);
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  const data = (await response.json()) as T;
  try { sessionStorage.setItem(key, JSON.stringify({ at: Date.now(), data })); } catch { /* ignored */ }
  return data;
}

type RawIssue = { number: number; title: string; body?: string | null; html_url: string; pull_request?: unknown; reactions?: { "+1"?: number } };

/** Open issues, up to 300 (GitHub gives 100 a page). */
async function openIssues(): Promise<RawIssue[]> {
  const all: RawIssue[] = [];
  for (let page = 1; page <= 3; page++) {
    const batch = await cached<RawIssue[]>(`repos/${REPO}/issues?state=open&per_page=100&page=${page}`);
    all.push(...batch);
    if (batch.length < 100) break;
  }
  return all;
}

function load(): Promise<Data> {
  pending ??= (async () => {
    const [repo, release, issues] = await Promise.allSettled([
      cached<{ stargazers_count: number }>(`repos/${REPO}`),
      cached<{ tag_name: string }>(`repos/${REPO}/releases/latest`),
      openIssues(),
    ]);
    const parent = `#${ROADMAP_PARENT}`;
    return {
      stars: repo.status === "fulfilled" ? repo.value.stargazers_count : undefined,
      release: release.status === "fulfilled" ? release.value.tag_name : undefined,
      roadmap:
        issues.status === "fulfilled"
          ? issues.value
              .filter((i) => !i.pull_request && i.number !== ROADMAP_PARENT && (i.body ?? "").includes(parent))
              .sort((a, b) => a.number - b.number)
              .map((i) => ({ number: i.number, title: i.title, url: i.html_url, votes: i.reactions?.["+1"] ?? 0 }))
          : "offline",
    };
  })();
  return pending;
}

function useGitHub(): Data | null {
  const [data, setData] = useState<Data | null>(null);
  useEffect(() => {
    let live = true;
    load().then((d) => live && setData(d));
    return () => { live = false; };
  }, []);
  return data;
}

export function count(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1).replace(/\.0$/, "")}k` : String(n);
}

export function Stars({ prefix = "" }: { prefix?: string }) {
  const data = useGitHub();
  return <span data-stat="stars">{prefix}{data?.stars !== undefined ? count(data.stars) : "–"}</span>;
}

export function Release() {
  const data = useGitHub();
  return <span data-stat="release">{data?.release ?? FALLBACK_RELEASE}</span>;
}

export function GimpVersion() {
  const data = useGitHub();
  const version = (data?.release ?? FALLBACK_RELEASE).match(/^v?(\d+\.\d+\.\d+)/)?.[1];
  return <span data-stat="gimp">{version}</span>;
}

export function RoadmapCount() {
  const data = useGitHub();
  return <span data-stat="roadmap">{Array.isArray(data?.roadmap) ? data.roadmap.length : "–"}</span>;
}

export function Roadmap({ lang }: { lang: Lang }) {
  const data = useGitHub();
  if (!data) return <ol className="roadmap" aria-live="polite"><li className="muted rest">{t(lang, "roadmap.loading")}</li></ol>;
  if (data.roadmap === "offline" || !data.roadmap?.length) {
    return <ol className="roadmap" aria-live="polite"><li className="muted rest">{t(lang, "roadmap.offline")}</li></ol>;
  }
  const shown = data.roadmap.slice(0, 8);
  const rest = data.roadmap.length - shown.length;
  return (
    <ol className="roadmap" aria-live="polite">
      {shown.map((issue) => (
        <li className="item" key={issue.number}>
          {/* "Edit › Fill (Shift+F5) and Edit › Stroke dialogs, with ...": the part before the comma */}
          <a className="title" href={issue.url} title={issue.title}>{issue.title.split(/,\s|:\s/)[0]}</a>
          <a className="vote" href={issue.url} aria-label={`${t(lang, "roadmap.vote")}: ${issue.title}`}>
            👍 {issue.votes || t(lang, "roadmap.vote")}
          </a>
        </li>
      ))}
      {rest > 0 && <li className="rest">+{rest} {t(lang, "roadmap.more")}</li>}
    </ol>
  );
}
