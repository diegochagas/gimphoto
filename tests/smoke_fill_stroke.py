# Run by scripts/smoke inside the installed GIMPhoto (python-fu-eval): Edit >
# Fill and Edit > Stroke (the fill-stroke plug-in, its module and its
# procedures). On white 64x64 images: a foreground fill covers only the
# selection; a Multiply green at 50% tints white half way; Black, 50% Gray
# and White; a pattern paints; Preserve Transparency leaves transparent
# pixels transparent (and without it they are filled); History brings back
# the layer as saved inside the selection only; Stroke puts a 4 px line
# inside, centred on or outside a square selection, keeps the selection,
# and strokes a layer's shape when nothing is selected; the gimphoto-fill
# and gimphoto-stroke procedures are in the Edit menu and run with
# arguments.
# Writes "ok" or a reason to the file in GIMPHOTO_SMOKE_OUT.
import importlib.util
import os
import tempfile

import gi

gi.require_version("Babl", "0.1")
from gi.repository import Babl, Gegl, Gimp, Gio  # noqa: E402

PLUGIN = os.environ.get("GIMPHOTO_FILL_STROKE", "/app/lib/gimp/3.0/plug-ins/fill-stroke/fill_stroke.py")


def load_module():
    spec = importlib.util.spec_from_file_location("fill_stroke", PLUGIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def srgb(drawable, x, y):
    """(r, g, b, a) as sRGB bytes."""
    return tuple(drawable.get_pixel(x, y).get_bytes(Babl.format("R'G'B'A u8")).get_data()[:4])


def white_image(alpha=False):
    img = Gimp.Image.new(64, 64, Gimp.ImageBaseType.RGB)
    kind = Gimp.ImageType.RGBA_IMAGE if alpha else Gimp.ImageType.RGB_IMAGE
    layer = Gimp.Layer.new(img, "paper", 64, 64, kind, 100, Gimp.LayerMode.NORMAL)
    img.insert_layer(layer, None, 0)
    layer.fill(Gimp.FillType.WHITE)
    return img, layer


def near(a, b, tolerance=3):
    return all(abs(x - y) <= tolerance for x, y in zip(a, b))


def check_fill(F):
    img, layer = white_image()
    Gimp.context_push()
    try:
        Gimp.context_set_foreground(Gegl.Color.new("#ff0000"))
        img.select_rectangle(Gimp.ChannelOps.REPLACE, 32, 0, 32, 64)
        F.fill(img, layer, "foreground")
    finally:
        Gimp.context_pop()
    if srgb(layer, 48, 32)[:3] != (255, 0, 0) or srgb(layer, 16, 32)[:3] != (255, 255, 255):
        return f"foreground: right {srgb(layer, 48, 32)}, left {srgb(layer, 16, 32)}"

    # on the white half: Multiply green is green, at 50% half way there
    img.select_rectangle(Gimp.ChannelOps.REPLACE, 0, 0, 32, 64)
    F.fill(img, layer, "color", color=Gegl.Color.new("#00ff00"), mode="multiply", opacity=50.0)
    r, g, b, _a = srgb(layer, 16, 32)
    if not (g == 255 and 120 < r < 230 and r == b) or srgb(layer, 48, 32)[:3] != (255, 0, 0):
        return f"multiply 50%: {srgb(layer, 16, 32)} on white, {srgb(layer, 48, 32)} on red"
    Gimp.Selection.none(img)
    for contents, expected in (("black", (0, 0, 0)), ("gray", (128, 128, 128)), ("white", (255, 255, 255))):
        F.fill(img, layer, contents)
        if not near(srgb(layer, 10, 10)[:3], expected, 1):
            return f"{contents}: {srgb(layer, 10, 10)}"

    pattern = next((p for p in Gimp.patterns_get_list("") if not p.get_name().startswith("Clipboard")), None)
    F.fill(img, layer, "pattern", pattern=pattern)
    if all(srgb(layer, x, x)[:3] == (255, 255, 255) for x in range(0, 64, 7)):
        return "pattern: still white"
    img.delete()

    # Preserve Transparency: the left half transparent
    img, layer = white_image(alpha=True)
    img.select_rectangle(Gimp.ChannelOps.REPLACE, 0, 0, 32, 64)
    layer.edit_clear()
    Gimp.Selection.none(img)
    F.fill(img, layer, "black", preserve=True)
    if srgb(layer, 10, 10)[3] != 0 or srgb(layer, 48, 10) != (0, 0, 0, 255):
        return f"preserve transparency: left {srgb(layer, 10, 10)}, right {srgb(layer, 48, 10)}"
    if layer.get_lock_alpha():
        return "preserve transparency: the alpha lock was left on"
    F.fill(img, layer, "black")
    if srgb(layer, 10, 10)[3] != 255:
        return f"without preserve transparency the left stays transparent: {srgb(layer, 10, 10)}"
    img.delete()

    # History: the layer as saved, inside the selection only
    img, layer = white_image()
    with tempfile.TemporaryDirectory() as tmp:
        xcf = Gio.File.new_for_path(os.path.join(tmp, "history.xcf"))
        Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, img, xcf, None)
        if img.get_file() is None:
            img.set_file(xcf)
        F.fill(img, layer, "black")
        img.select_rectangle(Gimp.ChannelOps.REPLACE, 0, 0, 32, 64)
        F.fill(img, layer, "history")
        restored, kept = srgb(layer, 10, 10)[:3], srgb(layer, 48, 10)[:3]
    if restored != (255, 255, 255) or kept != (0, 0, 0):
        return f"history: inside {restored}, outside {kept}"
    if len(img.get_layers()) != 1:
        return f"history left {len(img.get_layers()) - 1} layer(s) behind"
    if img.get_selected_layers() != [layer]:
        return "history: the layer is no longer the selected one"
    img.delete()
    return "ok"


