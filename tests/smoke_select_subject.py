# Run by scripts/smoke inside the installed GIMPhoto (python-fu-eval):
# GIMPhoto's AI commands without the local AI: Select Subject, Object
# Selection, Remove Background, Generative Fill, Generate Image, the
# Remove tool, Photo Restoration and Modern Photo. GIMPhoto recorded
# ComfyUI as missing (the gimphoto-comfyui parasite comfyui-service.py
# writes), so the command fails at once with a message saying where to
# install it, and leaves the selection and the layers (no mask, no new
# layer) alone. No ComfyUI is called: tests never use outside services.
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
    for name, args in (
        ("gimphoto-select-subject", {"drawables": [layer]}),
        # what the Object Selection tool sends: a box and add (0)
        ("gimphoto-object-select", {"operation": 0, "x": 30, "y": 30, "width": 20, "height": 20}),
        ("gimphoto-remove-background", {"drawables": [layer]}),
        ("gimphoto-generative-fill", {"drawables": [layer], "prompt": "a red ball", "model": "klein"}),
        ("gimphoto-generate-image", {"drawables": [layer], "prompt": "a lighthouse"}),
        ("gimphoto-photo-restoration", {"drawables": [layer]}),
        ("gimphoto-modern-photo", {"drawables": [layer]}),
        # what the Remove tool sends: one stroke
        ("gimphoto-remove", {"drawable": layer, "strokes": '[{"size": 10, "points": [40, 40, 50, 50]}]'}),
    ):
        proc = Gimp.get_pdb().lookup_procedure(name)
        if proc is None:
            return f"{name} is not registered"
        config = proc.create_config()
        config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
        config.set_property("image", img)
        for key, value in args.items():
            if key == "drawables":
                config.set_core_object_array(key, value)
            else:
                config.set_property(key, value)
        result = proc.run(config)
        if result.index(0) == Gimp.PDBStatusType.SUCCESS:
            return f"{name} succeeded without the local AI"
        message = result.index(1) if result.length() > 1 else ""
        message = getattr(message, "message", str(message))
        if "linux-mint-setup" not in message:
            return f"{name}: the error does not say where to install the local AI: {message!r}"
        _ok, non_empty, x1, y1, x2, y2 = Gimp.Selection.bounds(img)
        if (non_empty, x1, y1, x2, y2) != (True, 8, 8, 24, 24):
            return f"the selection changed although {name} failed"
        if layer.get_mask() is not None:
            return f"the layer got a mask although {name} failed"
        if len(img.get_layers()) != 1:
            return f"{name} added a layer although it failed"
    return "ok"


try:
    result = check()
except Exception as e:  # report, do not hang the batch run
    result = f"{type(e).__name__}: {e}"
open(os.environ["GIMPHOTO_SMOKE_OUT"], "w").write(result + "\n")
