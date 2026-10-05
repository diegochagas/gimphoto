# Layer Style engine: Photoshop Layer Style settings -> GIMP 3 filters.
#
# A style is a dict {effect key: settings dict} in Photoshop's own terms
# (opacity %, angle deg, distance px, spread %, size px...). It is stored on
# the layer as the parasite "gimp-setup-layer-style" (JSON), and rendered as
# non-destructive filters named "Layer Style: <effect>", appended in
# Photoshop's stacking order (fills first, outer effects last) every time
# the style changes. Filters the user added themselves are left alone.
#
# Every effect is drawn by a GEGL operation GIMP already has: gegl:dropshadow
# (Drop Shadow, Outer Glow), gegl:inner-glow (Inner Shadow, Inner Glow,
# inside stroke), gegl:styles (outside stroke; LinuxBeaver's Text Styling),
# gegl:bevel, gegl:color-overlay, and GIMPhoto's own gimphoto:gradient-overlay
# and gimphoto:pattern-overlay (gegl/ in GIMPhoto's repository). Photoshop's
# Satin and Contours have no GEGL counterpart.

import json
import math
import os

import gi

gi.require_version("Gimp", "3.0")
gi.require_version("Gegl", "0.4")
from gi.repository import Gegl, Gimp, Gio

PARASITE = "gimp-setup-layer-style"
PREFIX = "Layer Style: "

# key, label, in Photoshop's Layer Style list order
EFFECTS = [
    ("bevel", "Bevel & Emboss"),
    ("stroke", "Stroke"),
    ("inner_shadow", "Inner Shadow"),
    ("inner_glow", "Inner Glow"),
    ("color_overlay", "Color Overlay"),
    ("gradient_overlay", "Gradient Overlay"),
    ("pattern_overlay", "Pattern Overlay"),
    ("outer_glow", "Outer Glow"),
    ("drop_shadow", "Drop Shadow"),
]
LABELS = dict(EFFECTS)

# GEGL operations each effect needs; the gimphoto: ones ship with GIMPhoto.
REQUIRES = {
    "drop_shadow": ["gegl:dropshadow"],
    "outer_glow": ["gegl:dropshadow"],
    "inner_shadow": ["gegl:inner-glow"],
    "inner_glow": ["gegl:inner-glow"],
    "stroke": ["gegl:styles", "gegl:inner-glow"],
    "bevel": ["gegl:bevel"],
    "color_overlay": ["gegl:color-overlay"],
    "gradient_overlay": ["gimphoto:gradient-overlay"],
    "pattern_overlay": ["gimphoto:pattern-overlay"],
}
_AVAILABLE = None


def missing_operations(key):
    """GEGL operations effect key needs that this GIMP does not have."""
    global _AVAILABLE
    if _AVAILABLE is None:
        _AVAILABLE = set(Gimp.DrawableFilter.operation_get_available())
    return [op for op in REQUIRES.get(key, []) if op not in _AVAILABLE]


# order the filters are applied in: what is painted inside the layer first,
# then the bevel and the stroke on top, then what spreads outside it
RENDER_ORDER = [
    # Photoshop stacks Color Overlay over Gradient Overlay over Pattern
    # Overlay: the first one added is the lowest
    "pattern_overlay",
    "gradient_overlay",
    "color_overlay",
    "inner_glow",
    "inner_shadow",
    "bevel",
    "stroke",
    "outer_glow",
    "drop_shadow",
]

# Photoshop's defaults for a newly enabled effect
DEFAULTS = {
    "drop_shadow": {"color": "#000000", "opacity": 35, "angle": 120, "distance": 5, "spread": 0, "size": 5},
    "inner_shadow": {"color": "#000000", "opacity": 35, "angle": 120, "distance": 5, "choke": 0, "size": 5},
    "outer_glow": {"color": "#ffffbe", "opacity": 35, "spread": 0, "size": 5},
    "inner_glow": {"color": "#ffffbe", "opacity": 35, "choke": 0, "size": 5},
    "stroke": {"size": 3, "position": "outside", "color": "#ff0000", "opacity": 100},
    "bevel": {
        "style": "inner",
        "technique": "smooth",
        "depth": 100,
        "direction": "up",
        "size": 5,
        "angle": 120,
        "altitude": 30,
        "highlight_mode": "hardlight",
    },
    "color_overlay": {"color": "#ff0000", "blend": "normal", "opacity": 100},
    "gradient_overlay": {
        "color1": "#000000",
        "color2": "#ffffff",
        "blend": "normal",
        "opacity": 100,
        "style": "linear",
        "angle": 90,
        "scale": 100,
        "reverse": False,
    },
    # pattern: a GIMP pattern's name, or image: any image file (wins)
    "pattern_overlay": {"pattern": "", "image": "", "scale": 100, "blend": "normal", "opacity": 100},
}

