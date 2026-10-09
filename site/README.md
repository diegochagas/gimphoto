# GIMPhoto's website

Next.js (App Router, React, TypeScript), exported as static files and
published by GitHub Pages at <https://diegochagas.github.io/gimphoto/>, in
English (`/`) and Portuguese (`/pt/`).

## What it shows, and where it comes from

| Part | Source |
|---|---|
| The feature catalogue and one page per feature | The README's feature table and each `docs/features/<feature>.md`: its before and after screenshots, its other screenshots and how it is tested, read at build time (`src/lib/catalogue.ts`). A feature added to the README and the docs is on the site with the next deploy. |
| The large showcase on the home page | `content/features.json` (English and Portuguese) |
| Every interface text | `content/i18n.json` (the unit tests require the same keys in both languages) |
| Screenshots, icon, favicon, link preview | `docs/images/` and `branding/`, converted to WebP into `public/` by `scripts/assets.mjs` before each build (not stored twice in git) |
| Stars, latest release, roadmap | GitHub's API, from the visitor's browser; the page shows its own values when GitHub does not answer |
| Donation methods | `content/donate.json` |

## Donations

Fill in `content/donate.json`; an empty value hides that method, and with
none set up the section says donations are opening soon.

- `pix`: the key, and the receiver's name and city as the bank shows them.
  The site makes the PIX copy-and-paste code (the Banco Central's BR Code)
  and its QR code at build time.
- `links`: full `https://` addresses for GitHub Sponsors, Ko-fi, Buy Me a
  Coffee, PayPal or Liberapay.
- `goal`: a monthly amount and what came in, to show a progress bar (0:
  hidden).

## Develop

```bash
cd site
npm ci
npm run dev        # http://localhost:4310 (makes public/ first)
npm run check      # tsc --noEmit + unit tests (also run by scripts/check)
npm run e2e        # builds with /gimphoto, Playwright at 1280 and 375 px,
                   # screenshots in ../work/site-e2e/screenshots
```

The end-to-end tests answer GitHub's API themselves: no test calls an
outside service.

## Publish

`.github/workflows/site.yml` checks every pull request that touches the
site or what it shows, and on `main` builds with `SITE_BASE_PATH=/gimphoto`
and deploys to GitHub Pages. The repository's Pages source must be
"GitHub Actions" (Settings › Pages).
