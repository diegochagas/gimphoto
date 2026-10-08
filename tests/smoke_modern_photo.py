# Run by scripts/smoke inside the installed GIMPhoto (python-fu-eval): Modern
# Photo's black-and-white check on GIMP images, through the plug-in's own
# export (the thumbnail read from a GEGL buffer). A Grayscale-mode image
# and a sepia RGB one are black and white; a red and blue one is not. No
# ComfyUI is called. The plug-in is loaded as a module.
# Writes "ok" or a reason to the file in GIMPHOTO_SMOKE_OUT.
import importlib.util
import os
import shutil
import sys
import tempfile

from gi.repository import Gegl, Gimp

PLUGIN = os.environ.get(
    "GIMPHOTO_PHOTO_RESTORATION", "/app/lib/gimp/3.0/plug-ins/photo-restoration/photo-restoration.py"
)


def load_plugin():
    sys.path.insert(0, os.path.dirname(PLUGIN))
    spec = importlib.util.spec_from_file_location("photo_restoration", PLUGIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def image(base, layer_type, colours):
    """A 120x80 image in vertical stripes of `colours`."""
    img = Gimp.Image.new(120, 80, base)
    layer = Gimp.Layer.new(img, "photo", 120, 80, layer_type, 100, Gimp.LayerMode.NORMAL)
    img.insert_layer(layer, None, 0)
    width = 120 // len(colours)
    Gimp.context_push()
    try:
        for i, colour in enumerate(colours):
            img.select_rectangle(Gimp.ChannelOps.REPLACE, i * width, 0, width, 80)
            Gimp.context_set_foreground(Gegl.Color.new(colour))
            layer.edit_fill(Gimp.FillType.FOREGROUND)
        Gimp.Selection.none(img)
    finally:
        Gimp.context_pop()
    return img


def check():
    plugin = load_plugin()
    tmpdir = tempfile.mkdtemp(prefix="gimphoto-smoke-modern-")
    try:
        cases = (
            (
                "a Grayscale image",
                Gimp.ImageBaseType.GRAY,
                Gimp.ImageType.GRAY_IMAGE,
                ("#202020", "#808080", "#e0e0e0"),
                True,
            ),
            (
                "a sepia image",
                Gimp.ImageBaseType.RGB,
                Gimp.ImageType.RGB_IMAGE,
                ("#3a2a1c", "#8a6d50", "#e8d8c0"),
                True,
            ),
            ("a red and blue image", Gimp.ImageBaseType.RGB, Gimp.ImageType.RGB_IMAGE, ("#c03020", "#2040c0"), False),
        )
        for name, base, layer_type, colours, want in cases:
            img = image(base, layer_type, colours)
            try:
                pixels = plugin.export_flat(img, os.path.join(tmpdir, "photo.png"), plugin.SAMPLE)
            finally:
                img.delete()
            if len(pixels) != plugin.SAMPLE * plugin.SAMPLE * 3:
                return f"{name}: the thumbnail has {len(pixels)} bytes"
            if plugin.modern_photo.is_monochrome(pixels) != want:
                return f"{name} is {'not ' if want else ''}taken as black and white"
        return "ok"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


try:
    result = check()
except Exception as e:
    result = f"error: {e!r}"
with open(os.environ["GIMPHOTO_SMOKE_OUT"], "w") as f:
    f.write(result)
