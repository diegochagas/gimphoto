// The <html> of every page, in its language, with the fonts (self-hosted
// by Next at build time: the visitor's browser asks no font service).
import { Inter, JetBrains_Mono } from "next/font/google";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import "@/app/globals.css";
import { type Lang, localePath, t } from "@/lib/i18n";
import { SITE_URL, asset } from "@/lib/site";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", weight: ["400", "500"], display: "swap" });

export function Document({ lang, children }: { lang: Lang; children: ReactNode }) {
  return (
    <html lang={lang === "pt" ? "pt-BR" : "en"} className={`${inter.variable} ${mono.variable}`}>
      <head>
        <link rel="icon" type="image/svg+xml" href={asset("/icon.svg")} />
        <link rel="icon" type="image/png" href={asset("/favicon.png")} />
        {/* without JavaScript nothing fades in: show it all */}
        <noscript>
          <style>{".reveal{opacity:1;transform:none}"}</style>
        </noscript>
      </head>
      <body>{children}</body>
    </html>
  );
}

/** Title, description, canonical and language links, link previews. */
export function pageMetadata(lang: Lang, path: string, title?: string, description?: string): Metadata {
  const fullTitle = title ? `${title}: ${t(lang, "feature.suffix")} · GIMPhoto` : t(lang, "meta.title");
  const text = description ?? t(lang, "meta.description");
  const url = `${SITE_URL}${localePath(lang, path)}`;
  return {
    metadataBase: new URL(`${SITE_URL}/`),
    title: fullTitle,
    description: text,
    alternates: {
      canonical: url,
      languages: { en: `${SITE_URL}${localePath("en", path)}`, "pt-BR": `${SITE_URL}${localePath("pt", path)}` },
    },
    openGraph: { type: "website", title: fullTitle, description: text, url, images: [{ url: `${SITE_URL}/og.png`, width: 1200, height: 630 }], locale: lang === "pt" ? "pt_BR" : "en_US" },
    twitter: { card: "summary_large_image" },
    other: { "theme-color": "#15111d" },
  };
}
