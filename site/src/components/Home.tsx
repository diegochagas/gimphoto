// The home page, in either language.
import showcase from "../../content/features.json";
import { type Feature, catalogue, cover } from "@/lib/catalogue";
import { type Lang, localePath, pick, t } from "@/lib/i18n";
import { LOCAL_AI_URL, REPO_URL, asset, shot } from "@/lib/site";
import { Footer, Nav } from "./Chrome";
import Donate from "./Donate";
import { GimpVersion, Release, Roadmap, RoadmapCount, Stars } from "./GitHub";
import Install from "./Install";
import { LangRedirect } from "./LangSwitch";
import { inline } from "./Markdown";
import Reveal from "./Reveal";

type Titles = Record<string, { en: string; pt?: string }>;

export function featureTitle(lang: Lang, feature: Feature): string {
  const pt = (showcase.titles as Titles)[feature.slug]?.pt;
  return lang === "pt" && pt ? pt : feature.title;
}

function Heart() {
  return <svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M12 21s-7.5-4.6-9.6-9.2C.9 8.5 2.9 4.5 6.6 4.5c2.1 0 3.6 1.2 5.4 3.1 1.8-1.9 3.3-3.1 5.4-3.1 3.7 0 5.7 4 4.2 7.3C19.5 16.4 12 21 12 21z" /></svg>;
}

function Icon({ d }: { d: string }) {
  return <span className="point-icon" aria-hidden="true"><svg viewBox="0 0 24 24" width="22" height="22"><path fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d={d} /></svg></span>;
}

