"""The comfyui-service plug-in's decisions: when to start the local ComfyUI,
where it listens, what the AI tools are told. No GIMP and no D-Bus: the
plug-in makes the calls, these are plain functions."""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugins" / "comfyui-service"))
import comfyui_service as cs  # noqa: E402

# systemd's ExecStart as D-Bus unpacks it: (path, argv, ignore failure, ...)
PYTHON = "/opt/ComfyUI/.venv/bin/python"


def exec_start(*argv):
    return [(PYTHON, [PYTHON, *argv], False, 0, 0, 0, 0, 0, 0, 0)]


class PortTest(unittest.TestCase):
    def test_port_from_linux_mint_setups_unit(self):
        self.assertEqual(
            cs.port_from_exec_start(exec_start("main.py", "--listen", "127.0.0.1", "--port", "8190")), 8190
        )

    def test_port_with_equals_sign(self):
        self.assertEqual(cs.port_from_exec_start(exec_start("main.py", "--port=9000")), 9000)

    def test_default_port_without_one(self):
        self.assertEqual(cs.port_from_exec_start(exec_start("main.py")), 8188)
        self.assertEqual(cs.port_from_exec_start([]), 8188)
        self.assertEqual(cs.port_from_exec_start(None), 8188)

    def test_a_trailing_or_bad_port_is_ignored(self):
        self.assertEqual(cs.port_from_exec_start(exec_start("main.py", "--port")), 8188)
        self.assertEqual(cs.port_from_exec_start(exec_start("main.py", "--port", "http")), 8188)


class StartTest(unittest.TestCase):
    def test_starts_an_installed_stopped_service(self):
        self.assertTrue(cs.should_start("loaded", "inactive"))
        self.assertTrue(cs.should_start("loaded", "failed"))

    def test_leaves_a_running_service_alone(self):
        # started by hand, a script or GIMP's launcher: not ours to stop
        for state in ("active", "activating", "reloading"):
            self.assertFalse(cs.should_start("loaded", state), state)

    def test_never_starts_a_missing_service(self):
        self.assertFalse(cs.should_start("not-found", "inactive"))


class DescribeTest(unittest.TestCase):
    def test_missing_points_to_the_installer(self):
        info = cs.describe("not-found", "inactive", False, 8188)
        self.assertEqual(info["state"], "missing")
        self.assertIn("linux-mint-setup", info["install"])
        self.assertNotIn("url", info)

    def test_started_by_gimphoto(self):
        self.assertEqual(
            cs.describe("loaded", "inactive", True, 8190),
            {"state": "started", "url": "http://127.0.0.1:8190", "active": "inactive"},
        )

    def test_already_running(self):
        self.assertEqual(cs.describe("loaded", "active", False, 8188)["state"], "running")


if __name__ == "__main__":
    unittest.main()
