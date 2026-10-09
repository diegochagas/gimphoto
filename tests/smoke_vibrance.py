# Run by scripts/smoke inside the installed GIMPhoto (python-fu-eval):
# gimphoto:vibrance, Photoshop's Vibrance. On a strip of colours, as a
# filter merged into the layer: with Vibrance +100 a muted colour gains more
# saturation than an already saturated one, and a grey stays grey; a skin
# tone gains less than a blue just as saturated, unless skin protection is
# off; Saturation -100 turns colours grey; Vibrance and Saturation 0 change
# nothing; on a 32-bit float image a value above 1 is not clipped. The
# Colors menu and Layer > New Adjustment Layer entries are
# checked by scripts/smoke in the binary.
# Writes "ok" or a reason to the file in GIMPHOTO_SMOKE_OUT.
import os

import gi

gi.require_version("Babl", "0.1")
from gi.repository import Babl, Gegl, Gimp  # noqa: E402

COLORS = {
    "muted": "#998073",  # a dull pink-brown, little saturation
    "vivid": "#ff1a1a",  # nearly pure red
    "grey": "#808080",
    "skin": "#e0ab69",  # a typical skin tone (hue about 33 degrees)
    "blue": "#69abe0",  # as saturated as the skin tone, hue about 207
}


def rgb(drawable, x):
    return tuple(drawable.get_pixel(x, 0).get_bytes(Babl.format("R'G'B'A u8")).get_data()[:3])


def chroma(c):
    return max(c) - min(c)


def strip():
    """A 1-pixel-high image, one pixel per colour, in COLORS' order."""
    img = Gimp.Image.new(len(COLORS), 1, Gimp.ImageBaseType.RGB)
    layer = Gimp.Layer.new(img, "colors", len(COLORS), 1, Gimp.ImageType.RGB_IMAGE, 100, Gimp.LayerMode.NORMAL)
    img.insert_layer(layer, None, 0)
    Gimp.context_push()
    for x, value in enumerate(COLORS.values()):
        img.select_rectangle(Gimp.ChannelOps.REPLACE, x, 0, 1, 1)
        Gimp.context_set_foreground(Gegl.Color.new(value))
        layer.edit_fill(Gimp.FillType.FOREGROUND)
    Gimp.context_pop()
    Gimp.Selection.none(img)
    return img, layer


def vibrance(vibrance=0.0, saturation=0.0, protect=True):
    """The strip's colours after the filter: name -> (r, g, b)."""
    img, layer = strip()
    try:
        f = Gimp.DrawableFilter.new(layer, "gimphoto:vibrance", "Vibrance")
        cfg = f.get_config()
        cfg.set_property("vibrance", vibrance)
        cfg.set_property("saturation", saturation)
        cfg.set_property("protect-skin", protect)
        f.update()
        layer.append_filter(f)
        layer.merge_filters()
        return {name: rgb(layer, x) for x, name in enumerate(COLORS)}
    finally:
        img.delete()


def check():
    if "gimphoto:vibrance" not in Gimp.DrawableFilter.operation_get_available():
        return "gimphoto:vibrance is not among the operations GIMP offers"
    before = vibrance()
    original = {name: tuple(round(int(h[i : i + 2], 16)) for i in (1, 3, 5)) for name, h in COLORS.items()}
    for name in COLORS:
        if max(abs(a - b) for a, b in zip(before[name], original[name])) > 1:
            return f"Vibrance 0, Saturation 0 changed {name}: {original[name]} -> {before[name]}"

    up = vibrance(vibrance=100.0)
    gain = {name: chroma(up[name]) / max(1, chroma(before[name])) for name in COLORS}
    if not gain["muted"] > gain["vivid"] + 0.2:
        return f"Vibrance +100: the muted colour gained x{gain['muted']:.2f}, the vivid one x{gain['vivid']:.2f}"
    if chroma(up["grey"]) > 1:
        return f"Vibrance +100 coloured the grey: {up['grey']}"
    if not gain["skin"] < gain["blue"] - 0.1:
        return f"Vibrance +100: skin x{gain['skin']:.2f}, blue x{gain['blue']:.2f} (skin should be protected)"

    unprotected = vibrance(vibrance=100.0, protect=False)
    skin, blue = (chroma(unprotected[n]) / max(1, chroma(before[n])) for n in ("skin", "blue"))
    if abs(skin - blue) > 0.1:
        return f"Vibrance +100 without skin protection: skin x{skin:.2f}, blue x{blue:.2f}"

    # high bit depth: a value above 1 (brighter than white) is not clipped
    img = Gimp.Image.new_with_precision(1, 1, Gimp.ImageBaseType.RGB, Gimp.Precision.FLOAT_LINEAR)
    layer = Gimp.Layer.new(img, "hdr", 1, 1, Gimp.ImageType.RGB_IMAGE, 100, Gimp.LayerMode.NORMAL)
    img.insert_layer(layer, None, 0)
    bright = Gegl.Color.new("black")
    bright.set_rgba(3.0, 1.5, 1.0, 1.0)
    layer.set_pixel(0, 0, bright)
    f = Gimp.DrawableFilter.new(layer, "gimphoto:vibrance", "Vibrance")
    f.get_config().set_property("vibrance", 50.0)
    f.update()
    layer.append_filter(f)
    layer.merge_filters()
    red = layer.get_pixel(0, 0).get_rgba()[0]
    img.delete()
    if red <= 2.0:
        return f"Vibrance clipped a high bit depth value: red 3.0 became {red:.2f}"

    grey = vibrance(saturation=-100.0)
    for name, color in grey.items():
        if chroma(color) > 2:
            return f"Saturation -100 left {name} coloured: {color}"
    return "ok"


try:
    result = check()
except Exception as e:  # report, do not hang the batch run
    result = f"{type(e).__name__}: {e}"
with open(os.environ["GIMPHOTO_SMOKE_OUT"], "w") as out:
    out.write(result)
