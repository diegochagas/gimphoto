# Contributing to GIMPhoto

Thanks for helping make GIMP feel at home for Photoshop users. GIMPhoto is
GIMP plus a series of patches, **one feature per patch**. This page explains
how a feature goes from idea to merged patch, and how the patches follow
new GIMP releases.

## 1. Pick or propose a feature

- Features live as **GitHub issues** (template *Photoshop feature*), on the
  project board: *Backlog → Ready → In progress → In review → Done*.
- Comment on an issue before starting, so two people don't build the same
  thing; a maintainer assigns it and moves it to *In progress*.
- **Prefer a plug-in when one can do it.** A patch to GIMP's C code is only
  for what plug-ins cannot reach (the toolbox, docks, canvas tools, window
  layout). Logic that can live in a Python plug-in should live there, with
  the patch only adding the button or hook that calls it: small patches
  survive GIMP updates.

## 2. Set up (once)

Linux with Flatpak, git and Python 3. No sudo needed.

```bash
git clone --recursive https://github.com/<you>/gimphoto.git && cd gimphoto
git config core.hooksPath .githooks   # runs scripts/check before every push
scripts/bootstrap-tools               # builder + GNOME SDK (~1.5 GB, once)
scripts/build                         # first build: about an hour
scripts/smoke
```

## 3. Write the feature

```bash
scripts/source            # GIMP source at the pinned version in work/gimp,
                          # the existing patches applied as commits
cd work/gimp              # a normal git checkout of GIMP (branch "gimphoto")
# ... edit GIMP's code ...
git add -A && git commit  # ONE commit for the feature, new files included
                          # (git commit --amend while you work)
cd ../..
scripts/export-patches    # commits -> patches/NNNN-*.patch + patches/series
scripts/build             # rebuilds GIMP with your patch (incremental)
scripts/smoke             # and try it: flatpak run io.github.diegochagas.GIMPhoto
scripts/check
```

- **Commit message** = the patch's description, read by whoever adapts it to
  the next GIMP release. Subject: `Layers dock: add the Layer Style (fx)
  button`. Body: what it does, which GIMP files it touches and why, and how
  to test it. Reference the issue (`Closes #12`).
- **Follow GIMP's code style** (GNU style, see `work/gimp/devel-docs/`) so
  the patch could one day be proposed upstream.
- **Keep unrelated changes out** of the patch, including reformatting.
- `scripts/source` refuses to throw away work that was not exported yet;
  `--force` overrides that.

## 4. Open the pull request

- One feature per PR: the patch, `patches/series`, the regenerated
  `flatpak/io.github.diegochagas.GIMPhoto.json`, and any docs.
- Fill in the template: what changed, **screenshots** of the new interface
  (before/after), how you tested it, and how to roll back.
- CI runs `scripts/check` (lint, unit tests, manifest, patches apply) and
  builds GIMPhoto with the patch; the build is attached to the run.

## Updating GIMP

When Flathub publishes a new GIMP (or library update):

```bash
scripts/sync-flathub          # pulls Flathub's latest recipe into flatpak/upstream/
                              # and checks every patch still applies
```

- **All patches apply:** `scripts/build`, `scripts/smoke`, try each feature,
  commit `flatpak/` (*"Update to GIMP 3.2.7 (Flathub abc1234)"*).
- **A patch does not apply** (GIMP changed the code it touches): the
  script names it. Adapt it like a conflict in a git rebase:

  ```bash
  scripts/source --force             # applies the series, stops at that patch
  cd work/gimp
  git am --show-current-patch=diff   # what the patch wanted to do
  # make that change by hand on GIMP's new code, then:
  git add -A
  git am --continue                  # the remaining patches apply after it
  cd ../.. && scripts/export-patches && scripts/build && scripts/smoke
  ```

  Commit the adapted patch together with the `flatpak/` update.

Each GIMP update gets its own issue (label `gimp-update`) and PR.

## Labels

| Label | Meaning |
|---|---|
| `feature` | A Photoshop-style feature (one patch or plug-in) |
| `bug` | Something broken in GIMPhoto |
| `gimp-update` | Following a new GIMP / Flathub release |
| `needs-patch-update` | A patch no longer applies to the new GIMP |
| `good first issue` | Small and well defined |
| `plugin` / `core-patch` | Where the change lives |

## Tests

`scripts/check` must pass (the pre-push hook runs it). Changes to the
scripts or tools need a unit test in `tests/`. Interface changes need
screenshots in the PR. See [AGENTS.md](AGENTS.md) for the full rules,
which apply to people and coding agents alike.