BLEND_MODES = [
    ("normal", "Normal", Gimp.LayerMode.NORMAL),
    ("multiply", "Multiply", Gimp.LayerMode.MULTIPLY),
    ("screen", "Screen", Gimp.LayerMode.SCREEN),
    ("overlay", "Overlay", Gimp.LayerMode.OVERLAY),
    ("soft_light", "Soft Light", Gimp.LayerMode.SOFTLIGHT),
    ("hard_light", "Hard Light", Gimp.LayerMode.HARDLIGHT),
    ("color_dodge", "Color Dodge", Gimp.LayerMode.DODGE),
    ("color_burn", "Color Burn", Gimp.LayerMode.BURN),
    ("darken", "Darken", Gimp.LayerMode.DARKEN_ONLY),
    ("lighten", "Lighten", Gimp.LayerMode.LIGHTEN_ONLY),
    ("difference", "Difference", Gimp.LayerMode.DIFFERENCE),
    ("hue", "Hue", Gimp.LayerMode.LCH_HUE),
    ("saturation", "Saturation", Gimp.LayerMode.LCH_CHROMA),
    ("color", "Color", Gimp.LayerMode.LCH_COLOR),
    ("luminosity", "Luminosity", Gimp.LayerMode.LCH_LIGHTNESS),
]
GIMP_MODE = {k: m for k, _l, m in BLEND_MODES}


# --------------------------------------------------------------- storage


def parasite_text(item, name):
    try:
        if name not in item.get_parasite_list():
            return ""
        return bytes(b & 0xFF for b in item.get_parasite(name).get_data()).decode("utf8", "replace")
    except Exception:
        return ""


def read_style(layer):
    """The layer's style, minus effects whose filters were removed meanwhile
    (e.g. deleted from the Layers panel's fx menu)."""
    try:
        style = json.loads(parasite_text(layer, PARASITE) or "{}")
    except ValueError:
        style = {}
    present = {f.get_name()[len(PREFIX) :] for f in layer.get_filters() if f.get_name().startswith(PREFIX)}
    out = {}
    for key, settings in style.items():
        if key in LABELS:
            settings = {**DEFAULTS[key], **settings}
            if settings.get("enabled") and LABELS[key] not in present:
                settings["enabled"] = False
            out[key] = settings
    return out


def write_style(layer, style):
    data = {k: v for k, v in style.items() if k in LABELS}
    if not any(v.get("enabled") for v in data.values()):
        if PARASITE in layer.get_parasite_list():
            layer.detach_parasite(PARASITE)
        return
    layer.attach_parasite(Gimp.Parasite.new(PARASITE, 1, list(json.dumps(data).encode("utf8"))))


# -------------------------------------------------------------- geometry


def offset(angle, distance):
    """Photoshop's light angle (where the light comes from, counter-clockwise
    from 3 o'clock) and distance -> the x, y a shadow moves (y down)."""
    a = math.radians(angle)
    return -distance * math.cos(a), distance * math.sin(a)


def blur(size, grow):
    """Photoshop's Size includes the Spread/Choke part; what is left is the
    soft edge, about two gaussian standard deviations wide."""
    return max(0.0, (size - grow) / 2.0)


# ---------------------------------------------------------------- filters


def color(value):
    return Gegl.Color.new(value or "#000000")


