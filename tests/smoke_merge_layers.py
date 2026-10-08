# Run by scripts/smoke inside the installed GIMPhoto (python-fu-eval):
# Merge Layers (Photoshop's Ctrl+E) on several selected layers (with one in
# between that is not selected; a group and a hidden layer among them), on
# one layer (Merge Down), on a layer group (Merge Group) and on layers
# inside a group. Writes "ok" or a reason to the file in GIMPHOTO_SMOKE_OUT.
import os
import sys

sys.path.insert(0, os.environ.get("GIMPHOTO_MERGE_LAYERS", "/app/lib/gimp/3.0/plug-ins/merge-layers"))
from gi.repository import Gegl, Gimp

from merge_layers import merge_layers


def square(img, name, colour, x, parent=None, position=0):
    """A 20x20 square of `colour` at (x, 10) on a transparent layer."""
    layer = Gimp.Layer.new(img, name, 100, 40, Gimp.ImageType.RGBA_IMAGE, 100, Gimp.LayerMode.NORMAL)
    img.insert_layer(layer, parent, position)
    img.select_rectangle(Gimp.ChannelOps.REPLACE, x, 10, 20, 20)
    Gimp.context_set_foreground(Gegl.Color.new(colour))
    layer.edit_fill(Gimp.FillType.FOREGROUND)
    Gimp.Selection.none(img)
    return layer


def opaque(layer, x):
    return layer.get_pixel(x, 20).get_rgba()[3] > 0.99


def names(layers):
    return [layer.get_name() for layer in layers]


def check():
    Gimp.context_push()
    try:
        return run_checks()
    finally:
        Gimp.context_pop()


def run_checks():
    # several layers: top (red) and bottom (blue), "middle" not selected
    img = Gimp.Image.new(100, 40, Gimp.ImageBaseType.RGB)
    bottom = square(img, "bottom", "blue", 0)
    middle = square(img, "middle", "lime", 40)
    top = square(img, "top", "red", 70)
    img.set_selected_layers([top, bottom])
    merged = merge_layers(img)
    if names(img.get_layers()) != ["top", "middle"]:
        return f"several layers: the stack is {names(img.get_layers())}, not the merged 'top' over 'middle'"
    if img.get_layers()[1] != middle or not (opaque(merged, 5) and opaque(merged, 75)) or opaque(merged, 45):
        return "several layers: the merged layer does not hold the two selected layers' pixels only"
    if img.get_selected_layers() != [merged]:
        return "several layers: the merged layer is not selected"
    img.delete()

    # one layer: merge down, keeping the lower layer's name
    img = Gimp.Image.new(100, 40, Gimp.ImageBaseType.RGB)
    square(img, "lower", "blue", 0)
    upper = square(img, "upper", "red", 70)
    img.set_selected_layers([upper])
    merged = merge_layers(img)
    if names(img.get_layers()) != ["lower"] or not (opaque(merged, 5) and opaque(merged, 75)):
        return f"one layer: not merged down into 'lower': {names(img.get_layers())}"
    # nothing below: GIMP's own message
    try:
        merge_layers(img)
        return "one layer with nothing below: merged anyway"
    except ValueError:
        pass
    # one hidden layer: not merged
    hidden = square(img, "hidden", "lime", 40)
    hidden.set_visible(False)
    img.set_selected_layers([hidden])
    try:
        merge_layers(img)
        return "one hidden layer: merged anyway"
    except ValueError:
        pass
    img.delete()

    # a group: one layer with the group's name
    img = Gimp.Image.new(100, 40, Gimp.ImageBaseType.RGB)
    group = Gimp.GroupLayer.new(img, "group")
    img.insert_layer(group, None, 0)
    square(img, "a", "blue", 0, group, 0)
    square(img, "b", "red", 70, group, 0)
    img.set_selected_layers([group])
    merged = merge_layers(img)
    if merged.is_group() or names(img.get_layers()) != ["group"] or not opaque(merged, 75):
        return f"group: not merged into one layer named 'group': {names(img.get_layers())}"
    img.delete()

    # inside a group: merged where they are
    img = Gimp.Image.new(100, 40, Gimp.ImageBaseType.RGB)
    square(img, "outside", "lime", 40)
    group = Gimp.GroupLayer.new(img, "group")
    img.insert_layer(group, None, 0)
    a = square(img, "a", "blue", 0, group, 0)
    b = square(img, "b", "red", 70, group, 0)
    img.set_selected_layers([a, b])
    merged = merge_layers(img)
    if merged.get_parent() != group or names(group.get_children()) != ["b"]:
        return f"inside a group: not merged in the group: {names(group.get_children())}"
    if names(img.get_layers()) != ["group", "outside"]:
        return f"inside a group: layers outside changed: {names(img.get_layers())}"
    img.delete()

    # several, one of them a group and one hidden: the group is merged in,
    # the hidden layer is left as it is
    img = Gimp.Image.new(100, 40, Gimp.ImageBaseType.RGB)
    hidden = square(img, "hidden", "lime", 40)
    hidden.set_visible(False)
    group = Gimp.GroupLayer.new(img, "group")
    img.insert_layer(group, None, 0)
    square(img, "in group", "blue", 0, group, 0)
    top = square(img, "top", "red", 70)
    img.set_selected_layers([top, group, hidden])
    merged = merge_layers(img)
    if names(img.get_layers()) != ["top", "hidden"] or merged.is_group() or not opaque(merged, 5):
        return f"a group and a hidden layer: {names(img.get_layers())}"
    img.delete()

    # a layer whose position is locked (on the canvas) still merges into the top one
    img = Gimp.Image.new(100, 40, Gimp.ImageBaseType.RGB)
    locked = square(img, "locked", "blue", 0)
    square(img, "middle", "lime", 40)
    top = square(img, "top", "red", 70)
    locked.set_lock_position(True)
    img.set_selected_layers([top, locked])
    merge_layers(img)
    if names(img.get_layers()) != ["top", "middle"]:
        return f"a position-locked layer: not merged into 'top': {names(img.get_layers())}"
    img.delete()
    return "ok"


try:
    result = check()
except Exception as e:
    result = f"error: {e!r}"
with open(os.environ["GIMPHOTO_SMOKE_OUT"], "w") as f:
    f.write(result)
