"""Fill layers: Photoshop's Layer > New Fill Layer > Solid Color / Gradient /
Pattern, as GIMP layers whose content is a non-destructive filter.

A fill layer is a canvas-sized opaque layer carrying one GIMP filter that
paints its content: ``gegl:color-overlay`` (Solid Color; ``gegl:color`` is
not among the operations GIMP allows as a filter), GIMPhoto's
``gimphoto:gradient-overlay`` (Gradient, Photoshop's five styles) or
``gimphoto:pattern-overlay`` (Pattern, a GIMP pattern). The filter is what
the canvas shows and what the XCF keeps, so the fill is edited again at
any time; a mask (from the selection when there is one) limits it, as in
Photoshop. The parasite ``gimphoto-fill`` names the kind, for the
Properties panel, the double click and Layer > Layer Content Options.

Pure logic, importable by the smoke test; the dialogs are in fill-layers.py.
"""

import os
import sys

import gi

gi.require_version("Gimp", "3.0")
gi.require_version("Babl", "0.1")
from gi.repository import Babl, Gegl, Gimp

# the pattern cache of the layer-style plug-in, next door
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "layer-style"))
from layer_style_engine import pattern_cache_name, pattern_file

PARASITE = "gimphoto-fill"

KINDS = {
    "solid": ("Color Fill", "gegl:color-overlay"),
    "gradient": ("Gradient Fill", "gimphoto:gradient-overlay"),
    "pattern": ("Pattern Fill", "gimphoto:pattern-overlay"),
}

STYLES = [
    ("linear", "Linear"),
    ("radial", "Radial"),
    ("angle", "Angle"),
    ("reflected", "Reflected"),
    ("diamond", "Diamond"),
]


def color_hex(color):
    """``#rrggbb`` in sRGB, as ``Gegl.Color.new`` reads it back
    (``get_rgba()`` would give linear values: a darker colour)."""
    data = color.get_bytes(Babl.format("R'G'B'A u8")).get_data()
    return "#%02x%02x%02x" % tuple(data[:3])


def defaults(kind):
    """Photoshop's starting values: the foreground colour, a foreground to
    background gradient, the current pattern."""
    fg = color_hex(Gimp.context_get_foreground())
    if kind == "solid":
        return {"color": fg}
    if kind == "gradient":
        return {
            "color1": fg,
            "color2": color_hex(Gimp.context_get_background()),
            "style": "linear",
            "angle": 90.0,
            "scale": 100.0,
            "reverse": False,
        }
    pattern = Gimp.context_get_pattern()
    return {"pattern": pattern.get_name() if pattern else "", "scale": 100.0}


def configure(filter_, kind, settings):
    """Puts ``settings`` into the filter's configuration (the filter shows
    them once ``update()`` is called or the filter is appended)."""
    cfg = filter_.get_config()
    if kind == "solid":
        cfg.set_property("value", Gegl.Color.new(settings["color"]))
    elif kind == "gradient":
        cfg.set_property("color1", Gegl.Color.new(settings["color1"]))
        cfg.set_property("color2", Gegl.Color.new(settings["color2"]))
        cfg.set_property("style", settings.get("style", "linear"))
        cfg.set_property("angle", float(settings.get("angle", 90.0)))
        cfg.set_property("scale", float(settings.get("scale", 100.0)))
        cfg.set_property("reverse", bool(settings.get("reverse", False)))
    else:
        path = pattern_file(settings.get("pattern", ""))
        if path:
            cfg.set_property("path", path)
        cfg.set_property("scale", float(settings.get("scale", 100.0)))


def read_settings(filter_, kind):
    """The settings a fill layer's filter holds, for the dialog."""
    cfg = filter_.get_config()
    if kind == "solid":
        return {"color": color_hex(cfg.get_property("value"))}
    if kind == "gradient":
        style = cfg.get_property("style")
        return {
            "color1": color_hex(cfg.get_property("color1")),
            "color2": color_hex(cfg.get_property("color2")),
            "style": getattr(style, "value_nick", str(style)),
            "angle": float(cfg.get_property("angle")),
            "scale": float(cfg.get_property("scale")),
            "reverse": bool(cfg.get_property("reverse")),
        }
    path = cfg.get_property("path") or ""
    return {"pattern": pattern_name(path), "scale": float(cfg.get_property("scale"))}


