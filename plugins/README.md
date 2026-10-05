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

## layer-style

Copied from gimp-setup (`assets/plug-ins/layer-style`, commit 8287f63),
then changed here:

- effects whose GEGL operations this GIMP does not have are shown greyed
  out, with what they need, instead of doing nothing. Gradient Overlay and
  Pattern Overlay use `lb:effects`, from LinuxBeaver's GEGL plug-ins, which a
  plain GIMP does not ship.

- effects are added with the selection set aside (and put back): GIMP
  crops a filter to the selection there is when it is added, so with a
  selection the effects showed only inside it, or not at all.

- formatted with ruff and lint-clean for this repo's `scripts/check`
  (an unused import, a long line and two one-letter names fixed).

Fixes that apply to both copies should be made in both.
