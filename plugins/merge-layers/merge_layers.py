"""Photoshop's Merge Layers (Ctrl+E).

- Several layers selected: they become one layer, in the place of the top
  one and with its name (Photoshop's rule). Selected layers that are hidden
  are left as they are, and so are layers in between that are not
  selected.
- One layer selected: Merge Down, into the layer below it, which keeps its
  name (as in Photoshop; a hidden layer is not merged).
- One layer group selected: Merge Group, into one layer with the group's
  name.

Used by merge-layers.py; kept apart so the smoke test can run it headless.
"""

from gi.repository import Gimp, GLib

MERGE = Gimp.MergeType.EXPAND_AS_NECESSARY


def stacking(layers):
    """Every layer of `layers` and their children, top to bottom, a group
    before what is in it."""
    for layer in layers:
        yield layer
        if layer.is_group():
            yield from stacking(layer.get_children())


def inside(layer, ancestors):
    parent = layer.get_parent()
    while parent is not None:
        if parent in ancestors:
            return True
        parent = parent.get_parent()
    return False


def checked(result, message):
    """GIMP's calls give nothing (None or False) back when they cannot."""
    if not result:
        raise ValueError(message)
    return result


def as_layer(layer):
    """A group becomes one layer (Merge Group); a layer stays itself."""
    if not layer.is_group():
        return layer
    return checked(layer.merge(), f'The group "{layer.get_name()}" could not be merged.')


def merge_layers(image):
    """Merge the selected layers; return the merged layer. Raises
    ValueError with the message to show when there is nothing to merge."""
    selected = set(image.get_selected_layers())
    if not selected:
        raise ValueError("Select the layers to merge.")
    if len(selected) == 1:
        (layer,) = selected
        if not layer.get_visible():
            raise ValueError("The layer is hidden: show it to merge it.")
        merged = as_layer(layer) if layer.is_group() else merge_down(image, layer)
        image.set_selected_layers([merged])
        return merged

    # top to bottom; a layer inside a selected group goes with the group
    layers = [layer for layer in stacking(image.get_layers()) if layer in selected and layer.get_visible()]
    layers = [layer for layer in layers if not inside(layer, selected)]
    if len(layers) < 2:
        raise ValueError("Select at least two visible layers to merge.")
    name = layers[0].get_name()
    top = as_layer(layers[0])
    for layer in layers[1:]:
        layer = as_layer(layer)
        # right under the top one, then merged into it
        moved = image.reorder_item(layer, top.get_parent(), image.get_item_position(top) + 1)
        checked(moved, f'The layer "{layer.get_name()}" could not be moved under the top one.')
        top = merge_down(image, top)
    top.set_name(name)
    image.set_selected_layers([top])
    return top


def merge_down(image, layer):
    """GIMP's Merge Down, into the visible layer below; a message when there
    is none, or it is a group."""
    try:
        merged = image.merge_down(layer, MERGE)
    except GLib.Error:
        merged = None
    return checked(merged, "There is no visible layer below to merge with (or it is a layer group).")
