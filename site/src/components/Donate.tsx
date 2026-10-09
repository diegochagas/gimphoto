// The donation section: what donations pay for and the methods set up in
// content/donate.json (an empty value hides a method). The PIX code and its
// QR code are made when the site is built.
import QRCode from "qrcode";
import donate from "../../content/donate.json";
import { type Lang, t } from "@/lib/i18n";
import { pixPayload } from "@/lib/pix";
import { REPO_URL } from "@/lib/site";
import CopyButton from "./CopyButton";
import ShareButton from "./ShareButton";

const ICONS: Record<string, string> = { "github-sponsors": "♥", kofi: "☕", buymeacoffee: "☕", paypal: "P", liberapay: "L" };

type Config = {
  pix: { key: string; name: string; city: string };
  links: Record<string, string>;
  goal: { monthly: number; raised: number; currency: string };
};

export default async function Donate({ lang, config = donate as Config }: { lang: Lang; config?: Config }) {
  const { pix, links, goal } = config;
  const payload = pix.key && pix.name && pix.city ? pixPayload(pix) : null;
  const qr = payload ? await QRCode.toString(payload, { type: "svg", margin: 0, errorCorrectionLevel: "M" }) : null;
  const methods = Object.entries(links).filter(([, url]) => url);
  const any = Boolean(payload) || methods.length > 0;
  const money = new Intl.NumberFormat(lang === "pt" ? "pt-BR" : "en", { style: "currency", currency: goal.currency || "BRL", maximumFractionDigits: 0 });

  return (
    <section className="section donate" id="donate" aria-labelledby="donate-title">
      <div className="glow glow-c" aria-hidden="true" />
      <div className="container donate-grid">
        <div>
          <p className="kicker">{t(lang, "donate.kicker")}</p>
          <h2 id="donate-title"><span className="grad">{t(lang, "donate.title")}</span></h2>
          <p className="lead">{t(lang, "donate.lead")}</p>
          <h3>{t(lang, "donate.why.title")}</h3>
          <ul className="why">
            <li>{t(lang, "donate.why.1")}</li>
            <li>{t(lang, "donate.why.2")}</li>
            <li>{t(lang, "donate.why.3")}</li>
          </ul>
          {goal.monthly > 0 && (
            <div className="goal" data-goal="">
              <div className="goal-head">
                <span>{t(lang, "donate.goal")}</span>
                <span>{money.format(goal.raised)} {t(lang, "donate.goal.of")} {money.format(goal.monthly)}</span>
              </div>
              <div className="goal-bar"><span style={{ width: `${Math.min(100, (100 * goal.raised) / goal.monthly)}%` }} /></div>
            </div>
          )}
        </div>
        <div className="give">
          <h3>{t(lang, "donate.methods.title")}</h3>
          {any ? (
            <div className="methods" data-methods="">
              {payload && qr && (
                <div className="pix">
                  <img className="pix-qr" src={`data:image/svg+xml;utf8,${encodeURIComponent(qr)}`} alt="PIX QR code" width={156} height={156} />
                  <div>
                    <strong>{t(lang, "donate.pix.title")}</strong>
                    <p>{t(lang, "donate.pix.text")}</p>
                    <p>{t(lang, "donate.pix.key")}: <span className="key">{pix.key}</span></p>
                    <CopyButton className="btn btn-primary btn-sm" text={payload} label={t(lang, "donate.pix.copy")} done={t(lang, "install.copied")} data={{ pix: payload }} />
                  </div>
                </div>
              )}
              {methods.map(([id, url]) => (
                <a className="method" href={url} key={id} rel="noopener" target="_blank">
                  <span className="m-icon" aria-hidden="true">{ICONS[id] ?? "♥"}</span>
                  <span className="m-body"><strong>{t(lang, `donate.link.${id}`)}</strong><span>{t(lang, `donate.link.${id}.text`)}</span></span>
                  <span className="m-go">{t(lang, "donate.give")} →</span>
                </a>
              ))}
            </div>
          ) : (
            <div className="soon" data-soon="">
              <h4>{t(lang, "donate.soon.title")}</h4>
              <p>{t(lang, "donate.soon.text")}</p>
            </div>
          )}
          <div className="other">
            <h4>{t(lang, "donate.other.title")}</h4>
            <ul>
              <li><a href={REPO_URL}>{t(lang, "donate.other.star")}</a></li>
              <li><a href={`${REPO_URL}/issues/new/choose`}>{t(lang, "donate.other.bug")}</a></li>
              <li><ShareButton lang={lang} /></li>
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
