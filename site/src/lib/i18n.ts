import texts from "../../content/i18n.json";

export type Lang = "en" | "pt";
export const LANGS: Lang[] = ["en", "pt"];
export type Localized = { en: string; pt?: string };

const dict = texts as Record<Lang, Record<string, string>>;

/** The interface text for key, in English when Portuguese lacks it. */
export function t(lang: Lang, key: string): string {
  return dict[lang][key] ?? dict.en[key] ?? key;
}

export function pick(lang: Lang, value: Localized): string {
  return (lang === "pt" && value.pt) || value.en;
}

/** The page's path in a language: English at /, Portuguese under /pt. */
export function localePath(lang: Lang, path = "/"): string {
  const clean = path.startsWith("/") ? path : `/${path}`;
  return lang === "pt" ? `/pt${clean === "/" ? "/" : clean}` : clean;
}

export function textKeys(): Record<Lang, string[]> {
  return { en: Object.keys(dict.en).sort(), pt: Object.keys(dict.pt).sort() };
}
