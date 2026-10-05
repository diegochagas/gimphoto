# Run by scripts/smoke inside the installed GIMPhoto (python-fu-eval):
# Layer via Copy / Cut (Photoshop's Ctrl+J / Ctrl+Shift+J) on an opaque
# layer, as opened from a JPEG. Writes "ok" or a reason to the file in
# GIMPHOTO_SMOKE_OUT.
import os
import sys

sys.path.insert(0, os.environ.get("GIMPHOTO_LAYER_VIA", "/app/lib/gimp/3.0/plug-ins/layer-via"))
from gi.repository import Gegl, Gimp

from layer_via import layer_via


def setup():
    img = Gimp.Image.new(300, 200, Gimp.ImageBaseType.RGB)
    layer = Gimp.Layer.new(img, "photo", 300, 200, Gimp.ImageType.RGB_IMAGE, 100, Gimp.LayerMode.NORMAL)
    img.insert_layer(layer, None, 0)
    Gimp.context_set_foreground(Gegl.Color.new("#0000ff"))
    layer.edit_fill(Gimp.FillType.FOREGROUND)
    img.select_rectangle(Gimp.ChannelOps.REPLACE, 50, 40, 60, 30)
    return img, layer


def alpha(drawable, x, y):
    return drawable.get_pixel(x, y).get_rgba()[3]


def check():
    img, layer = setup()
    (new,) = layer_via(img)
    if len(img.get_layers()) != 2 or img.get_layers()[0] != new:
        return "copy: the new layer is not above the original"
    if (new.get_offsets()[1:], new.get_width(), new.get_height()) != ((50, 40), 60, 30):
        return f"copy: new layer is not the selected area: {new.get_offsets()[1:]} {new.get_width()}x{new.get_height()}"
    if alpha(new, 10, 10) < 0.99 or alpha(layer, 60, 50) < 0.99:
        return "copy: pixels missing"
    if not Gimp.Selection.is_empty(img) or img.get_selected_layers() != [new]:
        return "copy: selection not dropped or new layer not selected"

    img, layer = setup()
    (new,) = layer_via(img, cut=True)
    if alpha(new, 10, 10) < 0.99:
        return "cut: new layer is empty"
    if alpha(layer, 60, 50) > 0.01 or alpha(layer, 10, 10) < 0.99:
        return "cut: the area was not cleared (only it) from the original"
    if len(img.get_channels()) != 0:
        return "cut: a saved selection channel was left in the image"

    img, layer = setup()
    Gimp.Selection.none(img)
    (new,) = layer_via(img)
    if (new.get_width(), new.get_height()) != (300, 200):
        return "no selection: the layer was not duplicated whole"
    try:
        layer_via(img, cut=True)
        return "no selection: Layer via Cut did something"
    except ValueError:
        pass
    return "ok"


open(os.environ["GIMPHOTO_SMOKE_OUT"], "w").write(check() + "\n")
