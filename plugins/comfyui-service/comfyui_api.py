# The local ComfyUI's HTTP API, for GIMPhoto's AI plug-ins (Select Subject,
# Object Selection and Remove Background now; Generative Fill... later).
# Plain Python, no GIMP: the plug-ins pass what GIMPhoto found (the
# gimphoto-comfyui parasite of comfyui-service.py), and
# tests/test_comfyui_api.py drives it with a fake server.
#
# ComfyUI and its nodes are installed by linux-mint-setup's ComfyUI steps:
# BiRefNet (model set "birefnet") and its nodes, for the main subject
# (Select Subject, Remove Background);
# SAM 2.1 (model set "sam"), the SAM 2 nodes and its BBoxFromJSON node, for
# selecting the object in a box.

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

SAM_MODEL = "sam2.1_hiera_large.safetensors"
SUBJECT_MODEL = "General.safetensors"
INSTALL_HINT = "linux-mint-setup's ComfyUI steps (steps/comfyui)"
# a ComfyUI that GIMPhoto has just started takes ~20 s to answer
STARTUP_WAIT = 120
TIMEOUT = 600
POLL_INTERVAL = 1.0

# replaceable in tests
urlopen = urllib.request.urlopen
sleep = time.sleep


class ComfyUIError(RuntimeError):
    pass


def missing_message(what):
    return (
        f"{what} needs the local AI (ComfyUI), which is not installed on this "
        f"computer. Install it with {INSTALL_HINT}, then reopen GIMPhoto."
    )


def _request(url, data=None, headers=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace") if hasattr(e, "read") else ""
        raise ComfyUIError(f"ComfyUI answered HTTP {e.code} on {url}: {body[:400]}") from e
    except (urllib.error.URLError, OSError) as e:
        base = "/".join(url.split("/")[:3])
        raise ComfyUIError(f"The local AI (ComfyUI at {base}) is not answering ({e}).") from e


def is_up(url):
    try:
        _request(url + "/system_stats", timeout=5)
        return True
    except ComfyUIError:
        return False


def wait_until_up(url, waited=STARTUP_WAIT, progress=None):
    """True once ComfyUI answers; False after `waited` seconds."""
    started = time.monotonic()
    while True:
        if is_up(url):
            return True
        elapsed = time.monotonic() - started
        if elapsed >= waited:
            return False
        if progress:
            progress(elapsed)
        sleep(2)


def require_nodes(url, *nodes):
    for node in nodes:
        try:
            info = json.loads(_request(f"{url}/object_info/{node}"))
        except ComfyUIError as e:
            if "HTTP 404" not in str(e):
                raise
            info = {}
        if node not in info:
            raise ComfyUIError(
                f"The local AI (ComfyUI) has no {node} node: re-run {INSTALL_HINT}, then reopen GIMPhoto."
            )


def upload_png(url, name, png_bytes):
    """Put a PNG in ComfyUI's input folder (gimphoto/, overwritten each
    run); returns the name LoadImage takes."""
    boundary = uuid.uuid4().hex
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="subfolder"\r\n\r\ngimphoto\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode()
    body = head + png_bytes + f"\r\n--{boundary}--\r\n".encode()
    reply = json.loads(
        _request(url + "/upload/image", body, {"Content-Type": "multipart/form-data; boundary=" + boundary})
    )
    return f"{reply['subfolder']}/{reply['name']}" if reply.get("subfolder") else reply["name"]


def run(url, graph, progress=None, timeout=TIMEOUT):
    """Queue graph, wait for it, return the image of its "out" node."""
    reply = json.loads(
        _request(
            url + "/prompt",
            json.dumps({"prompt": graph, "client_id": uuid.uuid4().hex}).encode(),
            {"Content-Type": "application/json"},
        )
    )
    prompt_id = reply.get("prompt_id")
    if reply.get("node_errors") or not prompt_id:
        raise ComfyUIError(f"The local AI rejected the job: {json.dumps(reply)[:400]}")
    started = time.monotonic()
    while True:
        elapsed = time.monotonic() - started
        if elapsed > timeout:
            raise ComfyUIError(f"The local AI did not finish within {timeout} s.")
        if progress:
            progress(elapsed)
        sleep(POLL_INTERVAL)
        entry = json.loads(_request(f"{url}/history/{prompt_id}")).get(prompt_id)
        if not entry:
            continue
        status = entry.get("status", {})
        if status.get("status_str") == "error":
            for kind, data in status.get("messages") or []:
                if kind == "execution_error":
                    raise ComfyUIError(
                        f"The local AI failed: {data.get('node_type', 'node')}: {data.get('exception_message', '')}"
                    )
            raise ComfyUIError("The local AI failed.")
        for image in entry.get("outputs", {}).get("out", {}).get("images", [])[:1]:
            query = urllib.parse.urlencode(
                {
                    "filename": image["filename"],
                    "subfolder": image.get("subfolder", ""),
                    "type": image.get("type", "temp"),
                }
            )
            return _request(f"{url}/view?{query}", timeout=120)
        if status.get("completed"):
            raise ComfyUIError("The local AI finished without an image.")


def segment_graph(image_name, boxes):
    """SAM 2.1: a white-on-black mask of the object in each box."""
    return {
        "img": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "box": {"class_type": "BBoxFromJSON", "inputs": {"boxes": json.dumps([[round(v) for v in b] for b in boxes])}},
        "sam": {
            "class_type": "DownloadAndLoadSAM2Model",
            "inputs": {"model": SAM_MODEL, "segmentor": "single_image", "device": "cuda", "precision": "fp16"},
        },
        "seg": {
            "class_type": "Sam2Segmentation",
            "inputs": {"sam2_model": ["sam", 0], "image": ["img", 0], "keep_model_loaded": True, "bboxes": ["box", 0]},
        },
        "m2i": {"class_type": "MaskToImage", "inputs": {"mask": ["seg", 0]}},
        "out": {"class_type": "PreviewImage", "inputs": {"images": ["m2i", 0]}},
    }


def segment(url, image_png, boxes, progress=None):
    """Mask PNG (the image's size) of the object inside each box."""
    require_nodes(url, "Sam2Segmentation", "BBoxFromJSON")
    name = upload_png(url, "select.png", image_png)
    return run(url, segment_graph(name, boxes), progress)


def subject_graph(image_name):
    """BiRefNet: a soft mask (white = the main subject) the image's size."""
    return {
        "img": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "net": {
            "class_type": "LoadRembgByBiRefNetModel",
            "inputs": {"model": SUBJECT_MODEL, "device": "AUTO", "use_weight": False, "dtype": "float16"},
        },
        "mask": {
            "class_type": "GetMaskByBiRefNet",
            "inputs": {
                "model": ["net", 0],
                "images": ["img", 0],
                "width": 1024,
                "height": 1024,
                "upscale_method": "bilinear",
                "mask_threshold": 0.0,
            },
        },
        "m2i": {"class_type": "MaskToImage", "inputs": {"mask": ["mask", 0]}},
        "out": {"class_type": "PreviewImage", "inputs": {"images": ["m2i", 0]}},
    }


def subject(url, image_png, progress=None):
    """Mask PNG (the image's size) of the image's main subject."""
    require_nodes(url, "LoadRembgByBiRefNetModel", "GetMaskByBiRefNet")
    name = upload_png(url, "subject.png", image_png)
    return run(url, subject_graph(name), progress)
