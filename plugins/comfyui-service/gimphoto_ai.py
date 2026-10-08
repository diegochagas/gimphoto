# Where GIMPhoto's local ComfyUI is, and waiting for it: shared by the AI
# plug-ins (ai-select, generative-fill, photo-restoration). The
# comfyui-service plug-in finds and starts ComfyUI when GIMPhoto starts and
# records it in its gimphoto-comfyui parasite; comfyui_api.py next to this
# file speaks to it.

import json

from gi.repository import Gimp

import comfyui_api as api
import comfyui_service as service

DEFAULT_URL = service.url_for(service.DEFAULT_PORT)


def backend():
    """(state, url) as comfyui-service found them at startup."""
    try:
        parasite = Gimp.get_parasite(service.PARASITE)
    except Exception:
        parasite = None
    if parasite is None:
        # a run without a user interface (scripts): try the usual address
        return "unknown", DEFAULT_URL
    info = json.loads(bytes(parasite.get_data()).decode())
    return info.get("state", "unknown"), info.get("url", DEFAULT_URL)


def wait_ready(state, url, what, waiting=None):
    """Raise a ComfyUIError saying what is missing, or wait while GIMPhoto's
    ComfyUI is still starting (waiting(seconds) is called meanwhile). Plain
    HTTP, no GIMP calls: safe in a worker thread."""
    # "missing": GIMPhoto found no comfyui service; a ComfyUI started some
    # other way may still be answering
    if state == "missing" and not api.is_up(url):
        raise api.ComfyUIError(api.missing_message(what))
    if not api.wait_until_up(url, progress=waiting):
        raise api.ComfyUIError(
            f"The local AI (ComfyUI at {url}) is not answering. It starts with GIMPhoto; "
            "if it does not, see: systemctl --user status comfyui"
        )


def ready_url(what):
    """The URL of a local ComfyUI that answers, showing the wait in GIMP's
    progress; a ComfyUIError saying what is missing otherwise."""
    state, url = backend()

    def waiting(elapsed):
        Gimp.progress_set_text("Starting the local AI... %d s" % elapsed)
        Gimp.progress_pulse()

    wait_ready(state, url, what, waiting)
    return url
