"""Edit > Fill and Edit > Stroke, Photoshop's way: the logic.

Fill: the selection (or the whole layer when there is none) filled with
the foreground or background colour, a colour, a GIMP pattern, black, 50%
gray or white through GIMP's own fill (which takes the paint mode and
opacity of the context and leaves alone what an alpha lock protects), or
with History (the layer as last saved) or Content-Aware (the local LaMa,
from the generative-fill plug-in) pasted into the selection with the mode
and opacity. Preserve Transparency locks the layer's alpha meanwhile.

Stroke: the selection's edge (or the layer's opaque shape when there is no
selection) as a ring of the given width inside, centred on or outside the
edge, filled with the colour the same way.

Pure logic, importable by the smoke test; the procedures and their
dialogs are in fill-stroke.py.
"""

from contextlib import contextmanager

import gi

gi.require_version("Gimp", "3.0")
from gi.repository import Gegl, Gimp

CONTENT_AWARE_PROC = "gimphoto-content-aware-source"

# Photoshop's Fill contents (id, label)
CONTENTS = [
    ("foreground", "Foreground Color"),
    ("background", "Background Color"),
    ("color", "Color"),
    ("content-aware", "Content-Aware"),
    ("pattern", "Pattern"),
    ("history", "History"),
    ("black", "Black"),
    ("gray", "50% Gray"),
    ("white", "White"),
]
FIXED_COLORS = {"black": "#000000", "gray": "#808080", "white": "#ffffff"}

# Photoshop's Fill and Stroke modes (id, label, GIMP layer mode)
MODES = [
    ("normal", "Normal", "NORMAL"),
    ("dissolve", "Dissolve", "DISSOLVE"),
    ("behind", "Behind", "BEHIND"),
    ("clear", "Clear", "ERASE"),
    ("darken", "Darken", "DARKEN_ONLY"),
    ("multiply", "Multiply", "MULTIPLY"),
    ("color-burn", "Color Burn", "BURN"),
    ("linear-burn", "Linear Burn", "LINEAR_BURN"),
    ("darker-color", "Darker Color", "LUMA_DARKEN_ONLY"),
    ("lighten", "Lighten", "LIGHTEN_ONLY"),
    ("screen", "Screen", "SCREEN"),
    ("color-dodge", "Color Dodge", "DODGE"),
    ("linear-dodge", "Linear Dodge (Add)", "ADDITION"),
    ("lighter-color", "Lighter Color", "LUMA_LIGHTEN_ONLY"),
    ("overlay", "Overlay", "OVERLAY"),
    ("soft-light", "Soft Light", "SOFTLIGHT"),
    ("hard-light", "Hard Light", "HARDLIGHT"),
    ("vivid-light", "Vivid Light", "VIVID_LIGHT"),
    ("linear-light", "Linear Light", "LINEAR_LIGHT"),
    ("pin-light", "Pin Light", "PIN_LIGHT"),
    ("hard-mix", "Hard Mix", "HARD_MIX"),
    ("difference", "Difference", "DIFFERENCE"),
    ("exclusion", "Exclusion", "EXCLUSION"),
    ("subtract", "Subtract", "SUBTRACT"),
    ("divide", "Divide", "DIVIDE"),
    ("hue", "Hue", "LCH_HUE"),
    ("saturation", "Saturation", "LCH_CHROMA"),
    ("color", "Color", "LCH_COLOR"),
    ("luminosity", "Luminosity", "LCH_LIGHTNESS"),
]

LOCATIONS = [("inside", "Inside"), ("center", "Center"), ("outside", "Outside")]


def layer_mode(mode_id):
    for key, _label, name in MODES:
        if key == mode_id:
            return getattr(Gimp.LayerMode, name)
    raise ValueError(f"Unknown mode {mode_id!r}")


def check_drawable(drawable):
    """A drawable Fill and Stroke can paint on, else a ValueError."""
    if drawable is None:
        raise ValueError("Select a layer, a layer mask or a channel to fill.")
    if isinstance(drawable, Gimp.Layer) and drawable.is_group():
        raise ValueError("A layer group has no pixels of its own: select a layer in it.")
    if isinstance(drawable, Gimp.Layer) and drawable.get_lock_content():
        raise ValueError(f"The pixels of {drawable.get_name()!r} are locked.")


