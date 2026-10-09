"use client";
import { useState } from "react";
import { type Lang, t } from "@/lib/i18n";
import { SITE_URL } from "@/lib/site";

export default function ShareButton({ lang }: { lang: Lang }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className="linklike"
      type="button"
      onClick={async () => {
        const url = `${SITE_URL}/${lang === "pt" ? "pt/" : ""}`;
        if (navigator.share) {
          try { await navigator.share({ title: "GIMPhoto", text: t(lang, "meta.description"), url }); } catch { /* closed */ }
          return;
        }
        try {
          await navigator.clipboard.writeText(url);
          setCopied(true);
          setTimeout(() => setCopied(false), 1800);
        } catch { window.prompt("", url); }
      }}
    >
      {copied ? t(lang, "install.copied") : t(lang, "donate.other.share")}
    </button>
  );
}
