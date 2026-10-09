// Where GIMPhoto lives, and paths that work under GitHub Pages' /gimphoto.
export const REPO = "diegochagas/gimphoto";
export const REPO_URL = `https://github.com/${REPO}`;
export const SITE_URL = "https://diegochagas.github.io/gimphoto";
export const BOARD_URL = "https://github.com/users/diegochagas/projects/1";
export const AUTHOR = { name: "Diego Chagas", url: "https://diegochagas.com/" };
export const LOCAL_AI_URL = "https://github.com/diegochagas/local-ai-setup";
// the issue tracking the Photoshop features still to build
export const ROADMAP_PARENT = 66;
// shown until GitHub answers (the release the site was built with)
export const FALLBACK_RELEASE = "v3.2.6";

const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

/** A file in public/, under the site's base path. */
export function asset(path: string): string {
  return `${BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

export function docsUrl(slug: string): string {
  return `${REPO_URL}/blob/main/docs/features/${slug}.md`;
}

/** The screenshot as the site serves it: WebP, full size or thumbnail. */
export function shot(file: string, thumb = false): string {
  const stem = file.replace(/\.png$/, "");
  return asset(thumb ? `/images/thumbs/${stem}.webp` : `/images/${stem}.webp`);
}
