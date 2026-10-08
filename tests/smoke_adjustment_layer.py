# Run by scripts/smoke inside the installed GIMPhoto (python-fu-eval): an
# adjustment layer applies its filter to what is below it. The fixture
# tests/fixtures/adjustment-layer.xcf (made in GIMPhoto: a red layer, an
# Invert adjustment layer above it, with a white mask whose left half is
# painted black) opens with the adjustment layer, and flattening the image
# gives cyan where the mask is white and red where it is black; the red
# layer itself is untouched. Then the file is saved again and reopened,
# so the GIMPhoto property that marks the layer survives a save.
# Writes "ok" or a reason to the file in GIMPHOTO_SMOKE_OUT.
import os
import tempfile

from gi.repository import Gimp, Gio

FIXTURE = os.environ.get("GIMPHOTO_ADJUSTMENT_XCF", "tests/fixtures/adjustment-layer.xcf")


def rgb(drawable, x, y):
    return tuple(round(c, 1) for c in drawable.get_pixel(x, y).get_rgba()[:3])


def check_image(img, stage):
    layers = img.get_layers()
    if len(layers) != 2:
        return f"{stage}: {len(layers)} layers, not 2"
    adjustment, red = layers
    if adjustment.get_name() != "Invert":
        return f"{stage}: the top layer is {adjustment.get_name()!r}, not the Invert adjustment layer"
    if adjustment.get_mask() is None:
        return f"{stage}: the adjustment layer lost its mask"
    if rgb(red, 8, 8) != (1.0, 0.0, 0.0) or rgb(red, 56, 8) != (1.0, 0.0, 0.0):
        return f"{stage}: the red layer's pixels changed: {rgb(red, 8, 8)} {rgb(red, 56, 8)}"
    flat = img.duplicate()
    try:
        result = flat.flatten()
        left, right = rgb(result, 8, 8), rgb(result, 56, 8)
    finally:
        flat.delete()
    if right != (0.0, 1.0, 1.0):
        return f"{stage}: under the white mask the result is {right}, not cyan (inverted red)"
    if left != (1.0, 0.0, 0.0):
        return f"{stage}: under the black mask the result is {left}, not red (the adjustment held back)"
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
        img.delete()
        img = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(xcf))
        problem = check_image(img, "saved and reopened")
        img.delete()
    return problem or "ok"


try:
    result = main()
except Exception as err:  # report, do not hang the batch run
    result = f"{type(err).__name__}: {err}"
with open(os.environ["GIMPHOTO_SMOKE_OUT"], "w") as out:
    out.write(result)