@contextmanager
def preserved_transparency(drawable, preserve):
    """With preserve, the layer's alpha locked while painting (GIMP's fill
    and paste then leave its transparency as it was)."""
    lock = preserve and isinstance(drawable, Gimp.Layer) and drawable.has_alpha() and not drawable.get_lock_alpha()
    if lock:
        drawable.set_lock_alpha(True)
    try:
        yield
    finally:
        if lock:
            drawable.set_lock_alpha(False)


@contextmanager
def paint_context(mode, opacity):
    Gimp.context_push()
    try:
        Gimp.context_set_paint_mode(layer_mode(mode))
        Gimp.context_set_opacity(max(0.0, min(100.0, float(opacity))))
        yield
    finally:
        Gimp.context_pop()


@contextmanager
def kept_selected(image):
    """The selected layers (or channels) as they were: saving the selection
    as a channel, or adding a layer, selects that instead."""
    layers = image.get_selected_layers()
    channels = image.get_selected_channels()
    try:
        yield
    finally:
        if layers:
            image.set_selected_layers(layers)
        elif channels:
            image.set_selected_channels(channels)


def has_selection(image):
    return not Gimp.Selection.is_empty(image)


# ---------------------------------------------------------------- sources


def history_layer(image, drawable):
    """The layer as it was when the image was last saved, as a new layer at
    the top of the image (at its saved offsets). Photoshop's History
    fills from the state the image was opened in; GIMPhoto's is the saved
    file, read again."""
    if not isinstance(drawable, Gimp.Layer):
        raise ValueError("History fills a layer (not a mask or a channel).")
    gfile = image.get_file() or image.get_imported_file()
    if gfile is None or not gfile.query_exists(None):
        raise ValueError("History fills from the image as last saved: save it first.")
    saved = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, gfile)
    try:
        layers = _all_layers(saved.get_layers())
        source = next((layer for layer in layers if layer.get_name() == drawable.get_name()), None)
        if source is None and len(layers) == 1:
            source = layers[0]  # a one-layer file (a photo): that layer
        if source is None:
            raise ValueError(f"The saved file has no layer named {drawable.get_name()!r}.")
        layer = Gimp.Layer.new_from_drawable(source, image)
        layer.set_name("History")
        image.insert_layer(layer, None, 0)
        _ok, x, y = source.get_offsets()
        layer.set_offsets(x, y)
        return layer
    finally:
        saved.delete()


def _all_layers(layers):
    out = []
    for layer in layers:
        if layer.is_group():
            out.extend(_all_layers(layer.get_children()))
        else:
            out.append(layer)
    return out


def content_aware_layer(image):
    """The selection filled by the local LaMa (generative-fill plug-in), as
    a new layer at the top of the image."""
    proc = Gimp.get_pdb().lookup_procedure(CONTENT_AWARE_PROC)
    if proc is None:
        raise ValueError("Content-Aware needs GIMPhoto's generative-fill plug-in.")
    config = proc.create_config()
    config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
    config.set_property("image", image)
    result = proc.run(config)
    if result.index(0) != Gimp.PDBStatusType.SUCCESS:
        # the message comes back as a string (or a GLib.Error)
        error = result.index(1) if result.length() > 1 else None
        raise ValueError(str(getattr(error, "message", error) or "Content-Aware failed."))
    return result.index(1)


def paste_source(image, drawable, source, mode, opacity):
    """source's pixels pasted into drawable through the selection, with the
    mode and opacity, then source removed. A named buffer: the clipboard is
    left alone."""
    try:
        name = Gimp.edit_named_copy([source], "gimphoto-fill-source")
        try:
            floating = Gimp.edit_named_paste(drawable, name, True)
            floating.set_mode(layer_mode(mode))
            floating.set_opacity(max(0.0, min(100.0, float(opacity))))
            Gimp.floating_sel_anchor(floating)
        finally:
            Gimp.buffer_delete(name)
    finally:
        image.remove_layer(source)