export default function Home({ lang }: { lang: Lang }) {
  const features = catalogue();
  const names = features.map((f) => ({ name: featureTitle(lang, f), ai: f.ai }));
  const featurePath = (slug: string) => asset(localePath(lang, `/features/${slug}/`));
  return (
    <>
      {lang === "en" && <LangRedirect />}
      <a className="skip" href="#main">{lang === "pt" ? "Pular para o conteúdo" : "Skip to content"}</a>
      <Nav lang={lang} />
      <main id="main">
        <section className="hero">
          <div className="glow glow-a" aria-hidden="true" />
          <div className="glow glow-b" aria-hidden="true" />
          <div className="hero-inner">
            <div className="hero-copy">
              <a className="badge" href={`${REPO_URL}/releases/latest`}>
                <span className="badge-dot" aria-hidden="true" />
                <strong><Release /></strong> <span>{t(lang, "hero.badge.prefix")}</span>
                <span className="badge-link">{t(lang, "hero.badge.link")}</span>
              </a>
              <h1>
                <span className="grad">{t(lang, "hero.title.1")}</span>
                <span className="grad grad-2">{t(lang, "hero.title.2")}</span>
              </h1>
              <p className="lead">{t(lang, "hero.lead")}</p>
              <div className="cta-row">
                <a className="btn btn-primary" href="#install">{t(lang, "hero.download")}</a>
                <a className="btn btn-ghost" href="#donate"><Heart /><span>{t(lang, "hero.donate")}</span></a>
              </div>
              <ul className="checks">
                <li>{t(lang, "hero.check.1")}</li>
                <li>{t(lang, "hero.check.2")}</li>
                <li>{t(lang, "hero.check.3")}</li>
              </ul>
            </div>
            <figure className="hero-shot">
              <div className="window">
                <div className="window-bar" aria-hidden="true"><i /><i /><i /></div>
                <img src={shot("theme-after.png")} width={1460} height={800} alt={t(lang, "hero.shot")} fetchPriority="high" />
              </div>
            </figure>
          </div>
        </section>

        <section className="strip" aria-labelledby="strip-title">
          <h2 className="sr-only" id="strip-title">{t(lang, "strip.title")}</h2>
          <div className="marquee" aria-hidden="true">
            <div className="marquee-track">
              {/* twice, for a seamless loop; the copy is hidden when nothing moves */}
              {[...names, ...names].map((item, i) => (
                <span key={i} className={`${item.ai ? "ai" : ""} ${i >= names.length ? "dup" : ""}`.trim() || undefined}>{item.name}</span>
              ))}
            </div>
          </div>
          <ul className="sr-only">{names.map((item) => <li key={item.name}>{item.name}</li>)}</ul>
        </section>

        <section className="statement"><p>{t(lang, "statement")}</p></section>

        <section className="section" id="features" aria-labelledby="features-title">
          <div className="container">
            <p className="kicker">{t(lang, "features.kicker")}</p>
            <h2 id="features-title">{t(lang, "features.title")}</h2>
            <div className="showcase">
              {showcase.showcase.map((item) => (
                <Reveal key={item.id}>
                  <article className="feature">
                    <div className="feature-copy">
                      {"ai" in item && item.ai && <span className="tag">{t(lang, "features.ai")}</span>}
                      <h3>{pick(lang, item.title)}</h3>
                      <p>{pick(lang, item.text)}</p>
                      <a className="link-arrow" href={featurePath(item.docs)}>{t(lang, "features.docs")}</a>
                    </div>
                    <figure className="feature-shot">
                      <img loading="lazy" decoding="async" src={shot(item.image)} alt={pick(lang, item.title)} />
                    </figure>
                  </article>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        <section className="section" id="catalogue" aria-labelledby="catalogue-title">
          <div className="container">
            <p className="kicker">{t(lang, "catalogue.kicker")}</p>
            <h2 id="catalogue-title">{t(lang, "catalogue.title")}</h2>
            <p className="lead">{t(lang, "catalogue.lead")}</p>
            <div className="catalogue">
              {features.map((feature) => {
                const picture = cover(feature);
                const shots = [feature.before, feature.after, ...feature.gallery].filter(Boolean).length;
                return (
                  <a className="card" href={featurePath(feature.slug)} key={feature.slug}>
                    <div className={`card-shot ${picture ? "" : "empty"}`}>
                      <img loading="lazy" decoding="async" src={picture ? shot(picture.file, true) : asset("/icon.svg")} alt="" />
                    </div>
                    <div className="card-body">
                      <h3>{featureTitle(lang, feature)}</h3>
                      <p>{inline(feature.photoshop.replace(/^—\s*/, ""))}</p>
                      <div className="badges">
                        {feature.ai && <span className="pill ai">{t(lang, "features.ai")}</span>}
                        {feature.tests && <span className="pill tested">✓ {t(lang, "catalogue.tested")}</span>}
                        {shots > 0 && <span className="pill">{shots} {t(lang, "catalogue.shots")}</span>}
                      </div>
                    </div>
                  </a>
                );
              })}
            </div>
          </div>
        </section>

        <section className="section ai" id="ai" aria-labelledby="ai-title">
          <div className="container ai-grid">
            <div>
              <p className="kicker">{t(lang, "ai.kicker")}</p>
              <h2 id="ai-title">{t(lang, "ai.title")}</h2>
              <p className="lead">{t(lang, "ai.lead")}</p>
              <a className="btn btn-ghost" href={LOCAL_AI_URL}>{t(lang, "ai.setup")}</a>
            </div>
            <ul className="points">
              <li><Icon d="M12 3l7 3v6c0 4.5-3 7.6-7 9-4-1.4-7-4.5-7-9V6l7-3z" /><div><h3>{t(lang, "ai.point.1.title")}</h3><p>{t(lang, "ai.point.1.text")}</p></div></li>
              <li><Icon d="M4 12h16M12 4v16" /><div><h3>{t(lang, "ai.point.2.title")}</h3><p>{t(lang, "ai.point.2.text")}</p></div></li>
              <li><Icon d="M5 12l4 4 10-10" /><div><h3>{t(lang, "ai.point.3.title")}</h3><p>{t(lang, "ai.point.3.text")}</p></div></li>
            </ul>
          </div>
        </section>

        <section className="section" aria-labelledby="paths-title">
          <div className="container">
            <h2 id="paths-title">{t(lang, "paths.title")}</h2>
            <div className="paths">
              <a className="path" href={featurePath("photoshop-shortcuts")}><h3>{t(lang, "paths.1.title")}</h3><p>{t(lang, "paths.1.text")}</p><span className="link-arrow">{t(lang, "paths.1.link")}</span></a>
              <a className="path" href={LOCAL_AI_URL}><h3>{t(lang, "paths.2.title")}</h3><p>{t(lang, "paths.2.text")}</p><span className="link-arrow">{t(lang, "paths.2.link")}</span></a>
              <a className="path" href={`${REPO_URL}/issues`}><h3>{t(lang, "paths.3.title")}</h3><p>{t(lang, "paths.3.text")}</p><span className="link-arrow">{t(lang, "paths.3.link")}</span></a>
              <a className="path path-hot" href="#donate"><h3>{t(lang, "paths.4.title")}</h3><p>{t(lang, "paths.4.text")}</p><span className="link-arrow">{t(lang, "paths.4.link")}</span></a>
            </div>
          </div>
        </section>

        <section className="section" id="install" aria-labelledby="install-title">
          <div className="container install">
            <div>
              <p className="kicker">{t(lang, "install.kicker")}</p>
              <h2 id="install-title">{t(lang, "install.title")}</h2>
              <p className="lead">{t(lang, "install.lead")}</p>
              <p className="muted">{t(lang, "install.release")}: <a href={`${REPO_URL}/releases/latest`}><Release /></a></p>
            </div>
            <Install lang={lang} />
          </div>
        </section>

        <section className="section" id="roadmap" aria-labelledby="roadmap-title">
          <div className="container">
            <p className="kicker">{t(lang, "roadmap.kicker")}</p>
            <h2 id="roadmap-title">{t(lang, "roadmap.title")}</h2>
            <p className="lead">{t(lang, "roadmap.lead")}</p>
            <Roadmap lang={lang} />
            <a className="link-arrow" href="https://github.com/users/diegochagas/projects/1">{t(lang, "roadmap.board")}</a>
          </div>
        </section>

        <Donate lang={lang} />

        <section className="section stats" aria-label="GIMPhoto">
          <div className="container stats-grid">
            <div><strong><Stars /></strong><span>{t(lang, "stats.stars")}</span></div>
            <div><strong data-stat="features">{features.length}</strong><span>{t(lang, "stats.features")}</span></div>
            <div><strong><RoadmapCount /></strong><span>{t(lang, "stats.roadmap")}</span></div>
            <div><strong><GimpVersion /></strong><span>{t(lang, "stats.gimp")}</span></div>
          </div>
        </section>

        <section className="final">
          <h2 className="grad">{t(lang, "cta.title")}</h2>
          <p>{t(lang, "cta.text")}</p>
          <div className="cta-row center">
            <a className="btn btn-primary" href="#install">{t(lang, "hero.download")}</a>
            <a className="btn btn-ghost" href="#donate">{t(lang, "hero.donate")}</a>
          </div>
        </section>
      </main>
      <Footer lang={lang} />
    </>
  );
}

