"use client";
// The other language's version of this page; the choice is remembered, and
// a first visit from a Portuguese browser to the English home goes to /pt/.
import { useEffect } from "react";
import { type Lang, localePath, t } from "@/lib/i18n";
import { asset } from "@/lib/site";

export const LANG_KEY = "gimphoto-site-lang";

function remember(lang: Lang) {
  try { localStorage.setItem(LANG_KEY, lang); } catch { /* private window */ }
}

export function LangSwitch({ lang, path }: { lang: Lang; path: string }) {
  const other: Lang = lang === "pt" ? "en" : "pt";
  return (
    <a className="lang" href={asset(localePath(other, path))} hrefLang={other === "pt" ? "pt-BR" : "en"} onClick={() => remember(other)}>
      {t(lang, "nav.lang")}
    </a>
  );
}

export function LangRedirect() {
  useEffect(() => {
    let saved: string | null = null;
    try { saved = localStorage.getItem(LANG_KEY); } catch { /* none */ }
    const wanted = saved ?? (navigator.language.toLowerCase().startsWith("pt") ? "pt" : "en");
    if (wanted === "pt") window.location.replace(asset("/pt/") + window.location.hash);
  }, []);
  return null;
}
