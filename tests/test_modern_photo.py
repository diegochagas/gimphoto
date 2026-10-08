"""Modern Photo's prompt and black-and-white check
(plugins/photo-restoration/modern_photo.py): no network, no GIMP."""

import pathlib
import struct
import sys
import unittest
import zlib
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugins" / "comfyui-service"))
sys.path.insert(0, str(ROOT / "plugins" / "photo-restoration"))
import modern_photo  # noqa: E402

URL = "http://127.0.0.1:8188"


def pixels(colours, n=64 * 64):
    """n RGB pixels cycling through `colours`."""
    return bytes(c for i in range(n) for c in colours[i % len(colours)])


def png(width, height):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    raw = b"".join(b"\0" + bytes(width * 3) for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


class MonochromeTest(unittest.TestCase):
    def test_greys_are_monochrome(self):
        self.assertTrue(modern_photo.is_monochrome(pixels([(v, v, v) for v in range(0, 256, 8)])))

    def test_sepia_is_monochrome(self):
        # one brown tint, darker and lighter: a toned print
        sepia = [(min(255, int(v * 1.05) + 10), v, int(v * 0.9)) for v in range(20, 230, 10)]
        self.assertTrue(modern_photo.is_monochrome(pixels(sepia)))

    def test_faded_colours_are_not(self):
        # a yellowed print that still has a red car, blue sea and pale sand
        faded = [(200, 120, 100), (150, 170, 190), (220, 210, 160), (190, 180, 140)]
        self.assertFalse(modern_photo.is_monochrome(pixels(faded)))

    def test_no_pixels(self):
        self.assertTrue(modern_photo.is_monochrome(b""))


class PromptTest(unittest.TestCase):
    def test_colour_photo_stays_as_it_is(self):
        for keep in (False, True):
            self.assertEqual(modern_photo.prompt(False, keep), modern_photo.PROMPT)

    def test_black_and_white(self):
        self.assertTrue(modern_photo.prompt(True, False).endswith(modern_photo.COLORIZE))
        self.assertTrue(modern_photo.prompt(True, True).endswith(modern_photo.KEEP_BW))

    def test_people_are_kept(self):
        self.assertIn("same face", modern_photo.PROMPT)
        self.assertIn("framing", modern_photo.PROMPT)


class ModernizeTest(unittest.TestCase):
    def test_whole_image_edit_at_the_photos_size(self):
        client = modern_photo.client
        with (
            mock.patch.object(client, "_upload", return_value="modern.png") as upload,
            mock.patch.object(client, "_edit_graph", return_value={"g": 1}) as edit,
            mock.patch.object(client, "_run", return_value={"out": b"result"}) as run,
        ):
            out = modern_photo.modernize("klein", png(800, 600), True, False, URL)
        self.assertEqual(out, b"result")
        self.assertEqual(upload.call_args.args[0], URL)
        args = edit.call_args.args
        self.assertEqual(args[:3], (URL, "klein", "modern.png"))
        self.assertTrue(args[3].endswith(modern_photo.COLORIZE))
        self.assertEqual(args[4:6], client.work_size(800, 600))
        self.assertEqual(args[6:], (800, 600))
        self.assertEqual(run.call_args.args[:2], (URL, {"g": 1}))


if __name__ == "__main__":
    unittest.main()
