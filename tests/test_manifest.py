"""tools/make_manifest.py: GIMPhoto's recipe is Flathub's plus only the
documented changes (app ID, launcher name, patch paths, GIMPhoto patches)."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import make_manifest  # noqa: E402
import upstream_info  # noqa: E402

UPSTREAM = json.loads((ROOT / "flatpak" / "upstream" / "org.gimp.GIMP.json").read_text())


def gimp(manifest):
    return upstream_info.gimp_module(manifest)


class TransformTest(unittest.TestCase):
    def setUp(self):
        self.out = make_manifest.transform(UPSTREAM, [])

    def test_app_id_is_gimphoto(self):
        self.assertEqual(self.out["app-id"], "io.github.diegochagas.GIMPhoto")

    def test_input_is_not_modified(self):
        before = copy.deepcopy(UPSTREAM)
        make_manifest.transform(UPSTREAM, ["0001-x.patch"])
        self.assertEqual(UPSTREAM, before)

    def test_everything_but_the_gimp_module_and_app_id_is_flathubs(self):
        keys = set(UPSTREAM) | set(self.out)
        # sdk-extensions: Flathub's Node, added for plug-ins with npm packages
        for key in keys - {"app-id", "modules", "finish-args", "sdk-extensions"}:
            self.assertEqual(self.out.get(key), UPSTREAM.get(key), key)
        for theirs, ours in zip(UPSTREAM["modules"], self.out["modules"]):
            if isinstance(theirs, dict) and theirs.get("name") == "gimp":
                continue
            self.assertEqual(ours, theirs)
        self.assertEqual(len(self.out["modules"]), len(UPSTREAM["modules"]))

    def test_plugins_module_comes_last_and_installs_each_plugin(self):
        out = make_manifest.transform(UPSTREAM, [], ["layer-style"])
        self.assertEqual(out["modules"][:-1], make_manifest.transform(UPSTREAM, [])["modules"])
        module = out["modules"][-1]
        self.assertEqual(module["name"], "gimphoto-plug-ins")
        self.assertEqual(module["sources"], [{"type": "dir", "path": "../plugins"}])
        dest = "${FLATPAK_DEST}/lib/gimp/3.0/plug-ins/layer-style"
        self.assertIn(f"chmod 755 {dest}/layer-style.py", module["build-commands"])

    def test_defaults_module_comes_last_and_installs_into_gimps_data_folder(self):
        out = make_manifest.transform(UPSTREAM, [], ["layer-style"], defaults=True)
        self.assertEqual(out["modules"][:-1], make_manifest.transform(UPSTREAM, [], ["layer-style"])["modules"])
        module = out["modules"][-1]
        self.assertEqual(module["name"], "gimphoto-defaults")
        self.assertEqual(module["sources"], [{"type": "dir", "path": "../defaults"}])
        # gimp_data_directory_file ("gimphoto", "shortcutsrc") in patch 0002
        self.assertEqual(
            module["build-commands"],
            [
                "install -Dm 644 -t ${FLATPAK_DEST}/share/gimp/3.0/gimphoto shortcutsrc",
                "install -Dm 644 -t ${FLATPAK_DEST}/etc/gimp/3.0 sessionrc toolrc",
                "cat ${FLATPAK_DEST}/etc/gimp/3.0/gimprc gimprc > gimprc.gimphoto",
                "install -m 644 gimprc.gimphoto ${FLATPAK_DEST}/etc/gimp/3.0/gimprc",
            ],
        )

    def test_branding_replaces_gimps_splash_and_icon_before_the_rename(self):
        out = make_manifest.transform(UPSTREAM, [], branding=True)
        module = out["modules"][-1]
        self.assertEqual(module["name"], "gimphoto-branding")
        commands = module["build-commands"]
        self.assertIn("install -Dm 644 splash.png ${FLATPAK_DEST}/share/gimp/3.0/images/gimp-splash.png", commands)
        # the recipe renames the "gimp" icon to the app ID
        self.assertEqual(UPSTREAM["rename-icon"], "gimp")
        self.assertIn("install -Dm 644 icon.svg ${FLATPAK_DEST}/share/icons/hicolor/scalable/apps/gimp.svg", commands)
        for n in make_manifest.ICON_SIZES:
            self.assertIn(
                f"install -Dm 644 icons/{n}.png ${{FLATPAK_DEST}}/share/icons/hicolor/{n}x{n}/apps/gimp.png", commands
            )

    def test_icons_go_into_gimps_icon_theme(self):
        module = make_manifest.transform(UPSTREAM, [], icons=True)["modules"][-1]
        self.assertEqual(module["name"], "gimphoto-icons")
        self.assertIn(
            "install -Dm 644 -t ${FLATPAK_DEST}/share/gimp/3.0/icons/Default/scalable/apps *.svg",
            module["build-commands"],
        )

    def test_themes_install_one_file_per_colour_scheme(self):
        module = make_manifest.transform(UPSTREAM, [], themes=["Photoshop"])["modules"][-1]
        self.assertEqual(module["name"], "gimphoto-themes")
        dest = "${FLATPAK_DEST}/share/gimp/3.0/themes/Photoshop"
        for file in ("gimp.css", "gimp-dark.css", "gimp-gray.css", "gimp-light.css"):
            self.assertIn(f"install -Dm 644 Photoshop/gimp.css {dest}/{file}", module["build-commands"])

    def test_themes_import_gimps_default_theme_by_a_relative_path(self):
        # installed next to Default; no machine path, no placeholder
        for name in make_manifest.theme_names():
            css = (make_manifest.THEMES / name / "gimp.css").read_text()
            self.assertIn('@import url("../Default/', css)
            self.assertNotIn("file://", css)

    def test_every_icon_has_its_symbolic_variant(self):
        # GIMP's dark theme asks for <name>-symbolic
        names = {p.name for p in make_manifest.ICONS.glob("*.svg")}
        for name in names:
            if not name.endswith("-symbolic.svg"):
                self.assertIn(name.replace(".svg", "-symbolic.svg"), names)

    def test_every_icon_is_recognised_as_svg(self):
        # shared-mime-info looks for "<svg" in the first 256 bytes only:
        # past them, GTK cannot load the icon and GIMP shows Wilber instead
        for path in make_manifest.ICONS.glob("*.svg"):
            self.assertIn("<svg", path.read_bytes()[:256].decode(errors="replace"), path.name)

    def test_symbolic_icons_have_no_strokes(self):
        # GTK fills every shape of a symbolic icon: a stroked outline
        # (fill="none") becomes a solid shape
        for path in make_manifest.ICONS.glob("*-symbolic.svg"):
            self.assertNotIn("stroke", path.read_text().split("-->")[-1], path.name)

    def test_branding_and_default_files_exist(self):
        for name in make_manifest.SYSCONF_FILES + ["gimprc"]:
            self.assertTrue((make_manifest.DEFAULTS / name).is_file(), name)
        for name in ["splash.png", "icon.svg", *(f"icons/{n}.png" for n in make_manifest.ICON_SIZES)]:
            self.assertTrue((make_manifest.BRANDING / name).is_file(), name)

    def test_gegl_ops_module_builds_each_operation_into_gegls_plugin_folder(self):
        out = make_manifest.transform(UPSTREAM, [], [], gegl_ops=["a-op.c", "b-op.c"])
        module = out["modules"][-1]
        self.assertEqual(module["name"], "gimphoto-gegl-ops")
        self.assertEqual(module["sources"], [{"type": "dir", "path": "../gegl"}])
        commands = module["build-commands"]
        self.assertIn("-o a-op.so a-op.c", commands[1])
        self.assertIn("-o b-op.so b-op.c", commands[2])
        self.assertEqual(commands[-1], "install -Dm 755 -t ${FLATPAK_DEST}/lib/gegl-0.4 a-op.so b-op.so")

    def test_gegl_ops_in_cplusplus_link_maxflow(self):
        # GEGL's paint-select (Quick Selection) is C++ on the maxflow graph
        # cut library, which Flathub's recipe builds before GEGL
        out = make_manifest.transform(UPSTREAM, [], [], gegl_ops=["paint-select.cc"])
        commands = out["modules"][-1]["build-commands"]
        self.assertEqual(commands[0], "touch config.h")  # GEGL's sources include it
        self.assertTrue(commands[1].startswith("c++ "))
        self.assertIn("-o paint-select.so paint-select.cc", commands[1])
        self.assertIn("maxflow", commands[1])
        names = [m.get("name") for m in out["modules"] if isinstance(m, dict)]
        self.assertGreater(names.index("gimphoto-gegl-ops"), names.index("maxflow"))

    def test_gegl_ops_are_the_c_and_cplusplus_files(self):
        self.assertIn("gradient-overlay.c", make_manifest.gegl_ops())
        self.assertIn("paint-select.cc", make_manifest.gegl_ops())

    def test_gegl_ops_come_after_gegl_and_gimp(self):
        out = make_manifest.transform(UPSTREAM, [], [], gegl_ops=["a-op.c"])
        names = [m.get("name") for m in out["modules"] if isinstance(m, dict)]
        self.assertGreater(names.index("gimphoto-gegl-ops"), names.index("gegl"))
        self.assertGreater(names.index("gimphoto-gegl-ops"), names.index("gimp"))

    def test_every_default_file_exists(self):
        for name in make_manifest.DEFAULT_FILES:
            self.assertTrue((make_manifest.DEFAULTS / name).is_file(), name)

    def test_node_only_for_plugins_with_a_lockfile(self):
        self.assertEqual(make_manifest.node_plugins(["layer-style"]), [])
        self.assertEqual(make_manifest.node_plugins(["layer-style", "psd-text"]), ["psd-text"])
        out = make_manifest.transform(UPSTREAM, [], ["layer-style"])
        self.assertNotIn("sdk-extensions", out)
        self.assertNotIn("gimphoto-node", [m.get("name") for m in out["modules"] if isinstance(m, dict)])

    def test_node_plugins_get_flathubs_node_copied_into_the_app(self):
        out = make_manifest.transform(UPSTREAM, [], ["psd-text"])
        self.assertEqual(out["sdk-extensions"], [*UPSTREAM.get("sdk-extensions", []), make_manifest.NODE_EXTENSION])
        names = [m.get("name") for m in out["modules"] if isinstance(m, dict)]
        # after the plug-ins, whose folder the npm packages go into
        self.assertEqual(names[names.index("gimphoto-plug-ins") + 1 :][:2], ["gimphoto-node", "gimphoto-psd-text-npm"])
        node = next(m for m in out["modules"] if isinstance(m, dict) and m.get("name") == "gimphoto-node")
        self.assertIn(
            "install -Dm 755 /usr/lib/sdk/node24/bin/node ${FLATPAK_DEST}/lib/gimphoto/node/bin/node",
            node["build-commands"],
        )

    def test_npm_packages_come_from_the_lockfile_checked(self):
        lock = {
            "packages": {
                "": {},
                "node_modules/pako": {
                    "version": "2.1.0",
                    "resolved": "https://registry.npmjs.org/pako/-/pako-2.1.0.tgz",
                    "integrity": "sha512-AAEC",
                },
                "node_modules/a/node_modules/b": {"version": "1", "resolved": "x", "integrity": "sha512-AA=="},
            }
        }
        module = make_manifest.npm_module("psd-text", lock)
        self.assertEqual(
            module["sources"],
            [
                {
                    "type": "file",
                    "url": "https://registry.npmjs.org/pako/-/pako-2.1.0.tgz",
                    "sha512": "000102",
                    "dest-filename": "pako-2.1.0.tgz",
                }
            ],
        )
        dest = "${FLATPAK_DEST}/lib/gimp/3.0/plug-ins/psd-text/node_modules/pako"
        self.assertEqual(
            module["build-commands"], [f"mkdir -p {dest}", f"tar -xzf pako-2.1.0.tgz -C {dest} --strip-components=1"]
        )

    def test_psd_text_lockfile_is_fully_pinned(self):
        lock = json.loads((ROOT / "plugins" / "psd-text" / "package-lock.json").read_text())
        packages = [k for k in lock["packages"] if k.startswith("node_modules/")]
        self.assertIn("node_modules/ag-psd", packages)
        for path in packages:
            self.assertTrue(lock["packages"][path]["integrity"].startswith("sha512-"), path)

    def test_every_plugin_folder_has_its_executable(self):
        for name in make_manifest.plugin_names():
            self.assertTrue((ROOT / "plugins" / name / f"{name}.py").is_file(), name)

    def test_sandbox_is_flathubs_plus_only_the_own_profile_and_systemd(self):
        # the own profile, and the user's systemd on the session bus, to
        # start and stop the local ComfyUI service (comfyui-service plug-in)
        self.assertEqual(self.out["finish-args"][:-2], UPSTREAM["finish-args"])
        self.assertEqual(
            self.out["finish-args"][-2:],
            [
                "--env=GIMP3_DIRECTORY=.var/app/io.github.diegochagas.GIMPhoto/config/GIMPhoto",
                "--talk-name=org.freedesktop.systemd1",
            ],
        )

    def test_profile_is_not_under_a_mounted_config_folder(self):
        # Flathub's xdg-config/<dir> permissions mount the host's
        # ~/.config/<dir> over ~/.var/app/<id>/config/<dir> in the sandbox
        mounted = [
            a.split("=", 1)[1].split(":")[0].removeprefix("xdg-config/")
            for a in UPSTREAM["finish-args"]
            if a.startswith("--filesystem=xdg-config/")
        ]
        self.assertIn("GIMP", mounted)
        top = make_manifest.PROFILE.removeprefix(f".var/app/{make_manifest.APP_ID}/config/").split("/")[0]
        self.assertNotIn(top, mounted)

    def test_profile_is_relative_to_home_and_per_app(self):
        # GIMP reads a relative GIMP3_DIRECTORY from the home folder; an
        # absolute one would carry one machine's home path into the build
        self.assertFalse(make_manifest.PROFILE.startswith("/"))
        self.assertIn(make_manifest.APP_ID, make_manifest.PROFILE)

    def test_gimp_source_is_flathubs_pinned_commit(self):
        ours = next(s for s in gimp(self.out)["sources"] if s.get("type") == "git")
        theirs = next(s for s in gimp(UPSTREAM)["sources"] if s.get("type") == "git")
        self.assertEqual(ours, theirs)

    def test_flathub_patches_are_read_from_upstream_dir(self):
        paths = [p for s in gimp(self.out)["sources"] if s.get("type") == "patch" for p in s["paths"]]
        self.assertTrue(paths)
        for p in paths:
            self.assertTrue(p.startswith("upstream/"), p)
            self.assertTrue((ROOT / "flatpak" / p).is_file(), p)

    def test_no_gimphoto_patch_source_without_a_series(self):
        patch_sources = [s for s in gimp(self.out)["sources"] if s.get("type") == "patch"]
        self.assertEqual(len(patch_sources), len([s for s in gimp(UPSTREAM)["sources"] if s.get("type") == "patch"]))

    def test_gimphoto_patches_come_last_in_order(self):
        out = make_manifest.transform(UPSTREAM, ["0001-a.patch", "0002-b.patch"])
        last = gimp(out)["sources"][-1]
        self.assertEqual(last["type"], "patch")
        self.assertTrue(last["use-git-am"])
        self.assertEqual(last["paths"], ["../patches/0001-a.patch", "../patches/0002-b.patch"])

    def test_launcher_is_named_gimphoto(self):
        commands = gimp(self.out)["post-install"]
        self.assertIn("desktop-file-edit --set-name=GIMPhoto ${FLATPAK_DEST}/share/applications/gimp.desktop", commands)
        # Flathub's own post-install steps are kept, before ours
        self.assertEqual(commands[:-1], gimp(UPSTREAM).get("post-install", []))


class SeriesTest(unittest.TestCase):
    def read(self, text, files=()):
        with tempfile.TemporaryDirectory() as tmp:
            patches = Path(tmp) / "patches"
            patches.mkdir()
            (patches / "series").write_text(text)
            for name in files:
                (patches / name).write_text("")
            with (
                mock.patch.object(make_manifest, "ROOT", Path(tmp)),
                mock.patch.object(make_manifest, "SERIES", patches / "series"),
            ):
                return make_manifest.read_series()

    def test_comments_and_blank_lines_are_ignored(self):
        self.assertEqual(
            self.read("# head\n\n0001-a.patch  # first\n0002-b.patch\n", ["0001-a.patch", "0002-b.patch"]),
            ["0001-a.patch", "0002-b.patch"],
        )

    def test_a_listed_patch_that_does_not_exist_is_an_error(self):
        with self.assertRaises(SystemExit):
            self.read("0001-missing.patch\n")


class CommittedManifestTest(unittest.TestCase):
    def test_committed_manifest_matches_the_generator(self):
        path = ROOT / "flatpak" / f"{make_manifest.APP_ID}.json"
        self.assertEqual(path.read_text(), make_manifest.render(), "run tools/make_manifest.py and commit the result")


class UpstreamInfoTest(unittest.TestCase):
    def test_gimp_version_comes_from_the_tag(self):
        git = next(s for s in gimp(UPSTREAM)["sources"] if s.get("type") == "git")
        version = git["tag"].removeprefix("GIMP_").replace("_", ".")
        self.assertRegex(version, r"^\d+\.\d+\.\d+")


if __name__ == "__main__":
    unittest.main()
