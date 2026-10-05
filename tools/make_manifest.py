#!/usr/bin/env python3
"""Generate GIMPhoto's Flatpak manifest from Flathub's GIMP manifest.

    tools/make_manifest.py            write flatpak/<APP_ID>.json
    tools/make_manifest.py --check    exit 1 if that file is out of date

Input:  flatpak/upstream/org.gimp.GIMP.json, vendored from
        https://github.com/flathub/org.gimp.GIMP (commit in
        flatpak/upstream/FLATHUB_COMMIT; refreshed by scripts/sync-flathub).
        patches/series, GIMPhoto's own changes to GIMP's source, in order.
Output: flatpak/io.github.diegochagas.GIMPhoto.json, committed so every
        build (local, CI, contributors) uses exactly the same recipe.

What changes against Flathub's recipe, and nothing else:
  - the app ID and the launcher name, so GIMPhoto installs next to the
    official GIMP instead of replacing it;
  - its own user profile (GIMP3_DIRECTORY), apart from the official GIMP's;
  - Flathub's own GIMP patch is read from flatpak/upstream/patches/;
  - GIMPhoto's patches are applied to GIMP's source after Flathub's;
  - one module after GIMP installs GIMPhoto's own plug-ins (plugins/<name>/)
    as system plug-ins, so the features that need them work out of the box;
  - one builds GIMPhoto's own GEGL operations (gegl/<name>.c, e.g.
    gimphoto:gradient-overlay) against the GEGL just built, into GEGL's
    plug-in folder;
  - one more installs GIMPhoto's default settings: defaults/shortcutsrc
    (made by tools/make_keymap.py) into GIMP's data folder, under gimphoto/;
    defaults/sessionrc and toolrc over GIMP's system ones, and
    defaults/gimprc appended to GIMP's system gimprc;
  - one installs GIMPhoto's icon and splash screen (branding/) over GIMP's,
    before Flathub's recipe renames the icon to the app ID;
  - one installs GIMPhoto's own tool icons (icons/*.svg) into GIMP's icon
    theme;
  - one installs GIMPhoto's GIMP themes (themes/<Name>/gimp.css) next to
    GIMP's Default theme.
The GIMP version, every library, the build options and the sandbox
permissions stay Flathub's.
"""

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = ROOT / "flatpak" / "upstream" / "org.gimp.GIMP.json"
SERIES = ROOT / "patches" / "series"
PLUGINS = ROOT / "plugins"
DEFAULTS = ROOT / "defaults"
GEGL_OPS = ROOT / "gegl"
# defaults/ files GIMPhoto's patches read from GIMP's data folder
DEFAULT_FILES = ["shortcutsrc"]
# defaults/ files that replace GIMP's system ones in /app/etc/gimp/3.0, read
# when the profile has none of its own (GIMP's own fallback, no patch)
SYSCONF_FILES = ["sessionrc", "toolrc"]
BRANDING = ROOT / "branding"
ICONS = ROOT / "icons"
THEMES = ROOT / "themes"
# the file names GIMP reads in a theme folder: one per colour scheme
# (dark, grey, light) and gimp.css as the fallback
THEME_FILES = ["gimp.css", "gimp-dark.css", "gimp-gray.css", "gimp-light.css"]
ICON_SIZES = [16, 22, 24, 32, 36, 48, 64, 72, 96, 128, 192, 256, 512]
APP_ID = "io.github.diegochagas.GIMPhoto"
APP_NAME = "GIMPhoto"
# GIMPhoto's own user profile, relative to the home folder (GIMP reads a
# relative GIMP3_DIRECTORY that way). Without it GIMP, inside any Flatpak,
# uses the host's ~/.config/GIMP/3.x, the official GIMP's profile with all
# its plug-ins, theme and shortcuts: GIMPhoto starts as plain GIMP instead,
# in Flatpak's per-app folder (removed by `flatpak uninstall --delete-data`).
# Not config/GIMP: Flathub's xdg-config/GIMP permission mounts the host's
# ~/.config/GIMP there inside the sandbox, so that "own" profile would be
# the host's ~/.config/GIMP, next to the official GIMP's.
PROFILE = f".var/app/{APP_ID}/config/GIMPhoto"
OUTPUT = ROOT / "flatpak" / f"{APP_ID}.json"


