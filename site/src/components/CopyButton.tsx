"use client";
import { useState } from "react";

/** Copies text; says done for a moment. */
export default function CopyButton({ text, label, done, className = "", data }: { text: string; label: string; done: string; className?: string; data?: Record<string, string> }) {
  const [copied, setCopied] = useState(false);
  const extra = Object.fromEntries(Object.entries(data ?? {}).map(([k, v]) => [`data-${k}`, v]));
  return (
    <button
      type="button"
      className={className}
      {...extra}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1800);
        } catch {
          window.prompt("", text);
        }
      }}
    >
      {copied ? done : label}
    </button>
  );
}
