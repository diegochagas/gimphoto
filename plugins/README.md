# GIMPhoto's own plug-ins

Python plug-ins that GIMPhoto installs as **system plug-ins**
(`/app/lib/gimp/3.0/plug-ins/<name>/`), so the features that use them work
in any GIMPhoto install, with a fresh profile and nothing else installed.

Each folder is one plug-in; GIMP runs the file named after the folder
(`<name>/<name>.py`), and the other files beside it are its modules.
`tools/make_manifest.py` adds every folder here to the build (module
`gimphoto-plug-ins`), so a new plug-in is just a new folder.

| Plug-in | Used by | Origin |
|---|---|---|
| `layer-style/` | The Layers panel's **fx** button ([docs](../docs/features/layer-style-fx-button.md)); also *Layer > Layer Style* | gimp-setup's [Layer Style](https://github.com/diegochagas/gimp-setup/blob/main/docs/LAYER_STYLE.md) plug-in |
| `layer-via/` | Layer via Copy / Cut on Ctrl+J / Ctrl+Shift+J ([docs](../docs/features/layer-via-copy-cut.md)) | GIMPhoto |
| `psd-text/` | PSD with editable text and Layer Styles, open and export ([docs](../docs/features/psd-editable-text.md)) | gimp-setup's [PSD with editable text](https://github.com/diegochagas/gimp-setup/blob/main/docs/PSD_TEXT.md) |
| `ai-select/` | Select Subject (AI), *Select › Subject* and the Properties panel's Quick Action ([docs](../docs/features/select-subject.md)); the Object Selection tool's AI, `gimphoto-object-select` ([docs](../docs/features/object-selection.md)); Remove Background, *Layer › Remove Background* and the Properties panel's Quick Action ([docs](../docs/features/remove-background.md)) | GIMPhoto (BiRefNet; gimp-setup's AI Object Selection used SAM) |
| `comfyui-service/` | Starts the local ComfyUI with GIMPhoto and stops it on quit ([docs](../docs/features/comfyui-with-gimphoto.md)) | GIMPhoto (gimp-setup's `gimp-with-comfyui` launcher does the same for GIMP) |
| `smart-objects/` | Smart Objects in *Layer > Smart Object* and the Layers panel's right-click menu ([docs](../docs/features/smart-objects.md)) | gimp-setup's Smart Objects plug-in |

## layer-style

Copied from gimp-setup (`assets/plug-ins/layer-style`, commit 8287f63),
then changed here:

- effects whose GEGL operations this GIMP does not have are shown greyed
  out, with what they need, instead of doing nothing.

- Gradient Overlay and Pattern Overlay are drawn by GIMPhoto's own GEGL
  operations, `gimphoto:gradient-overlay` and `gimphoto:pattern-overlay`
  (`gegl/`), instead of `lb:effects` from LinuxBeaver's GEGL plug-ins, which
  GIMP does not ship. Gradient Overlay gains Photoshop's styles (Linear,
  Radial, Angle, Reflected, Diamond); Pattern Overlay takes a GIMP pattern
  (exported once to the profile's `gimphoto-patterns/`) or an image file,
  and a scale. Pattern, Gradient and Color Overlay stack as in Photoshop
  (Color on top). gimp-setup's copy keeps `lb:effects`.

- effects are added with the selection set aside (and put back): GIMP
  crops a filter to the selection there is when it is added, so with a
  selection the effects showed only inside it, or not at all.

- formatted with ruff and lint-clean for this repo's `scripts/check`
  (an unused import, a long line and two one-letter names fixed).

Fixes that apply to both copies should be made in both.

## psd-text

Copied from gimp-setup (`assets/plug-ins/psd-text`, after commit 71868f8),
then changed here:

- Node.js: GIMPhoto's own (`/app/lib/gimphoto/node/bin/node`, from
  Flathub's Node SDK extension) after `PSD_TEXT_NODE`, then `node` on PATH;
  gimp-setup's `~/.config/PhotoGIMP/node-path` and nvm lookups removed.
  ag-psd is installed by the build (`gimphoto-psd-text-npm`), not by npm at
  install time.
- Layer Styles through GIMPhoto's own engine, imported from
  `plug-ins/layer-style` instead of a copy next to the plug-in; the
  Gradient Overlay's style (linear, radial, angle, reflected, diamond) read
  from and written to the PSD.
- Smart objects both ways (with `smart-objects/`): Photoshop's placed
  layers with embedded files open as link layers on the same corners, their
  contents saved as XCF; link layers export as placed layers with their
  contents embedded. Their transform comes from GIMPhoto's
  `gimp-link-layer-get-corners` (its bounds without it).
- The text-language setting is `psd-text-language` in the GIMP profile
  instead of `~/.config/PhotoGIMP/`.
- Lint-clean for this repo's `scripts/check` (one-letter names renamed,
  long lines wrapped, a lambda made a function).

Its `psd_text_gimp.py`, `psd_text_fonts.py` and the `.mjs` scripts come from
comic-skills' `psd-xcf-convert` (see gimp-setup's
`assets/plug-ins/psd-text/PATCHES.md`).

## smart-objects

Copied from gimp-setup (`assets/plug-ins/smart-objects`, commit e2d10ad),
then changed here:

- the Layers panel's right-click menu shows its three commands (GIMPhoto's
  `patches/0006-…`), noted in its header;
- contents of an image never saved go in the app's data folder (GIMPhoto's
  own, inside its sandbox) under `gimp-smart-objects/`;
- the layers inside a smart object keep their names (not "<name> copy");
- Edit Contents (and a double click on a smart object, GIMPhoto's
  `patches/0007-…`) first shows Photoshop's notice on how to commit the
  changes, with "Don't show again" (remembered in the profile);
- attribution GIMPhoto and gimp-setup contributors;
- formatted with ruff and lint-clean for this repo's `scripts/check`
  (one-letter names renamed).