def read_series():
    """Patch file names from patches/series: one per line, # comments."""
    if not SERIES.exists():
        return []
    names = []
    for line in SERIES.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            if not (ROOT / "patches" / line).is_file():
                sys.exit(f"patches/series lists {line}, which is not in patches/")
            names.append(line)
    return names


def plugin_names():
    """Plug-in folders in plugins/: each holds <name>/<name>.py (GIMP's rule
    for plug-ins: the executable is named after its folder)."""
    if not PLUGINS.is_dir():
        return []
    names = sorted(p.name for p in PLUGINS.iterdir() if p.is_dir() and not p.name.startswith(("_", ".")))
    for name in names:
        main = PLUGINS / name / f"{name}.py"
        if not main.is_file():
            sys.exit(f"plugins/{name}/ has no {name}.py (GIMP runs the file named after the folder)")
    return names


def plugins_module(names):
    """flatpak-builder module installing plugins/<name>/ into GIMP's system
    plug-in folder: <name>.py executable, the other files beside it."""
    commands = []
    for name in names:
        dest = f"${{FLATPAK_DEST}}/lib/gimp/3.0/plug-ins/{name}"
        commands += [
            f"install -d {dest}",
            # files only: a __pycache__ folder left by a local run is skipped
            f"find {name} -maxdepth 1 -type f -exec install -m 644 -t {dest} {{}} +",
            f"chmod 755 {dest}/{name}.py",
        ]
    return {
        "name": "gimphoto-plug-ins",
        "buildsystem": "simple",
        "sources": [{"type": "dir", "path": "../plugins"}],
        "build-commands": commands,
    }


def gegl_op_names():
    """GEGL operation sources in gegl/: one shared module per <name>.c."""
    if not GEGL_OPS.is_dir():
        return []
    return sorted(p.stem for p in GEGL_OPS.glob("*.c"))


def gegl_ops_module(names):
    """flatpak-builder module compiling gegl/<name>.c into GEGL's plug-in
    folder, where GIMP's GEGL loads them (-I.: gegl-op.h includes the source
    by name)."""
    flags = "-shared -fPIC -O2 -Wall -I. -DGETTEXT_PACKAGE='\"gimphoto\"'"
    commands = [
        f"cc {flags} $(pkg-config --cflags gegl-0.4) -o {name}.so {name}.c $(pkg-config --libs gegl-0.4) -lm"
        for name in names
    ]
    commands.append("install -Dm 755 -t ${FLATPAK_DEST}/lib/gegl-0.4 " + " ".join(f"{n}.so" for n in names))
    return {
        "name": "gimphoto-gegl-ops",
        "buildsystem": "simple",
        "sources": [{"type": "dir", "path": "../gegl"}],
        "build-commands": commands,
    }


SYSCONF = "${FLATPAK_DEST}/etc/gimp/3.0"


def defaults_module():
    """flatpak-builder module installing defaults/ files GIMPhoto's patches
    read (gimp_data_directory_file ("gimphoto", ...))."""
    dest = "${FLATPAK_DEST}/share/gimp/3.0/gimphoto"
    return {
        "name": "gimphoto-defaults",
        "buildsystem": "simple",
        "sources": [{"type": "dir", "path": "../defaults"}],
        "build-commands": [
            f"install -Dm 644 -t {dest} {' '.join(DEFAULT_FILES)}",
            f"install -Dm 644 -t {SYSCONF} {' '.join(SYSCONF_FILES)}",
            # a new file: earlier modules' files cannot be changed in place
            f"cat {SYSCONF}/gimprc gimprc > gimprc.gimphoto",
            f"install -m 644 gimprc.gimphoto {SYSCONF}/gimprc",
        ],
    }


def branding_module():
    """flatpak-builder module putting branding/ over GIMP's own: the splash
    screen, and the icon as "gimp", which the recipe's rename-icon then
    installs under the app ID for the launcher."""
    icons = "${FLATPAK_DEST}/share/icons/hicolor"
    return {
        "name": "gimphoto-branding",
        "buildsystem": "simple",
        "sources": [{"type": "dir", "path": "../branding"}],
        "build-commands": [
            "install -Dm 644 splash.png ${FLATPAK_DEST}/share/gimp/3.0/images/gimp-splash.png",
            *(f"install -Dm 644 icons/{n}.png {icons}/{n}x{n}/apps/gimp.png" for n in ICON_SIZES),
            f"install -Dm 644 icon.svg {icons}/scalable/apps/gimp.svg",
        ],
    }


