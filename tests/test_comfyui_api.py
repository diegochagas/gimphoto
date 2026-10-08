"""GIMPhoto's ComfyUI client (plugins/comfyui-service/comfyui_api.py) against
a fake ComfyUI: no network, no GIMP."""

import io
import json
import pathlib
import sys
import unittest
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugins" / "comfyui-service"))
import comfyui_api as api  # noqa: E402

URL = "http://127.0.0.1:8188"


class FakeComfyUI:
    """Answers urlopen like ComfyUI's HTTP API; records the requests."""

    def __init__(self, nodes=("Sam2Segmentation", "BBoxFromJSON"), up_after=0, history=None):
        self.nodes = set(nodes)
        self.calls_until_up = up_after
        self.requests = []
        self.history = history or [
            {},
            {"p1": {"status": {"completed": True}, "outputs": {"out": {"images": [{"filename": "m.png"}]}}}},
        ]

    def __call__(self, req, timeout=None):
        path = req.full_url[len(URL) :]
        self.requests.append((path, req.data))
        if path == "/system_stats":
            if self.calls_until_up > 0:
                self.calls_until_up -= 1
                raise urllib.error.URLError("refused")
            return io.BytesIO(b"{}")
        if path.startswith("/object_info/"):
            node = path.split("/")[-1]
            if node not in self.nodes:
                raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, io.BytesIO(b""))
            return io.BytesIO(json.dumps({node: {}}).encode())
        if path == "/upload/image":
            return io.BytesIO(json.dumps({"name": "select.png", "subfolder": "gimphoto"}).encode())
        if path == "/prompt":
            return io.BytesIO(json.dumps({"prompt_id": "p1", "node_errors": {}}).encode())
        if path.startswith("/history/"):
            return io.BytesIO(json.dumps(self.history.pop(0) if self.history else {}).encode())
        if path.startswith("/view?"):
            return io.BytesIO(b"MASKPNG")
        raise AssertionError(path)


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.saved = api.urlopen, api.sleep
        api.sleep = lambda s: None

    def tearDown(self):
        api.urlopen, api.sleep = self.saved

    def test_segment_uploads_runs_and_returns_the_mask(self):
        fake = api.urlopen = FakeComfyUI()
        self.assertEqual(api.segment(URL, b"PNG", [[0, 0, 640, 420]]), b"MASKPNG")
        prompt = json.loads(dict(fake.requests)["/prompt"])["prompt"]
        self.assertEqual(prompt["img"]["inputs"]["image"], "gimphoto/select.png")
        self.assertEqual(json.loads(prompt["box"]["inputs"]["boxes"]), [[0, 0, 640, 420]])
        self.assertEqual(prompt["box"]["class_type"], "BBoxFromJSON")
        self.assertEqual(prompt["seg"]["inputs"]["bboxes"], ["box", 0])
        self.assertIn(b'name="subfolder"\r\n\r\ngimphoto', dict(fake.requests)["/upload/image"])

    def test_subject_runs_birefnet_on_the_uploaded_image(self):
        fake = api.urlopen = FakeComfyUI(nodes=("LoadRembgByBiRefNetModel", "GetMaskByBiRefNet"))
        self.assertEqual(api.subject(URL, b"PNG"), b"MASKPNG")
        prompt = json.loads(dict(fake.requests)["/prompt"])["prompt"]
        self.assertEqual(prompt["img"]["inputs"]["image"], "gimphoto/select.png")
        self.assertEqual(prompt["net"]["inputs"]["model"], "General.safetensors")
        self.assertEqual(prompt["mask"]["inputs"]["images"], ["img", 0])
        self.assertEqual(prompt["mask"]["inputs"]["mask_threshold"], 0.0)  # soft edges kept
        self.assertEqual(prompt["m2i"]["inputs"]["mask"], ["mask", 0])

    def test_subject_without_birefnet_says_how_to_install_it(self):
        api.urlopen = FakeComfyUI(nodes=("Sam2Segmentation", "BBoxFromJSON"))
        with self.assertRaises(api.ComfyUIError) as caught:
            api.subject(URL, b"PNG")
        self.assertIn("LoadRembgByBiRefNetModel", str(caught.exception))
        self.assertIn("local-ai-setup", str(caught.exception))

    def test_a_missing_node_says_how_to_install_it(self):
        api.urlopen = FakeComfyUI(nodes=("Sam2Segmentation",))
        with self.assertRaises(api.ComfyUIError) as caught:
            api.segment(URL, b"PNG", [[0, 0, 10, 10]])
        self.assertIn("BBoxFromJSON", str(caught.exception))
        self.assertIn("local-ai-setup", str(caught.exception))

    def test_waits_for_a_booting_comfyui(self):
        fake = api.urlopen = FakeComfyUI(up_after=3)
        self.assertTrue(api.wait_until_up(URL, waited=60))
        self.assertEqual([p for p, _ in fake.requests].count("/system_stats"), 4)

    def test_gives_up_when_it_never_answers(self):
        api.urlopen = FakeComfyUI(up_after=10**6)
        self.assertFalse(api.wait_until_up(URL, waited=0))

    def test_a_failed_run_reports_the_node_error(self):
        api.urlopen = FakeComfyUI(
            history=[
                {
                    "p1": {
                        "status": {
                            "status_str": "error",
                            "messages": [
                                ["execution_error", {"node_type": "Sam2Segmentation", "exception_message": "CUDA OOM"}]
                            ],
                        }
                    }
                }
            ]
        )
        with self.assertRaises(api.ComfyUIError) as caught:
            api.segment(URL, b"PNG", [[0, 0, 10, 10]])
        self.assertIn("CUDA OOM", str(caught.exception))

    def test_remove_runs_lama_on_the_image_and_its_mask(self):
        fake = api.urlopen = FakeComfyUI(nodes=("INPAINT_LoadInpaintModel", "INPAINT_InpaintWithModel"))
        self.assertEqual(api.remove(URL, b"IMAGE", b"MASK"), b"MASKPNG")
        uploads = [data for path, data in fake.requests if path == "/upload/image"]
        self.assertEqual(len(uploads), 2)  # the image, then the mask
        prompt = json.loads(dict(fake.requests)["/prompt"])["prompt"]
        self.assertEqual(prompt["lama"]["inputs"]["model_name"], "big-lama.pt")
        self.assertEqual(prompt["mask"]["class_type"], "ImageToMask")
        self.assertEqual(prompt["fill"]["inputs"]["image"], ["img", 0])
        self.assertEqual(prompt["fill"]["inputs"]["mask"], ["mask", 0])

    def test_remove_without_lama_says_how_to_install_it(self):
        api.urlopen = FakeComfyUI(nodes=("Sam2Segmentation", "BBoxFromJSON"))
        with self.assertRaises(api.ComfyUIError) as caught:
            api.remove(URL, b"IMAGE", b"MASK")
        self.assertIn("INPAINT_LoadInpaintModel", str(caught.exception))
        self.assertIn("local-ai-setup", str(caught.exception))

    def test_missing_message_points_to_local_ai_setup(self):
        self.assertIn("local-ai-setup", api.missing_message("Select Subject"))


if __name__ == "__main__":
    unittest.main()
