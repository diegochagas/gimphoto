// The navigation bar and the footer, on every page.
import { type Lang, localePath, t } from "@/lib/i18n";
import { AUTHOR, BOARD_URL, REPO_URL, asset } from "@/lib/site";
import { Stars } from "./GitHub";
import { LangSwitch } from "./LangSwitch";

export function Nav({ lang, path = "/" }: { lang: Lang; path?: string }) {
  const home = asset(localePath(lang, "/"));
  return (
    <header className="nav" id="top">
      <div className="nav-inner">
        <a className="brand" href={home} aria-label="GIMPhoto">
          <img src={asset("/icon.svg")} alt="" width={32} height={32} />
          <span>GIMPhoto</span>
        </a>
        <nav className="nav-links" aria-label={t(lang, "nav.features")}>
          <a href={`${home}#features`}>{t(lang, "nav.features")}</a>
          <a href={`${home}#ai`}>{t(lang, "nav.ai")}</a>
          <a href={`${home}#roadmap`}>{t(lang, "nav.roadmap")}</a>
          <a href={`${home}#install`}>{t(lang, "nav.install")}</a>
        </nav>
        <div className="nav-actions">
          <a className="gh-pill" href={REPO_URL} aria-label={`GitHub: ${t(lang, "stats.stars")}`}>
            <svg aria-hidden="true" viewBox="0 0 16 16" width="16" height="16"><path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" /></svg>
            <Stars prefix="★ " />
          </a>
          <LangSwitch lang={lang} path={path} />
          <a className="btn btn-primary btn-sm" href={`${home}#donate`}>{t(lang, "nav.donate")}</a>
        </div>
      </div>
    </header>
  );
}

export function Footer({ lang }: { lang: Lang }) {
  return (
    <footer className="footer">
      <div className="container footer-grid">
        <div className="brand">
          <img src={asset("/icon.svg")} alt="" width={28} height={28} />
          <span>GIMPhoto</span>
        </div>
        <nav aria-label="GitHub">
          <a href={`${REPO_URL}#features`}>{t(lang, "footer.docs")}</a>
          <a href={`${REPO_URL}/issues`}>{t(lang, "footer.issues")}</a>
          <a href={BOARD_URL}>{t(lang, "footer.board")}</a>
          <a href={REPO_URL}>GitHub</a>
        </nav>
        <p className="fine">
          {t(lang, "footer.made")} <a href={AUTHOR.url}>{AUTHOR.name}</a>. {t(lang, "footer.license")}
        </p>
        <p className="fine">{t(lang, "footer.trademark")}</p>
      </div>
    </footer>
  );
}
