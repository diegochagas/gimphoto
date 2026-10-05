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
        for key in keys - {"app-id", "modules", "finish-args"}:
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
            module["build-commands"], ["install -Dm 644 -t ${FLATPAK_DEST}/share/gimp/3.0/gimphoto shortcutsrc"]
        )

    def test_every_default_file_exists(self):
        for name in make_manifest.DEFAULT_FILES:
            self.assertTrue((make_manifest.DEFAULTS / name).is_file(), name)

    def test_every_plugin_folder_has_its_executable(self):
        for name in make_manifest.plugin_names():
            self.assertTrue((ROOT / "plugins" / name / f"{name}.py").is_file(), name)

    def test_sandbox_is_flathubs_plus_only_the_own_profile(self):
        self.assertEqual(self.out["finish-args"][:-1], UPSTREAM["finish-args"])
        self.assertEqual(
            self.out["finish-args"][-1], "--env=GIMP3_DIRECTORY=.var/app/io.github.diegochagas.GIMPhoto/config/GIMPhoto"
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
