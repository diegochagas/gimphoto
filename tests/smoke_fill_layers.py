# Run by scripts/smoke inside the installed GIMPhoto (python-fu-eval): fill
# layers (the fill-layers plug-in, loaded as a module). On a white 64x64
# image with the right half selected: a preview keeps the selection; a red
# Solid Color fill shows red on the right and white on the left (the mask
# came from the selection); a black-to-white linear Gradient fill is darker
# on the left than on the right; a Pattern fill paints something other than
# white. The parasite names the kind and Layer Content Options' reading of
# the settings matches what was set (a mid tone and the foreground colour
# too, in sRGB; a pattern named with a space); names count layers inside
# groups; a failure leaves no layer behind; saved to XCF and reopened, the
# fills are still there; a grayscale image gets a grayscale fill layer.
# Writes "ok" or a reason to the file in GIMPHOTO_SMOKE_OUT.
import importlib.util
import os
import tempfile

from gi.repository import Gegl, Gimp, Gio

PLUGIN = os.environ.get("GIMPHOTO_FILL_LAYERS", "/app/lib/gimp/3.0/plug-ins/fill-layers/fill_layers.py")


def load_module():
    spec = importlib.util.spec_from_file_location("fill_layers", PLUGIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rgb(drawable, x, y):
    return tuple(round(c, 2) for c in drawable.get_pixel(x, y).get_rgba()[:3])


def flat_rgb(img, x, y):
    d = img.duplicate()
    try:
        return rgb(d.flatten(), x, y)
    finally:
        d.delete()


def check(F):
    img = Gimp.Image.new(64, 64, Gimp.ImageBaseType.RGB)
    bg = Gimp.Layer.new(img, "white", 64, 64, Gimp.ImageType.RGB_IMAGE, 100, Gimp.LayerMode.NORMAL)
    img.insert_layer(bg, None, 0)
    bg.fill(Gimp.FillType.WHITE)

    # solid, masked by the selection; the dialog's preview keeps the
    # selection (for Cancel), the final layer drops it
    img.select_rectangle(Gimp.ChannelOps.REPLACE, 32, 0, 32, 64)
    preview = F.create(img, "solid", {"color": "#ff0000"}, drop_selection=False)
    if Gimp.Selection.is_empty(img) or preview.get_mask() is None:
        return "preview: the selection was dropped or the mask missing"
    img.remove_layer(preview)
    solid = F.create(img, "solid", {"color": "#ff0000"})
    if not Gimp.Selection.is_empty(img):
        return "the selection was not dropped after making the mask"
    if solid.get_mask() is None or F.kind_of(solid) != "solid":
        return f"solid: mask {solid.get_mask()}, kind {F.kind_of(solid)!r}"
    # undoable, or undoing the new layer warns "Can't undo Attach Parasite"
    if not solid.get_parasite(F.PARASITE).get_flags() & Gimp.PARASITE_UNDOABLE:
        return "solid: the gimphoto-fill parasite is not undoable"
    if flat_rgb(img, 48, 32) != (1.0, 0.0, 0.0) or flat_rgb(img, 16, 32) != (1.0, 1.0, 1.0):
        return f"solid: right {flat_rgb(img, 48, 32)}, left {flat_rgb(img, 16, 32)}"
    if F.read_settings(F.fill_filter(solid, "solid"), "solid") != {"color": "#ff0000"}:
        return f"solid: settings read back as {F.read_settings(F.fill_filter(solid, 'solid'), 'solid')}"
    # a mid tone reads back as itself (sRGB, not linear values)
    F.apply(solid, "solid", {"color": "#d04020"})
    if F.read_settings(F.fill_filter(solid, "solid"), "solid") != {"color": "#d04020"}:
        return f"solid: #d04020 read back as {F.read_settings(F.fill_filter(solid, 'solid'), 'solid')}"
    Gimp.context_push()  # leave the profile's foreground colour alone
    try:
        Gimp.context_set_foreground(Gegl.Color.new("#d04020"))
        from_fg = F.defaults("solid")
    finally:
        Gimp.context_pop()
    if from_fg != {"color": "#d04020"}:
        return f"solid: the foreground #d04020 gave {from_fg}"
    F.apply(solid, "solid", {"color": "#ff0000"})
    solid.set_visible(False)

    # gradient, left to right
    gradient = F.create(
        img,
        "gradient",
        {"color1": "#000000", "color2": "#ffffff", "style": "linear", "angle": 0.0, "scale": 100.0, "reverse": False},
    )
    left, right = flat_rgb(img, 4, 32), flat_rgb(img, 60, 32)
    if not (left[0] < 0.3 and right[0] > 0.7):
        return f"gradient: left {left}, right {right}"
    got = F.read_settings(F.fill_filter(gradient, "gradient"), "gradient")
    if got["style"] != "linear" or got["color1"] != "#000000":
        return f"gradient: settings read back as {got}"
    gradient.set_visible(False)

    # pattern: any GIMP pattern paints something
    patterns = Gimp.Pattern.get_by_name("Pine") or Gimp.Pattern.get_by_name("Wood")
    if patterns is None:
        candidates = Gimp.patterns_get_list("")
        patterns = candidates[0] if candidates else None
    if patterns is None:
        return "no GIMP pattern to test with"
    pattern = F.create(img, "pattern", {"pattern": patterns.get_name(), "scale": 100.0})
    if flat_rgb(img, 10, 10) == (1.0, 1.0, 1.0) and flat_rgb(img, 40, 40) == (1.0, 1.0, 1.0):
        return "pattern: the layer is still white"
    if F.read_settings(F.fill_filter(pattern, "pattern"), "pattern")["pattern"] != patterns.get_name():
        return "pattern: name read back differs"

    # a pattern whose name has a space reads back by its own name (the
    # cache file's name has it replaced)
    named = [p for p in Gimp.patterns_get_list("") if not p.get_name().startswith("Clipboard")]
    spaced = next((p for p in named if F.pattern_cache_name(p.get_name()) != p.get_name()), None)
    if spaced is not None:
        F.apply(pattern, "pattern", {"pattern": spaced.get_name(), "scale": 100.0})
        got = F.read_settings(F.fill_filter(pattern, "pattern"), "pattern")["pattern"]
        if got != spaced.get_name():
            return f"pattern: {spaced.get_name()!r} read back as {got!r}"

    # names count the layers inside groups too
    group = Gimp.GroupLayer.new(img, "group")
    img.insert_layer(group, None, 0)
    inner = Gimp.Layer.new(img, "Pattern Fill 2", 8, 8, Gimp.ImageType.RGBA_IMAGE, 100, Gimp.LayerMode.NORMAL)
    img.insert_layer(inner, group, 0)
    if F._next_name(img, "Pattern Fill") != "Pattern Fill 3":
        return f"names: next pattern fill would be {F._next_name(img, 'Pattern Fill')!r}"
    img.remove_layer(group)

    # a failure while making the layer leaves no layer and keeps the selection
    before = len(img.get_layers())
    img.select_rectangle(Gimp.ChannelOps.REPLACE, 0, 0, 8, 8)
    configure = F.configure

    def broken(*_args):
        raise RuntimeError("test")

    F.configure = broken
    try:
        F.create(img, "solid", {"color": "#00ff00"})
        return "failure: create() did not raise"
    except RuntimeError:
        pass
    finally:
        F.configure = configure
    if len(img.get_layers()) != before or Gimp.Selection.is_empty(img):
        left = len(img.get_layers()) - before
        return f"failure: {left} layer(s) left, selection kept: {not Gimp.Selection.is_empty(img)}"
    Gimp.Selection.none(img)

    # through an XCF
    pattern.set_visible(False)
    solid.set_visible(True)
    with tempfile.TemporaryDirectory() as tmp:
        xcf = os.path.join(tmp, "fills.xcf")
        Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, img, Gio.File.new_for_path(xcf), None)
        img.delete()
        img = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(xcf))
    kinds = [F.kind_of(layer) for layer in img.get_layers()]
    if kinds != ["pattern", "gradient", "solid", None]:
        return f"reopened: kinds {kinds}"
    if flat_rgb(img, 48, 32) != (1.0, 0.0, 0.0) or flat_rgb(img, 16, 32) != (1.0, 1.0, 1.0):
        return f"reopened solid: right {flat_rgb(img, 48, 32)}, left {flat_rgb(img, 16, 32)}"
    img.delete()

    # a grayscale image gets a grayscale fill layer
    gray = Gimp.Image.new(16, 16, Gimp.ImageBaseType.GRAY)
    base = Gimp.Layer.new(gray, "white", 16, 16, Gimp.ImageType.GRAY_IMAGE, 100, Gimp.LayerMode.NORMAL)
    gray.insert_layer(base, None, 0)
    fill = F.create(gray, "solid", {"color": "#000000"})
    if fill.is_rgb() or F.kind_of(fill) != "solid" or flat_rgb(gray, 8, 8) != (0.0, 0.0, 0.0):
        return f"grayscale: rgb {fill.is_rgb()}, kind {F.kind_of(fill)!r}, pixel {flat_rgb(gray, 8, 8)}"
    gray.delete()
    return "ok"


try:
    result = check(load_module())
except Exception as e:  # report, do not hang the batch run
    result = f"{type(e).__name__}: {e}"
with open(os.environ["GIMPHOTO_SMOKE_OUT"], "w") as out:
    out.write(result)