def pattern_name(path):
    """The GIMP pattern whose cache file is ``path`` (the file name is the
    pattern's name with spaces and punctuation replaced), or ""."""
    cached = os.path.splitext(os.path.basename(path))[0]
    if not cached:
        return ""
    for pattern in Gimp.patterns_get_list(""):
        if pattern_cache_name(pattern.get_name()) == cached:
            return pattern.get_name()
    return ""


def kind_of(layer):
    """'solid', 'gradient' or 'pattern' for a fill layer, else None."""
    parasite = layer.get_parasite(PARASITE)
    if parasite is None:
        return None
    kind = bytes(parasite.get_data()).decode("utf-8", "replace").rstrip("\0")
    return kind if kind in KINDS else None


def fill_filter(layer, kind):
    """The filter that paints the fill, or None if it was removed."""
    label = KINDS[kind][0]
    for f in layer.get_filters():
        if f.get_name() == label:
            return f
    return None


def _all_names(layers):
    for layer in layers:
        yield layer.get_name()
        if layer.is_group():
            yield from _all_names(layer.get_children())


def _next_name(image, label):
    names = set(_all_names(image.get_layers()))
    n = 1
    while f"{label} {n}" in names:
        n += 1
    return f"{label} {n}"


def create(image, kind, settings=None, drop_selection=True):
    """A new fill layer above the selected layer, masked by the selection
    (which is then dropped, as Photoshop does, unless ``drop_selection`` is
    False: the dialog's preview keeps it for Cancel), with its filter.
    Returns the layer; the caller groups the undo."""
    label, op = KINDS[kind]
    if settings is None:
        settings = defaults(kind)
    width, height = image.get_width(), image.get_height()
    # the image's own type (GIMP refuses an RGB layer in a grayscale image)
    gray = image.get_base_type() == Gimp.ImageBaseType.GRAY
    layer_type = Gimp.ImageType.GRAYA_IMAGE if gray else Gimp.ImageType.RGBA_IMAGE
    layer = Gimp.Layer.new(image, _next_name(image, label), width, height, layer_type, 100.0, Gimp.LayerMode.NORMAL)
    selected = image.get_selected_layers()
    parent, position = None, 0
    if selected:
        parent, position = selected[0].get_parent(), image.get_item_position(selected[0])
    image.insert_layer(layer, parent, position)
    selection = not Gimp.Selection.is_empty(image)
    try:
        # opaque, so the overlay operations (which keep the layer's alpha) paint
        # everywhere; the mask is what limits the fill
        layer.fill(Gimp.FillType.WHITE)
        mask_type = Gimp.AddMaskType.SELECTION if selection else Gimp.AddMaskType.WHITE
        layer.add_mask(layer.create_mask(mask_type))

        # saved in the XCF and undone with the layer (without UNDOABLE, GIMP
        # records "Can't undo Attach Parasite to Item" on an attached layer)
        flags = Gimp.PARASITE_PERSISTENT | Gimp.PARASITE_UNDOABLE
        layer.attach_parasite(Gimp.Parasite.new(PARASITE, flags, list(kind.encode("utf-8"))))

        # raises when GIMP has no such operation (GIMPhoto's own ones missing)
        f = Gimp.DrawableFilter.new(layer, op, label)
        configure(f, kind, settings)
        f.update()
        layer.append_filter(f)
    except Exception:
        image.remove_layer(layer)  # no half-made layer left behind
        raise
    if selection and drop_selection:
        Gimp.Selection.none(image)
    image.set_selected_layers([layer])
    layer.set_edit_mask(True)
    return layer


def apply(layer, kind, settings):
    """Changes a fill layer's content."""
    f = fill_filter(layer, kind)
    if f is None:
        f = Gimp.DrawableFilter.new(layer, KINDS[kind][1], KINDS[kind][0])
        configure(f, kind, settings)
        f.update()
        layer.append_filter(f)
    else:
        configure(f, kind, settings)
        f.update()
