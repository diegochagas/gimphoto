# Run by scripts/smoke inside the installed GIMPhoto (python-fu-eval):
# GIMPhoto's GEGL operations gimphoto:gradient-overlay and
# gimphoto:pattern-overlay work as layer filters, only where the layer has
# pixels, and are still drawn after saving and reopening an XCF; and the
# Layer Style plug-in draws its Gradient and Pattern Overlay with them.
# Writes "ok" or a reason to the file in GIMPHOTO_SMOKE_OUT.
import os
import sys
import tempfile

sys.path.insert(0, os.environ.get("GIMPHOTO_LAYER_STYLE", "/app/lib/gimp/3.0/plug-ins/layer-style"))
from gi.repository import Gegl, Gimp, Gio

import layer_style_engine as E

OPS = ("gimphoto:gradient-overlay", "gimphoto:pattern-overlay")


def rgba(drawable, x, y):
    return drawable.get_pixel(x, y).get_rgba()


def near(c, want, tol=0.06):
    return all(abs(a - b) <= tol for a, b in zip(c, want))


def new_image():
    """200x100 image: a transparent layer, opaque only in x 50..149."""
    img = Gimp.Image.new(200, 100, Gimp.ImageBaseType.RGB)
    layer = Gimp.Layer.new(img, "shape", 200, 100, Gimp.ImageType.RGBA_IMAGE, 100, Gimp.LayerMode.NORMAL)
    img.insert_layer(layer, None, 0)
    img.select_rectangle(Gimp.ChannelOps.REPLACE, 50, 0, 100, 100)
    Gimp.context_set_foreground(Gegl.Color.new("#808080"))
    layer.edit_fill(Gimp.FillType.FOREGROUND)
    Gimp.Selection.none(img)
    return img, layer


def add(layer, op, props):
    f = Gimp.DrawableFilter.new(layer, op, "test " + op)
    cfg = f.get_config()
    for name, value in props.items():
        cfg.set_property(name, value)
    f.update()
    layer.append_filter(f)


def flat_pixel(img, x, y):
    flat = img.duplicate()
    flat.flatten()
    return rgba(flat.get_layers()[0], x, y)


def check(tmp):
    available = set(Gimp.DrawableFilter.operation_get_available())
    missing = [op for op in OPS if op not in available]
    if missing:
        return f"operations not available: {missing}"

    # gradient: black at the bottom, white at the top (angle 90), only on
    # the opaque part, so the flattened transparent part stays white
    img, layer = new_image()
    add(layer, OPS[0], {"color1": Gegl.Color.new("#000000"), "color2": Gegl.Color.new("#ffffff"), "angle": 90.0})
    top, bottom = flat_pixel(img, 100, 2), flat_pixel(img, 100, 97)
    if not (near(top[:3], (1, 1, 1), 0.1) and near(bottom[:3], (0, 0, 0), 0.1)):
        return f"gradient: top {top[:3]} bottom {bottom[:3]}, want white over black"
    if rgba(layer, 10, 50)[3] > 0.01:
        return "gradient: painted outside the layer's pixels"

    # pattern: a 2x1 red|blue image tiled from the layer's corner
    pattern = Gimp.Image.new(2, 1, Gimp.ImageBaseType.RGB)
    pl = Gimp.Layer.new(pattern, "p", 2, 1, Gimp.ImageType.RGB_IMAGE, 100, Gimp.LayerMode.NORMAL)
    pattern.insert_layer(pl, None, 0)
    pl.set_pixel(0, 0, Gegl.Color.new("#ff0000"))
    pl.set_pixel(1, 0, Gegl.Color.new("#0000ff"))
    path = os.path.join(tmp, "pattern.png")
    Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, pattern, Gio.File.new_for_path(path), None)
    img2, layer2 = new_image()
    add(layer2, OPS[1], {"path": path})
    a, b = flat_pixel(img2, 100, 50), flat_pixel(img2, 101, 50)
    if not (near(a[:3], (1, 0, 0)) and near(b[:3], (0, 0, 1))):
        return f"pattern: pixels {a[:3]} {b[:3]}, want red then blue"

    # both kept in an XCF
    xcf = os.path.join(tmp, "overlays.xcf")
    add(layer, OPS[1], {"path": path})
    Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, img, Gio.File.new_for_path(xcf), None)
    again = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(xcf))
    ops = [f.get_operation_name() for f in again.get_layers()[0].get_filters()]
    if sorted(ops) != sorted(OPS):
        return f"after reopening the XCF the layer's filters are {ops}"
    a = flat_pixel(again, 100, 50)
    if not near(a[:3], (1, 0, 0)):
        return f"after reopening the XCF the pattern is not drawn: {a[:3]}"
    # the Layer Style plug-in: a radial gradient (start colour at the
    # centre) and a GIMP pattern, exported to a file the operation reads
    img3, layer3 = new_image()
    pattern_name = Gimp.context_get_pattern().get_name()
    E.apply_style(
        layer3,
        {
            "gradient_overlay": {
                **E.DEFAULTS["gradient_overlay"],
                "enabled": True,
                "style": "radial",
                "color1": "#ff0000",
                "color2": "#0000ff",
            },
            "pattern_overlay": {**E.DEFAULTS["pattern_overlay"], "enabled": True, "pattern": pattern_name},
        },
    )
    ops = [f.get_operation_name() for f in layer3.get_filters()]
    if ops != list(OPS):
        return f"Layer Style: filters {ops}, want {list(OPS)}"
    path = E.pattern_file(pattern_name)
    if not path or not os.path.getsize(path):
        return f"Layer Style: GIMP pattern {pattern_name!r} was not exported"
    layer3.get_filters()[1].set_visible(False)
    centre = flat_pixel(img3, 100, 50)
    if not near(centre[:3], (1, 0, 0), 0.1):
        return f"Layer Style: radial gradient centre {centre[:3]}, want the start colour"
    return "ok"


with tempfile.TemporaryDirectory() as tmp:
    try:
        result = check(tmp)
    except Exception as e:  # report, do not hang the batch run
        result = f"{type(e).__name__}: {e}"
open(os.environ["GIMPHOTO_SMOKE_OUT"], "w").write(result + "\n")
