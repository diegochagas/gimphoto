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
        for key in keys - {"app-id", "modules"}:
            self.assertEqual(self.out.get(key), UPSTREAM.get(key), key)
        for theirs, ours in zip(UPSTREAM["modules"], self.out["modules"]):
            if isinstance(theirs, dict) and theirs.get("name") == "gimp":
                continue
            self.assertEqual(ours, theirs)
        self.assertEqual(len(self.out["modules"]), len(UPSTREAM["modules"]))

    def test_sandbox_permissions_are_flathubs(self):
        self.assertEqual(self.out["finish-args"], UPSTREAM["finish-args"])

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
