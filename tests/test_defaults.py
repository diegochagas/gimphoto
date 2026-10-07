"""GIMPhoto's default layout reaches existing profiles only when its version
goes up (patch "Default layout updates reach existing profiles"), so every
change to defaults/sessionrc must come with a new version.

When this test fails after a layout change: raise the number in the
"# gimphoto-layout-version N" line of defaults/sessionrc and add
N: "<the hash the failure prints>" to LAYOUTS below."""

import hashlib
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SESSIONRC = ROOT / "defaults" / "sessionrc"

# layout version -> SHA-256 of the layout (the file without its comments)
LAYOUTS = {
    1: "c70cd755570ccac55aa5a564ca3e986815b6b0a07ee25706db7cdcaa4c0c6951",
}


def layout():
    text = SESSIONRC.read_text()
    match = re.search(r"^# gimphoto-layout-version (\d+)$", text, re.M)
    body = re.sub(r"^#.*\n", "", text, flags=re.M)
    return (int(match.group(1)) if match else None), hashlib.sha256(body.encode()).hexdigest()


class LayoutVersionTest(unittest.TestCase):
    def test_sessionrc_has_a_layout_version(self):
        version, _digest = layout()
        self.assertIsNotNone(version, "defaults/sessionrc needs a '# gimphoto-layout-version N' line")
        self.assertGreater(version, 0)

    def test_one_version_line(self):
        # GIMP reads the first line of this form (patch 0009): two would be
        # ambiguous
        lines = re.findall(r"^# gimphoto-layout-version \d+$", SESSIONRC.read_text(), re.M)
        self.assertEqual(len(lines), 1, lines)

    def test_the_version_is_the_newest_known(self):
        version, _digest = layout()
        self.assertEqual(version, max(LAYOUTS), "the layout version only goes up")

    def test_a_layout_change_raises_the_version(self):
        version, digest = layout()
        self.assertEqual(
            LAYOUTS.get(version),
            digest,
            f"defaults/sessionrc changed without a new layout version: raise it and add {digest!r} to LAYOUTS",
        )


if __name__ == "__main__":
    unittest.main()
