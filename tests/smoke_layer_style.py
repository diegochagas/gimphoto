# Run by scripts/smoke inside the installed GIMPhoto (python-fu-eval):
# Layer Style effects must draw outside an opaque layer that has no alpha
# channel (regression: a layer from a JPEG or opaque PNG showed nothing).
# Writes "ok" or a reason to the file in GIMPHOTO_SMOKE_OUT.
import os
import sys

sys.path.insert(0, "/app/lib/gimp/3.0/plug-ins/layer-style")
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

E.apply_style(layer, {"stroke": {**E.DEFAULTS["stroke"], "enabled": True, "size": 8, "color": "#ff0000"}})
flat = img.duplicate()
flat.flatten()
# 4 px left of the layer: inside an 8 px outside stroke
r, g, b, _a = flat.get_layers()[0].get_pixel(96, 100).get_rgba()
if not layer.has_alpha():
    result = "the layer still has no alpha channel"
elif r > 0.8 and g < 0.2 and b < 0.2:
    result = "ok"
else:
    result = f"no stroke outside the layer (pixel {r:.2f},{g:.2f},{b:.2f})"
open(out, "w").write(result + "\n")