def check_stroke(F):
    for location, black, white in (
        ("inside", (16, 19), (15, 20)),
        ("center", (14, 17), (13, 18)),
        ("outside", (12, 15), (11, 16)),
    ):
        img, layer = white_image()
        img.select_rectangle(Gimp.ChannelOps.REPLACE, 16, 16, 32, 32)
        F.stroke(img, layer, 4, color=Gegl.Color.new("black"), location=location)
        got_black = [srgb(layer, x, 32)[:3] for x in black]
        got_white = [srgb(layer, x, 32)[:3] for x in white]
        if any(p != (0, 0, 0) for p in got_black) or any(p != (255, 255, 255) for p in got_white):
            return f"stroke {location}: x={black} {got_black}, x={white} {got_white}"
        _ok, non_empty, x1, y1, x2, y2 = Gimp.Selection.bounds(img)
        if (non_empty, x1, y1, x2, y2) != (True, 16, 16, 48, 48):
            return f"stroke {location}: the selection changed to {(non_empty, x1, y1, x2, y2)}"
        if img.get_channels():
            return f"stroke {location}: {len(img.get_channels())} channel(s) left behind"
        if img.get_selected_layers() != [layer]:
            return f"stroke {location}: the layer is no longer the selected one"
        img.delete()

    # no selection: the layer's shape
    img = Gimp.Image.new(64, 64, Gimp.ImageBaseType.RGB)
    layer = Gimp.Layer.new(img, "shape", 64, 64, Gimp.ImageType.RGBA_IMAGE, 100, Gimp.LayerMode.NORMAL)
    img.insert_layer(layer, None, 0)
    img.select_rectangle(Gimp.ChannelOps.REPLACE, 16, 16, 32, 32)
    Gimp.context_push()
    Gimp.context_set_foreground(Gegl.Color.new("white"))
    layer.edit_fill(Gimp.FillType.FOREGROUND)
    Gimp.context_pop()
    Gimp.Selection.none(img)
    F.stroke(img, layer, 4, color=Gegl.Color.new("#0000ff"), location="outside")
    if srgb(layer, 13, 32) != (0, 0, 255, 255) or srgb(layer, 8, 32)[3] != 0:
        return f"stroke of the layer's shape: {srgb(layer, 13, 32)}, outside it {srgb(layer, 8, 32)}"
    if not Gimp.Selection.is_empty(img):
        return "stroke of the layer's shape left a selection"
    img.delete()
    return "ok"


def check_procedures():
    img, layer = white_image()
    img.select_rectangle(Gimp.ChannelOps.REPLACE, 0, 0, 32, 64)
    for name, args in (
        ("gimphoto-fill", {"contents": "black", "opacity": 100.0}),
        ("gimphoto-stroke", {"width": 2, "location": "outside", "color": Gegl.Color.new("#ff0000")}),
    ):
        proc = Gimp.get_pdb().lookup_procedure(name)
        if proc is None:
            return f"{name} is not registered"
        # in the Edit menu (GIMP drops a menu path given before the label)
        if "<Image>/Edit/[Stroke]" not in (proc.get_menu_paths() or []) or not proc.get_menu_label():
            return f"{name} is not in the Edit menu: {proc.get_menu_paths()!r}, {proc.get_menu_label()!r}"
        config = proc.create_config()
        config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
        config.set_property("image", img)
        config.set_core_object_array("drawables", [layer])
        for key, value in args.items():
            config.set_property(key, value)
        result = proc.run(config)
        if result.index(0) != Gimp.PDBStatusType.SUCCESS:
            return f"{name}: {getattr(result.index(1), 'message', result.index(1))}"
    if srgb(layer, 10, 10)[:3] != (0, 0, 0) or srgb(layer, 33, 10)[:3] != (255, 0, 0):
        return f"procedures: filled {srgb(layer, 10, 10)}, stroked {srgb(layer, 33, 10)}"
    if srgb(layer, 40, 10)[:3] != (255, 255, 255):
        return f"procedures: outside the stroke {srgb(layer, 40, 10)}"
    img.delete()
    return "ok"


try:
    F = load_module()
    result = check_fill(F)
    if result == "ok":
        result = check_stroke(F)
    if result == "ok":
        result = check_procedures()
except Exception as e:  # report, do not hang the batch run
    result = f"{type(e).__name__}: {e}"
with open(os.environ["GIMPHOTO_SMOKE_OUT"], "w") as out:
    out.write(result)
