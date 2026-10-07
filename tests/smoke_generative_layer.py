# Run by scripts/smoke inside the installed GIMPhoto (python-fu-eval): a
# layer made by Generative Fill keeps its variations, through an XCF save
# and reload, so its window can open again (a double click) and change it.
# Three made-up variations (red, green, blue) stand in for the AI: no
# ComfyUI is called. The plug-in is loaded as a module. Also: the layer is
# named after the chosen variation's own prompt, and keeping at most 12
# variations never drops the chosen one.
# Writes "ok" or a reason to the file in GIMPHOTO_SMOKE_OUT.
import importlib.util
import os
import shutil
import tempfile

from gi.repository import Gegl, Gimp, Gio

PLUGIN = os.environ.get("GIMPHOTO_GENERATIVE_FILL", "/app/lib/gimp/3.0/plug-ins/generative-fill/generative-fill.py")
COLORS = ("red", "lime", "blue")


def load_plugin():
    spec = importlib.util.spec_from_file_location("generative_fill", PLUGIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def solid_png(path, w, h, color):
    img = Gimp.Image.new(w, h, Gimp.ImageBaseType.RGB)
    try:
        layer = Gimp.Layer.new(img, "v", w, h, Gimp.ImageType.RGB_IMAGE, 100, Gimp.LayerMode.NORMAL)
        img.insert_layer(layer, None, 0)
        Gimp.context_push()
        Gimp.context_set_foreground(Gegl.Color.new(color))
        layer.fill(Gimp.FillType.FOREGROUND)
        Gimp.context_pop()
        Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, img, Gio.File.new_for_path(path), None)
    finally:
        img.delete()


def rgb(layer, x, y):
    return tuple(round(c, 1) for c in layer.get_pixel(x, y).get_rgba()[:3])


def check(gf, tmp):
    img = Gimp.Image.new(64, 48, Gimp.ImageBaseType.RGB)
    bg = Gimp.Layer.new(img, "bg", 64, 48, Gimp.ImageType.RGB_IMAGE, 100, Gimp.LayerMode.NORMAL)
    img.insert_layer(bg, None, 0)
    bg.fill(Gimp.FillType.WHITE)
    img.select_ellipse(Gimp.ChannelOps.REPLACE, 10, 8, 30, 20)

    job = gf.Job.new(img, "fill", tmp)
    if job.layer_box[2:] != (30, 20) or job.layer_at != (10, 8):
        return f"the layer's box is {job.layer_box} at {job.layer_at}, not the selection's"
    for color in COLORS:
        path = os.path.join(tmp, f"{color}.png")
        solid_png(path, 30, 20, color)
        # the last one from another prompt, as after a second Generate
        job.add(path, "a blue cube" if color == "blue" else "a ball", "qwen")
    job.chosen = 1
    layer = job.commit()
    if rgb(layer, 15, 10) != (0.0, 1.0, 0.0) or layer.get_mask() is None:
        return "the chosen variation is not the new masked layer"
    if layer.get_name() != "Generative Fill: a ball":
        return f"the layer is named {layer.get_name()!r}, not after its variation's prompt"

    xcf = os.path.join(tmp, "kept.xcf")
    Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, img, Gio.File.new_for_path(xcf), None)
    img.delete()
    img = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(xcf))
    layer = img.get_layers()[0]
    if layer.get_parasite(gf.META) is None:
        return "the generated layer lost its parasites in the XCF"

    reopened = os.path.join(tmp, "reopened")
    os.mkdir(reopened)
    again = gf.Job.edit(img, layer, reopened)
    if (again.prompt, again.model, again.chosen, len(again.variations)) != ("a ball", "qwen", 1, 3):
        return f"reopened as {again.prompt!r} {again.model!r}, variation {again.chosen} of {len(again.variations)}"
    for kept, color in zip(again.variations, COLORS):
        with open(kept, "rb") as f, open(os.path.join(tmp, f"{color}.png"), "rb") as g:
            if f.read() != g.read():
                return f"the {color} variation came back changed"

    again.chosen = 2
    changed = again.commit()
    layers = img.get_layers()
    if len(layers) != 2 or layers[0] != changed:
        return f"changing the variation left {len(layers)} layers"
    if changed.get_name() != "Generative Fill: a blue cube":
        return f"the changed layer is named {changed.get_name()!r}"
    if rgb(changed, 15, 10) != (0.0, 0.0, 1.0) or changed.get_mask() is None:
        return "the changed layer does not show the new variation, masked"
    if gf.Job.edit(img, changed, reopened).chosen != 2:
        return "the changed layer does not remember its variation"

    # 15 variations, the first (red) kept: it survives keeping only 12
    for name in ("many", "trimmed"):
        os.mkdir(os.path.join(tmp, name))
    many = gf.Job.edit(img, changed, os.path.join(tmp, "many"))
    for i in range(12):
        many.add(many.variations[1], f"more {i}", "klein")
    many.chosen = 0
    kept = many.commit()
    trimmed = gf.Job.edit(img, kept, os.path.join(tmp, "trimmed"))
    if len(trimmed.variations) != gf.KEEP_VARIATIONS:
        return f"{len(trimmed.variations)} variations kept, not {gf.KEEP_VARIATIONS}"
    with open(trimmed.variations[trimmed.chosen], "rb") as f, open(os.path.join(tmp, "red.png"), "rb") as g:
        if f.read() != g.read() or rgb(kept, 15, 10) != (1.0, 0.0, 0.0):
            return "keeping only the latest variations dropped the chosen one"
    return "ok"


tmp = tempfile.mkdtemp(prefix="gimphoto-smoke-generative-")
try:
    result = check(load_plugin(), tmp)
except Exception as e:  # report, do not hang the batch run
    result = f"{type(e).__name__}: {e}"
finally:
    shutil.rmtree(tmp, ignore_errors=True)
open(os.environ["GIMPHOTO_SMOKE_OUT"], "w").write(result + "\n")
