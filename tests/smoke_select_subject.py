# Run by scripts/smoke inside the installed GIMPhoto (python-fu-eval):
# Select Subject without the local AI. GIMPhoto recorded ComfyUI as missing
# (the gimphoto-comfyui parasite comfyui-service.py writes), so the command
# fails at once with a message saying where to install it, and leaves the
# selection alone. No ComfyUI is called: tests never use outside services.
# Writes "ok" or a reason to the file in GIMPHOTO_SMOKE_OUT.
import json
import os

from gi.repository import Gimp


def check():
    img = Gimp.Image.new(64, 64, Gimp.ImageBaseType.RGB)
    layer = Gimp.Layer.new(img, "bg", 64, 64, Gimp.ImageType.RGB_IMAGE, 100, Gimp.LayerMode.NORMAL)
    img.insert_layer(layer, None, 0)
    img.select_rectangle(Gimp.ChannelOps.REPLACE, 8, 8, 16, 16)
    # an address nothing listens on: a ComfyUI running on this machine is
    # not called
    data = json.dumps({"state": "missing", "url": "http://127.0.0.1:9"}).encode()
    Gimp.attach_parasite(Gimp.Parasite.new("gimphoto-comfyui", 0, list(data)))
    proc = Gimp.get_pdb().lookup_procedure("gimphoto-select-subject")
    if proc is None:
        return "gimphoto-select-subject is not registered"
    config = proc.create_config()
    config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
    config.set_property("image", img)
    config.set_core_object_array("drawables", [layer])
    result = proc.run(config)
    if result.index(0) == Gimp.PDBStatusType.SUCCESS:
        return "Select Subject succeeded without the local AI"
    message = result.index(1) if result.length() > 1 else ""
    message = getattr(message, "message", str(message))
    if "linux-mint-setup" not in message:
        return f"the error does not say where to install the local AI: {message!r}"
    _ok, non_empty, x1, y1, x2, y2 = Gimp.Selection.bounds(img)
    if (non_empty, x1, y1, x2, y2) != (True, 8, 8, 24, 24):
        return "the selection changed although Select Subject failed"
    return "ok"


try:
    result = check()
except Exception as e:  # report, do not hang the batch run
    result = f"{type(e).__name__}: {e}"
open(os.environ["GIMPHOTO_SMOKE_OUT"], "w").write(result + "\n")