def filter_specs(layer, key, s):
    """[(operation, {property: value}, blend key, opacity 0..1)] for one
    effect. Opacity goes on the filter where the operation has none."""
    op = []
    if key == "drop_shadow":
        x, y = offset(s["angle"], s["distance"])
        grow = s["size"] * s["spread"] / 100.0
        op.append(
            (
                "gegl:dropshadow",
                {
                    "x": x,
                    "y": y,
                    "radius": blur(s["size"], grow),
                    "grow-shape": "circle",
                    "grow-radius": grow,
                    "color": color(s["color"]),
                    "opacity": s["opacity"] / 100.0,
                },
                "normal",
                1.0,
            )
        )
    elif key == "outer_glow":
        grow = s["size"] * s["spread"] / 100.0
        op.append(
            (
                "gegl:dropshadow",
                {
                    "x": 0.0,
                    "y": 0.0,
                    "radius": blur(s["size"], grow),
                    "grow-shape": "circle",
                    "grow-radius": grow,
                    "color": color(s["color"]),
                    # a glow is lighter than a shadow of the same opacity
                    "opacity": min(2.0, s["opacity"] / 100.0 * 1.5),
                },
                "normal",
                1.0,
            )
        )
    elif key in ("inner_shadow", "inner_glow"):
        x, y = offset(s["angle"], s["distance"]) if key == "inner_shadow" else (0.0, 0.0)
        grow = s["size"] * s["choke"] / 100.0
        op.append(
            (
                "gegl:inner-glow",
                {
                    "x": x,
                    "y": y,
                    "radius": max(0.5, blur(s["size"], grow)),
                    "grow-radius": grow,
                    "value": color(s["color"]),
                    "opacity": s["opacity"] / 100.0,
                },
                "normal",
                1.0,
            )
        )
    elif key == "stroke":
        size, pos, opacity = float(s["size"]), s["position"], s["opacity"] / 100.0
        outside = size if pos == "outside" else size / 2.0 if pos == "center" else 0.0
        inside = size if pos == "inside" else size / 2.0 if pos == "center" else 0.0
        if inside > 0:
            op.append(
                (
                    "gegl:inner-glow",
                    {
                        "x": 0.0,
                        "y": 0.0,
                        "radius": 0.5,
                        "grow-radius": inside,
                        "value": color(s["color"]),
                        "opacity": 2.0,
                    },
                    "normal",
                    opacity,
                )
            )
        if outside > 0:
            op.append(
                (
                    "gegl:styles",
                    {
                        "enableoutline": True,
                        "outline": outside,
                        "outline-color": color(s["color"]),
                        "outline-opacity": opacity,
                        "outline-x": 0.0,
                        "outline-y": 0.0,
                        "outline-blur": 0.0,
                        "shadow-opacity": 0.0,
                        "enablebevel": False,
                        "enableinnerglow": False,
                        "enableimage": False,
                        "color-fill": color("#ffffff"),
                        "color-policy": "multiply",
                    },
                    "normal",
                    1.0,
                )
            )
    elif key == "bevel":
        azimuth = s["angle"] + (180 if s["direction"] == "down" else 0)
        # gegl:bevel's radius is 1-8 px and its depth 1-100 (40 looks like
        # Photoshop's default 100%); Smooth = bump, Chisel = chamfer
        chisel = s["technique"] == "chisel"
        op.append(
            (
                "gegl:bevel",
                {
                    "type": "chamfer" if chisel else "bump",
                    "metric": "euclidean",
                    "blendmode": s.get("highlight_mode", "hardlight"),
                    "radius": float(s["size"]) * 0.6,
                    "elevation": float(s["altitude"]),
                    "depth": int(round(s["depth"] * 0.4)),
                    "azimuth": float(azimuth % 360),
                },
                "normal",
                1.0,
            )
        )
    elif key == "color_overlay":
        op.append(("gegl:color-overlay", {"value": color(s["color"])}, s["blend"], s["opacity"] / 100.0))
    elif key == "gradient_overlay":
        op.append(
            (
                "gimphoto:gradient-overlay",
                {
                    "color1": color(s["color1"]),
                    "color2": color(s["color2"]),
                    "style": s.get("style", "linear"),
                    "angle": float(s["angle"]),
                    "scale": float(s["scale"]),
                    "reverse": bool(s["reverse"]),
                },
                s["blend"],
                s["opacity"] / 100.0,
            )
        )
    elif key == "pattern_overlay":
        path = s.get("image") or pattern_file(s.get("pattern"))
        if path:
            op.append(
                (
                    "gimphoto:pattern-overlay",
                    {"path": path, "scale": float(s.get("scale", 100))},
                    s["blend"],
                    s["opacity"] / 100.0,
                )
            )
    return op


