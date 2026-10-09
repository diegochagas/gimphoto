"use client";
// The install commands, as tabs (arrow keys move between them); Copy takes
// the commands of the open tab without their comments.
import { useRef, useState } from "react";
import { type Lang, t } from "@/lib/i18n";
import CopyButton from "./CopyButton";

const BUNDLE = [
  ["# 1. Download the latest release", ""],
  ["curl -fLO https://github.com/diegochagas/gimphoto/releases/latest/download/GIMPhoto.flatpak", ""],
  ["", ""],
  ["# 2. Install it for your user (fetches the GNOME runtime from Flathub)", ""],
  ["flatpak install --user GIMPhoto.flatpak", ""],
  ["", ""],
  ["# 3. Open it (it is also in the applications menu)", ""],
  ["flatpak run io.github.diegochagas.GIMPhoto", ""],
];
const SOURCE = [
  ["git clone --recursive https://github.com/diegochagas/gimphoto.git", ""],
  ["cd gimphoto", ""],
  ["scripts/bootstrap-tools", "# Flathub's builder + the GNOME SDK, once"],
  ["scripts/build", "# compiles GIMP with GIMPhoto's patches"],
  ["scripts/smoke", "# checks the installed build"],
  ["flatpak run io.github.diegochagas.GIMPhoto", ""],
];

function commands(lines: string[][]): string {
  return lines.map(([code]) => code).filter((code) => code && !code.startsWith("#")).join("\n");
}

function Code({ lines }: { lines: string[][] }) {
  return (
    <pre tabIndex={0}>
      <code>
        {lines.map(([code, comment], i) => (
          <span key={i}>
            {code.startsWith("#") ? <span className="c">{code}</span> : code}
            {comment && <span className="c">{`   ${comment}`}</span>}
            {"\n"}
          </span>
        ))}
      </code>
    </pre>
  );
}

export default function Install({ lang }: { lang: Lang }) {
  const [tab, setTab] = useState<"bundle" | "source">("bundle");
  const refs = { bundle: useRef<HTMLButtonElement>(null), source: useRef<HTMLButtonElement>(null) };
  const select = (next: "bundle" | "source") => {
    setTab(next);
    refs[next].current?.focus();
  };
  const tabButton = (id: "bundle" | "source", key: string) => (
    <button
      ref={refs[id]}
      role="tab"
      type="button"
      id={`tab-${id}`}
      aria-controls={`panel-${id}`}
      aria-selected={tab === id}
      tabIndex={tab === id ? 0 : -1}
      onClick={() => setTab(id)}
      onKeyDown={(event) => {
        if (event.key === "ArrowRight" || event.key === "ArrowLeft") select(id === "bundle" ? "source" : "bundle");
      }}
    >
      {t(lang, key)}
    </button>
  );
  return (
    <div className="terminal">
      <div className="term-head">
        <div className="tabs" role="tablist" aria-label={t(lang, "nav.install")}>
          {tabButton("bundle", "install.tab.bundle")}
          {tabButton("source", "install.tab.source")}
        </div>
        <CopyButton className="copy" text={commands(tab === "bundle" ? BUNDLE : SOURCE)} label={t(lang, "install.copy")} done={t(lang, "install.copied")} data={{ copy: "" }} />
      </div>
      <div className="panel" role="tabpanel" id="panel-bundle" aria-labelledby="tab-bundle" hidden={tab !== "bundle"}>
        <Code lines={BUNDLE} />
      </div>
      <div className="panel" role="tabpanel" id="panel-source" aria-labelledby="tab-source" hidden={tab !== "source"}>
        <Code lines={SOURCE} />
        <p className="note">{t(lang, "install.source.note")}</p>
      </div>
      <p className="note">{t(lang, "install.uninstall")}</p>
    </div>
  );
}
