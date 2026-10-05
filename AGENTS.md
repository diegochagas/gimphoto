# GIMPhoto: rules for contributors and coding agents

GIMPhoto = Flathub's GIMP recipe (`flatpak/upstream/`, vendored, never edited
by hand) + a patch series (`patches/`) + a generator
(`tools/make_manifest.py`) that combines them into
`flatpak/io.github.diegochagas.GIMPhoto.json` (committed, never edited by hand).

## Ground rules

- **One feature per patch, one patch per PR**, linked to its GitHub issue.
  Patches are made in `work/gimp` (`scripts/source`) as one commit each and
  exported with `scripts/export-patches`; never edit `patches/*.patch` by hand.
- **Plug-in first:** only patch GIMP's C code for what a plug-in cannot do
  (toolbox, docks, canvas tools, window layout). Keep patches small: every
  line has to be re-applied on each GIMP update.
- **A GEGL operation** (`gegl/<name>.c`, built by the manifest's
  `gimphoto-gegl-ops` module) when a layer effect needs pixels no GEGL
  operation draws: it is saved in the XCF like GIMP's own filters, which a
  graph built by a plug-in is not.
- **Flathub's recipe stays Flathub's.** Changes to the build go through the
  generator, and its tests in `tests/` pin what may differ (app ID, launcher
  name, own user profile, patches, the `plugins/` module). Updating GIMP =
  `scripts/sync-flathub`.
- GIMP's code style (GNU) inside patches; no reformatting of lines a feature
  does not need to touch.
- **Every modification is documented**: `docs/features/<feature>.md` with
  before/after screenshots of it in use, plus its row in the README's
  feature table. A feature PR without them is not done.
- **The README shows only** the splash screen (which carries the logo) and
  one screenshot of GIMPhoto open (`docs/images/gimphoto.png`). Every feature's screenshots go
  on its own page; a PR that changes what GIMPhoto looks like also updates
  `docs/images/gimphoto.png`.
- No personal paths, IPs, tokens or real user data in code, tests or docs.

## Testing and shipping (dev-playbook)

This repo follows the dev-playbook (`~/.claude/skills/dev-playbook/PLAYBOOK.md`).

- One gate: `scripts/check` (shellcheck + shfmt, ruff, unit tests, manifest
  up to date, patches apply). The pre-push hook runs it
  (`git config core.hooksPath .githooks`). Never push with `--no-verify`.
- The build is not part of the gate (about an hour): `scripts/build` +
  `scripts/smoke` locally for every patch, and CI builds pull requests.
- Bugs: write a failing regression test first, then fix.
- Never weaken, skip or delete a test to make it pass.
- UI changes: attach before/after screenshots of every changed window or
  tool to the PR (GIMP running the build from the PR).
- Risk class for this repo: **system** (it installs an application) and
  **public project others install**. Safeguards: the build installs next to
  the official GIMP (own app ID), never over it; `scripts/source` never
  discards unexported work; patch applicability is checked on every push.
- External services are never called by tests.
- Before finishing: run `/code-review` on the diff, then give the evidence
  package: summary, risk class, test results, screenshots, rollback steps
  (`flatpak uninstall --user io.github.diegochagas.GIMPhoto`, or revert the PR).