GRADIENT_STYLES = [
    ("linear", "Linear"),
    ("radial", "Radial"),
    ("angle", "Angle"),
    ("reflected", "Reflected"),
    ("diamond", "Diamond"),
]


def pattern_file(name):
    """A GIMP pattern as a PNG file gimphoto:pattern-overlay can read, in the
    profile's cache (gimphoto-patterns/), made once per pattern; None if
    there is no such pattern."""
    if not name:
        return None
    pattern = Gimp.Pattern.get_by_name(name)
    if pattern is None:
        return None
    folder = os.path.join(Gimp.directory(), "gimphoto-patterns")
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    path = os.path.join(folder, safe + ".png")
    if not os.path.exists(path):
        os.makedirs(folder, exist_ok=True)
        _ok, width, height, _bpp = pattern.get_info()
        image = Gimp.Image.new(width, height, Gimp.ImageBaseType.RGB)
        try:
            layer = Gimp.Layer.new(
                image, "pattern", width, height, Gimp.ImageType.RGBA_IMAGE, 100, Gimp.LayerMode.NORMAL
            )
            image.insert_layer(layer, None, 0)
            Gimp.context_push()
            try:
                Gimp.context_set_pattern(pattern)
                layer.edit_fill(Gimp.FillType.PATTERN)
            finally:
                Gimp.context_pop()
            Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, Gio.File.new_for_path(path), None)
        finally:
            image.delete()
    return path


_RANGES = {}


def _range(op, prop):
    """(minimum, maximum) of a numeric operation property, else None."""
    if op not in _RANGES:
        ranges = {}
        specs = Gimp.DrawableFilter.operation_get_pspecs(op)
        for i in range(specs.length() if specs else 0):
            p = specs.index(i)
            lo, hi = getattr(p, "minimum", None), getattr(p, "maximum", None)
            if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
                ranges[p.name] = (lo, hi)
        _RANGES[op] = ranges
    return _RANGES[op].get(prop)


def _set(op, config, prop, value):
    rng = _range(op, prop)
    if rng and isinstance(value, (int, float)) and not isinstance(value, bool):
        value = type(value)(max(rng[0], min(rng[1], value)))
    try:
        config.set_property(prop, value)
    except (TypeError, ValueError):
        # enum values differ between versions of the LinuxBeaver ops: keep
        # the operation's default rather than fail the whole style
        pass


def remove_filters(layer):
    for f in layer.get_filters():
        if f.get_name().startswith(PREFIX):
            f.delete()


def apply_style(layer, style):
    """Replace the layer's Layer Style filters by those of style."""
    remove_filters(layer)
    # Shadows, glows and outside strokes paint where the layer is transparent;
    # a layer without an alpha channel (an image opened from a JPEG or an
    # opaque PNG) would show them as solid black instead. Photoshop layers
    # always have transparency: give the layer an alpha channel, as Layer >
    # Transparency > Add Alpha Channel does.
    if any(s.get("enabled") for s in style.values()) and not layer.has_alpha():
        layer.add_alpha()
    # GIMP crops a filter to the selection there is when it is added, and
    # keeps that crop after the selection changes: with a selection, the
    # effects showed only inside it, or not at all. Photoshop's layer styles
    # ignore the selection; set it aside while the effects are added.
    image = layer.get_image()
    saved = None
    if not Gimp.Selection.is_empty(image):
        saved = Gimp.Selection.save(image)
        Gimp.Selection.none(image)
    try:
        for key in RENDER_ORDER:
            s = style.get(key)
            if not s or not s.get("enabled") or missing_operations(key):
                continue
            for op, props, blend, opacity in filter_specs(layer, key, {**DEFAULTS[key], **s}):
                f = Gimp.DrawableFilter.new(layer, op, PREFIX + LABELS[key])
                if f is None:
                    continue
                cfg = f.get_config()
                for prop, value in props.items():
                    _set(op, cfg, prop, value)
                f.set_blend_mode(GIMP_MODE.get(blend, Gimp.LayerMode.NORMAL))
                f.set_opacity(max(0.0, min(1.0, opacity)))
                f.update()
                layer.append_filter(f)
    finally:
        if saved is not None:
            image.select_item(Gimp.ChannelOps.REPLACE, saved)
            image.remove_channel(saved)
    write_style(layer, style)
