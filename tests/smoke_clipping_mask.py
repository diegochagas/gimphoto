# Run by scripts/smoke inside the installed GIMPhoto (python-fu-eval): a
# clipped layer shows only where the layer below it has pixels. The fixture
# tests/fixtures/clipping-mask.xcf (made in GIMPhoto: a white layer, a red
# block in the middle on a transparent layer "base", a blue layer "clipped"
# covering everything, clipped to "base" with Ctrl+Alt+G) flattens to blue
# inside the block and white outside; the clipping survives a save and
# reopen (the "gimphoto-clipped" parasite); exported to PSD and loaded again
# the layer is still clipped (the PSD clipping byte).
# Writes "ok" or a reason to the file in GIMPHOTO_SMOKE_OUT.
import os
import tempfile

from gi.repository import Gimp, Gio

FIXTURE = os.environ.get("GIMPHOTO_CLIPPING_XCF", "tests/fixtures/clipping-mask.xcf")


def rgb(drawable, x, y):
    return tuple(round(c, 1) for c in drawable.get_pixel(x, y).get_rgba()[:3])


def clipped(layer):
    return layer.get_parasite("gimphoto-clipped") is not None


def check_image(img, stage):
    layers = img.get_layers()
    if [layer.get_name() for layer in layers] != ["clipped", "base", "white"]:
        return f"{stage}: layers are {[layer.get_name() for layer in layers]}"
    top, base = layers[0], layers[1]
    if not clipped(top):
        return f"{stage}: the top layer is not clipped"
    if clipped(base):
        return f"{stage}: the base is clipped"
    if rgb(top, 4, 4) != (0.0, 0.0, 1.0):
        return f"{stage}: the clipped layer's own pixels changed: {rgb(top, 4, 4)}"
    flat = img.duplicate()
    try:
        result = flat.flatten()
        inside, outside = rgb(result, 32, 32), rgb(result, 4, 4)
    finally:
        flat.delete()
    if inside != (0.0, 0.0, 1.0):
        return f"{stage}: inside the base the result is {inside}, not blue"
    if outside != (1.0, 1.0, 1.0):
        return f"{stage}: outside the base the result is {outside}, not white (the clipped layer leaks)"
    return None


def main():
    if not os.path.exists(FIXTURE):
        return f"missing fixture {FIXTURE}"
    img = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(FIXTURE))
    problem = check_image(img, "opened")
    if problem:
        return problem
    with tempfile.TemporaryDirectory() as tmp:
        xcf = os.path.join(tmp, "again.xcf")
        Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, img, Gio.File.new_for_path(xcf), None)
        psd = os.path.join(tmp, "again.psd")
        Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, img, Gio.File.new_for_path(psd), None)
        img.delete()
        img = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(xcf))
        problem = check_image(img, "saved and reopened")
        img.delete()
        if problem:
            return problem
        img = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(psd))
        problem = check_image(img, "through PSD")
        img.delete()
    return problem or "ok"


try:
    result = main()
except Exception as err:  # report, do not hang the batch run
    result = f"{type(err).__name__}: {err}"
with open(os.environ["GIMPHOTO_SMOKE_OUT"], "w") as out:
    out.write(result)
