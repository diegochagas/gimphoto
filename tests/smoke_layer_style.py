# Run by scripts/smoke inside the installed GIMPhoto (python-fu-eval):
# Layer Style effects must draw outside an opaque layer that has no alpha
# channel (regression: a layer from a JPEG or opaque PNG showed nothing),
# also while a selection that does not cover them exists (regression: GIMP
# cropped the effects to the selection), which must be kept.
# Writes "ok" or a reason to the file in GIMPHOTO_SMOKE_OUT.
import os
import sys

sys.path.insert(0, os.environ.get("GIMPHOTO_LAYER_STYLE", "/app/lib/gimp/3.0/plug-ins/layer-style"))
from gi.repository import Gegl, Gimp

import layer_style_engine as E

out = os.environ["GIMPHOTO_SMOKE_OUT"]
img = Gimp.Image.new(300, 200, Gimp.ImageBaseType.RGB)
bg = Gimp.Layer.new(img, "bg", 300, 200, Gimp.ImageType.RGB_IMAGE, 100, Gimp.LayerMode.NORMAL)
img.insert_layer(bg, None, 0)
Gimp.context_set_foreground(Gegl.Color.new("#ffffff"))
bg.edit_fill(Gimp.FillType.FOREGROUND)
layer = Gimp.Layer.new(img, "opaque", 100, 100, Gimp.ImageType.RGB_IMAGE, 100, Gimp.LayerMode.NORMAL)
img.insert_layer(layer, None, 0)
layer.set_offsets(100, 50)
Gimp.context_set_foreground(Gegl.Color.new("#0000ff"))
layer.edit_fill(Gimp.FillType.FOREGROUND)

# a selection inside the layer, away from where the stroke goes
img.select_rectangle(Gimp.ChannelOps.REPLACE, 120, 70, 40, 40)
channels = len(img.get_channels())
E.apply_style(layer, {"stroke": {**E.DEFAULTS["stroke"], "enabled": True, "size": 8, "color": "#ff0000"}})
_, selected, x1, y1, x2, y2 = Gimp.Selection.bounds(img)
flat = img.duplicate()
flat.flatten()
# 4 px left of the layer: inside an 8 px outside stroke
r, g, b, _a = flat.get_layers()[0].get_pixel(96, 100).get_rgba()
if not layer.has_alpha():
    result = "the layer still has no alpha channel"
elif (selected, x1, y1, x2, y2) != (True, 120, 70, 160, 110):
    result = f"the selection was not kept: {(selected, x1, y1, x2, y2)}"
elif len(img.get_channels()) != channels:
    result = "a saved selection channel was left in the image"
elif r > 0.8 and g < 0.2 and b < 0.2:
    result = "ok"
else:
    result = f"no stroke outside the layer (pixel {r:.2f},{g:.2f},{b:.2f})"
open(out, "w").write(result + "\n")