def icons_module():
    """flatpak-builder module installing icons/*.svg (GIMPhoto's tool icons,
    e.g. the shape tools') into GIMP's Default icon theme, which has no
    icon cache, and into hicolor as a fallback for the other themes."""
    return {
        "name": "gimphoto-icons",
        "buildsystem": "simple",
        "sources": [{"type": "dir", "path": "../icons"}],
        "build-commands": [
            "install -Dm 644 -t ${FLATPAK_DEST}/share/gimp/3.0/icons/Default/scalable/apps *.svg",
            "install -Dm 644 -t ${FLATPAK_DEST}/share/icons/hicolor/scalable/apps *.svg",
        ],
    }


def theme_names():
    """Theme folders in themes/, each with its gimp.css."""
    if not THEMES.is_dir():
        return []
    names = sorted(p.name for p in THEMES.iterdir() if p.is_dir())
    for name in names:
        if not (THEMES / name / "gimp.css").is_file():
            sys.exit(f"themes/{name}/ has no gimp.css")
    return names


def themes_module(names):
    """flatpak-builder module installing themes/<Name>/gimp.css as a GIMP
    theme in GIMP's data folder, the same file for every colour scheme so
    the theme looks the same whichever scheme Preferences has."""
    commands = []
    for name in names:
        dest = f"${{FLATPAK_DEST}}/share/gimp/3.0/themes/{name}"
        commands += [f"install -Dm 644 {name}/gimp.css {dest}/{file}" for file in THEME_FILES]
    return {
        "name": "gimphoto-themes",
        "buildsystem": "simple",
        "sources": [{"type": "dir", "path": "../themes"}],
        "build-commands": commands,
    }


def transform(manifest, series, plugins=(), defaults=False, gegl_ops=(), branding=False, icons=False, themes=()):
    m = copy.deepcopy(manifest)
    m["app-id"] = APP_ID
    m["finish-args"] = [*m["finish-args"], f"--env=GIMP3_DIRECTORY={PROFILE}"]
    # Flathub renames the desktop file, icon and AppStream file to the app
    # ID; flatpak-builder does the same with ours.
    gimp = next((mod for mod in m["modules"] if isinstance(mod, dict) and mod.get("name") == "gimp"), None)
    if gimp is None:
        sys.exit("Flathub's manifest has no 'gimp' module: the generator needs updating")
    for source in gimp["sources"]:
        if isinstance(source, dict) and source.get("type") == "patch":
            source["paths"] = [f"upstream/{p}" for p in source["paths"]]
    if series:
        gimp["sources"].append(
            {"type": "patch", "use-git-am": True, "paths": [f"../patches/{name}" for name in series]}
        )
    if plugins:
        m["modules"].append(plugins_module(plugins))
    if gegl_ops:
        m["modules"].append(gegl_ops_module(gegl_ops))
    if defaults:
        m["modules"].append(defaults_module())
    if branding:
        m["modules"].append(branding_module())
    if icons:
        m["modules"].append(icons_module())
    if themes:
        m["modules"].append(themes_module(themes))
    # The launcher says GIMPhoto, so it can be told apart from GIMP.
    gimp.setdefault("post-install", []).append(
        "desktop-file-edit --set-name=" + APP_NAME + " ${FLATPAK_DEST}/share/applications/gimp.desktop"
    )
    return m


def render():
    manifest = json.loads(UPSTREAM.read_text())
    header = {
        "//": "GENERATED by tools/make_manifest.py from flatpak/upstream/org.gimp.GIMP.json "
        "and patches/series. Do not edit by hand."
    }
    out = transform(
        manifest,
        read_series(),
        plugin_names(),
        DEFAULTS.is_dir(),
        gegl_op_names(),
        BRANDING.is_dir(),
        ICONS.is_dir(),
        theme_names(),
    )
    return json.dumps({**header, **out}, indent=4) + "\n"


def main():
    text = render()
    if "--check" in sys.argv[1:]:
        if not OUTPUT.exists() or OUTPUT.read_text() != text:
            print(f"{OUTPUT.relative_to(ROOT)} is out of date: run tools/make_manifest.py", file=sys.stderr)
            return 1
        return 0
    OUTPUT.write_text(text)
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