# ------------------------------------------------------------------ fill


def fill(image, drawable, contents, color="#000000", pattern=None, mode="normal", opacity=100.0, preserve=False):
    """Edit > Fill on drawable. The caller groups the undo."""
    check_drawable(drawable)
    if contents == "content-aware" and not has_selection(image):
        raise ValueError("Content-Aware fills a selection: make one first.")
    with kept_selected(image), preserved_transparency(drawable, preserve):
        if contents in ("history", "content-aware"):
            source = history_layer(image, drawable) if contents == "history" else content_aware_layer(image)
            if not has_selection(image):
                # History without a selection: the whole layer, as Photoshop
                Gimp.Selection.all(image)
                try:
                    paste_source(image, drawable, source, mode, opacity)
                finally:
                    Gimp.Selection.none(image)
            else:
                paste_source(image, drawable, source, mode, opacity)
            return
        with paint_context(mode, opacity):
            if contents == "background":
                fill_type = Gimp.FillType.BACKGROUND
            elif contents == "pattern":
                if pattern is not None:
                    Gimp.context_set_pattern(pattern)
                fill_type = Gimp.FillType.PATTERN
            else:
                if contents != "foreground":
                    value = FIXED_COLORS.get(contents, color if contents == "color" else None)
                    if value is None:
                        raise ValueError(f"Unknown contents {contents!r}")
                    Gimp.context_set_foreground(value if isinstance(value, Gegl.Color) else Gegl.Color.new(value))
                fill_type = Gimp.FillType.FOREGROUND
            drawable.edit_fill(fill_type)


# ---------------------------------------------------------------- stroke


def ring_widths(width, location):
    """(grow, shrink) of the selection's edge, in px, for a stroke of width:
    its outer edge is the selection grown by the first, its inner edge the
    selection shrunk by the second."""
    width = max(1, int(round(width)))
    if location == "inside":
        return 0, width
    if location == "outside":
        return width, 0
    return (width + 1) // 2, width // 2


def stroke(image, drawable, width, color="#000000", location="center", mode="normal", opacity=100.0, preserve=False):
    """Edit > Stroke on drawable. The selection is left as it was; the
    caller groups the undo."""
    check_drawable(drawable)
    with kept_selected(image):
        _stroke(image, drawable, width, color, location, mode, opacity, preserve)


def _stroke(image, drawable, width, color, location, mode, opacity, preserve):
    selected = has_selection(image)
    if not selected:
        # Photoshop strokes the layer's content when nothing is selected
        if isinstance(drawable, Gimp.Layer) and drawable.has_alpha():
            image.select_item(Gimp.ChannelOps.REPLACE, drawable)
        if not has_selection(image):
            raise ValueError("Make a selection to stroke (or select a layer with transparent areas).")
    base = Gimp.Selection.save(image)
    temporary = [base]
    try:
        grow, shrink = ring_widths(width, location)
        if grow:
            Gimp.Selection.grow(image, grow)
            outer = Gimp.Selection.save(image)
            temporary.append(outer)
        else:
            outer = base
        image.select_item(Gimp.ChannelOps.REPLACE, base)
        if shrink:
            Gimp.Selection.shrink(image, shrink)
            inner = Gimp.Selection.save(image)
            temporary.append(inner)
        else:
            inner = base
        image.select_item(Gimp.ChannelOps.REPLACE, outer)
        image.select_item(Gimp.ChannelOps.SUBTRACT, inner)
        if has_selection(image):
            with preserved_transparency(drawable, preserve), paint_context(mode, opacity):
                Gimp.context_set_foreground(color if isinstance(color, Gegl.Color) else Gegl.Color.new(color))
                drawable.edit_fill(Gimp.FillType.FOREGROUND)
    finally:
        if selected:
            image.select_item(Gimp.ChannelOps.REPLACE, base)
        else:
            Gimp.Selection.none(image)
        for channel in temporary:
            image.remove_channel(channel)
