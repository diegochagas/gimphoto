// One feature: its README description, its documentation's before and after
// screenshots, how it is tested (in its page's words) and its other
// screenshots, with a link to the whole page on GitHub.
import { type Feature, catalogue } from "@/lib/catalogue";
import { type Lang, localePath, t } from "@/lib/i18n";
import { asset, docsUrl, shot } from "@/lib/site";
import { Footer, Nav } from "./Chrome";
import { featureTitle } from "./Home";
import Markdown, { inline } from "./Markdown";

export function findFeature(slug: string): { feature: Feature; prev?: Feature; next?: Feature } {
  const all = catalogue();
  const i = all.findIndex((f) => f.slug === slug);
  if (i < 0) throw new Error(`No feature ${slug}`);
  return { feature: all[i], prev: all[i - 1], next: all[i + 1] };
}

export default function FeaturePage({ lang, slug }: { lang: Lang; slug: string }) {
  const { feature, prev, next } = findFeature(slug);
  const path = `/features/${slug}/`;
  const link = (f: Feature) => asset(localePath(lang, `/features/${f.slug}/`));
  return (
    <>
      <a className="skip" href="#main">{lang === "pt" ? "Pular para o conteúdo" : "Skip to content"}</a>
      <Nav lang={lang} path={path} />
      <main id="main">
        <header className="page-head">
          <div className="glow glow-a" aria-hidden="true" />
          <div className="container" style={{ position: "relative" }}>
            <a className="crumbs" href={`${asset(localePath(lang, "/"))}#catalogue`}>{t(lang, "feature.back")}</a>
            {feature.ai && <p><span className="tag">{t(lang, "features.ai")}</span></p>}
            <h1 className="grad">{featureTitle(lang, feature)}</h1>
            <p className="lead">{inline(feature.summary)}</p>
            {lang === "pt" && <p className="note-en">{t(lang, "feature.english")}</p>}
            <dl className="facts">
              <div><dt>{t(lang, "feature.photoshop")}</dt><dd>{inline(feature.photoshop)}</dd></div>
              <div><dt>{t(lang, "feature.where")}</dt><dd>{inline(feature.where)}</dd></div>
            </dl>
          </div>
        </header>

        <div className="container stack">
          {feature.before && feature.after && (
            <section aria-labelledby="compare-title">
              <h2 id="compare-title">{t(lang, "feature.compare")}</h2>
              <div className="compare">
                {[["feature.before", feature.before], ["feature.after", feature.after]].map(([label, s]) => {
                  const item = s as NonNullable<Feature["before"]>;
                  return (
                    <figure key={label as string}>
                      <a className="frame" href={shot(item.file)}><img src={shot(item.file)} alt={item.alt} loading="lazy" /></a>
                      <figcaption><strong>{t(lang, label as string)}</strong>{inline(item.caption ?? "")}</figcaption>
                    </figure>
                  );
                })}
              </div>
            </section>
          )}

          <section className="tests" aria-labelledby="tests-title" data-tests="">
            <h2 id="tests-title">{t(lang, "feature.tests")}</h2>
            {feature.tests ? <Markdown className="md" text={feature.tests} /> : <p className="muted">{t(lang, "feature.notests")}</p>}
          </section>

          {feature.gallery.length > 0 && (
            <section aria-labelledby="gallery-title">
              <h2 id="gallery-title">{t(lang, "feature.gallery")}</h2>
              <div className="gallery">
                {feature.gallery.map((item) => (
                  <figure key={item.file}>
                    <a className="frame" href={shot(item.file)}><img src={shot(item.file)} alt={item.alt} loading="lazy" /></a>
                    <figcaption>{inline(item.alt)}</figcaption>
                  </figure>
                ))}
              </div>
            </section>
          )}

          <p><a className="btn btn-ghost" href={docsUrl(feature.slug)}>{t(lang, "feature.docs")}</a></p>

          <nav className="pager" aria-label={t(lang, "feature.back")}>
            {prev ? <a href={link(prev)}><span>← {t(lang, "feature.prev")}</span><strong>{featureTitle(lang, prev)}</strong></a> : <span />}
            {next ? <a href={link(next)} style={{ textAlign: "right" }}><span>{t(lang, "feature.next")} →</span><strong>{featureTitle(lang, next)}</strong></a> : <span />}
          </nav>
        </div>
      </main>
      <Footer lang={lang} />
    </>
  );
}
