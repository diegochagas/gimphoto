# GIMPhoto

**A GIMP edition with Photoshop-style tools and interface**, built from
GIMP's own source with a small series of changes on top, one feature at a
time, and kept up to date with each official GIMP release.

> **Status: just started.** GIMPhoto currently builds **unmodified GIMP
> 3.2.6** through its own pipeline: the base every feature will be added
> to. Planned features are tracked as
> [GitHub issues](../../issues) on the [project board](https://github.com/users/diegochagas/projects/1).

GIMPhoto is not affiliated with the GIMP project or with Adobe. "GIMP" is
the GNU Image Manipulation Program; Photoshop is a trademark of Adobe Inc.,
mentioned only to describe the goal. It is also unrelated to "Gimphoto",
an earlier Photoshop-style GIMP modification (2008–2015).

## Why a patched build?

Plug-ins, themes and shortcuts (see
[gimp-setup](https://github.com/diegochagas/gimp-setup)) already bring a lot
of Photoshop to the official GIMP, but they can only add **menu entries and
dialogs**. Anything in GIMP's own interface (a tool in the toolbox, a button
in the Layers panel, how a window is laid out, how a tool behaves on the
canvas) is compiled into GIMP. GIMPhoto changes that code directly.

## How it works

```
Flathub's GIMP recipe ──┐
(flatpak/upstream/)     ├─ tools/make_manifest.py ─> flatpak/io.github.diegochagas.GIMPhoto.json
GIMPhoto's patches ─────┘                                     │
(patches/series)                                       scripts/build (flatpak-builder)
                                                              │
                                     GIMPhoto, installed next to the official GIMP
```

- **The base is Flathub's recipe** for the official GIMP Flatpak, vendored
  in `flatpak/upstream/`: same GIMP version, same libraries, same build
  options and sandbox. GIMPhoto's generated manifest differs only in its app
  ID (`io.github.diegochagas.GIMPhoto`), its launcher name and the patches
  it applies.
- **GIMPhoto's changes are a patch series** in `patches/`, applied to GIMP's
  source after Flathub's own patch. One patch = one feature = one pull
  request.
- **It installs next to the official GIMP**, not over it, and uses the same
  user profile (`~/.config/GIMP/3.x`): your plug-ins, brushes, theme and
  shortcuts work in both. Flathub's GIMP add-ons (G'MIC, Resynthesizer)
  load in GIMPhoto as well.
- **Updating to a new GIMP** is `scripts/sync-flathub`: it pulls Flathub's
  new recipe and checks that every patch still applies; patches that no
  longer do are adapted in a normal git checkout (see
  [CONTRIBUTING.md](CONTRIBUTING.md#updating-gimp)).

## Install (build it yourself)

Releases with ready-made Flatpak bundles will come with the first feature.
Until then, build it, on any Linux with Flatpak, without sudo:

```bash
git clone --recursive https://github.com/diegochagas/gimphoto.git && cd gimphoto
scripts/bootstrap-tools   # Flathub's flatpak-builder + the GNOME SDK (~1.5 GB, once)
scripts/build             # compiles GIMP and its libraries: about an hour the first time
scripts/smoke             # checks the installed build
flatpak run io.github.diegochagas.GIMPhoto
```

GIMPhoto then also appears in the applications menu. Later builds only
recompile what changed. To remove it:
`flatpak uninstall --user io.github.diegochagas.GIMPhoto`.

## Scripts

| Script | What it does |
|---|---|
| `scripts/bootstrap-tools` | Installs Flathub's builder app and the SDK the recipe needs (per user) |
| `scripts/build` | Builds and installs GIMPhoto (`--no-install`: only build) |
| `scripts/smoke` | Checks the installed build: starts, GIMP version, user profile, launcher name |
| `scripts/source` | Checks out GIMP's source with the patches as git commits in `work/gimp`, to write features |
| `scripts/export-patches` | Turns those commits back into `patches/` |
| `scripts/sync-flathub` | Updates to Flathub's latest GIMP recipe and checks the patches still apply |
| `scripts/check` | The gate: lint, unit tests, manifest up to date, patches apply (pre-push hook and CI) |

## Contributing

Features are proposed and tracked as GitHub issues, organized on the
[project board](https://github.com/users/diegochagas/projects/1); each one is implemented as one patch in one pull request.
[CONTRIBUTING.md](CONTRIBUTING.md) explains the workflow.

## License

GPL-3.0-or-later, the license of GIMP itself ([LICENSE](LICENSE)). The
patches in `patches/` modify GIMP and are distributed under the same
license.
