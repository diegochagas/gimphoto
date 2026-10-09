#!/usr/bin/env python3
#
# Fill layers: Photoshop's Layer > New Fill Layer.
#
#   Layer > New Fill Layer > Solid Color...   a layer filled with a colour
#   Layer > New Fill Layer > Gradient...      a two-colour gradient (Photoshop's
#                                             Linear, Radial, Angle, Reflected,
#                                             Diamond styles)
#   Layer > New Fill Layer > Pattern...       a GIMP pattern, tiled
#   Layer > Layer Content Options...          change a fill layer's content
#                                             (also a double click on the layer)
#
# A fill layer is a canvas-sized layer whose content is a non-destructive
# filter, masked by the selection there was; the dialog previews live and
# Cancel leaves no layer behind. Logic: fill_layers.py.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.

import os
import sys
import traceback

import gi

gi.require_version("Gimp", "3.0")
gi.require_version("GimpUi", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gimp, GimpUi, GLib, Gtk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fill_layers as F

PROCS = {
    "gimphoto-fill-layer-solid": "solid",
    "gimphoto-fill-layer-gradient": "gradient",
    "gimphoto-fill-layer-pattern": "pattern",
}
EDIT_PROC = "gimphoto-fill-layer-edit"


def hex_to_rgba(value):
    rgba = Gdk.RGBA()
    rgba.parse(value)
    return rgba


def rgba_to_hex(rgba):
    return "#%02x%02x%02x" % tuple(round(c * 255) for c in (rgba.red, rgba.green, rgba.blue))


class FillDialog:
    """The fill's settings, previewed live on the layer's filter."""

    def __init__(self, image, layer, kind, settings, title):
        self.image = image
        self.layer = layer
        self.kind = kind
        self.settings = dict(settings)
        self.pending = None
        self.dialog = GimpUi.Dialog(title=title, role="gimphoto-fill-layer")
        self.dialog.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        self.dialog.add_button("_OK", Gtk.ResponseType.OK)
        self.dialog.set_default_response(Gtk.ResponseType.OK)
        grid = Gtk.Grid(row_spacing=6, column_spacing=12, margin=12)
        self.dialog.get_content_area().pack_start(grid, True, True, 0)
        self.row = 0
        if kind == "solid":
            self.color(grid, "color", "Color")
        elif kind == "gradient":
            self.color(grid, "color1", "Start color")
            self.color(grid, "color2", "End color")
            self.choice(grid, "style", "Style", F.STYLES)
            self.spin(grid, "angle", "Angle", -360, 360, 1, "°")
            self.spin(grid, "scale", "Scale", 10, 150, 1, "%")
            self.check(grid, "reverse", "Reverse")
        else:
            name = self.settings.get("pattern", "")
            pattern = Gimp.Pattern.get_by_name(name) if name else None
            chooser = GimpUi.PatternChooser.new(None, None, pattern)

            def pattern_set(_chooser, resource, *_args):
                if resource is not None:
                    self.changed("pattern", resource.get_name())

            chooser.connect("resource-set", pattern_set)
            self.add(grid, "Pattern", chooser)
            self.spin(grid, "scale", "Scale", 10, 1000, 1, "%")
        grid.show_all()

    def add(self, grid, label, widget):
        grid.attach(Gtk.Label(label=label, xalign=1.0), 0, self.row, 1, 1)
        grid.attach(widget, 1, self.row, 1, 1)
        self.row += 1

    def color(self, grid, name, label):
        btn = Gtk.ColorButton.new_with_rgba(hex_to_rgba(self.settings[name]))
        btn.connect("color-set", lambda b: self.changed(name, rgba_to_hex(b.get_rgba())))
        self.add(grid, label, btn)

    def choice(self, grid, name, label, options):
        combo = Gtk.ComboBoxText()
        for value, text in options:
            combo.append(value, text)
        combo.set_active_id(str(self.settings[name]))
        combo.connect("changed", lambda c: self.changed(name, c.get_active_id()))
        self.add(grid, label, combo)

    def spin(self, grid, name, label, lo, hi, step, unit):
        adj = Gtk.Adjustment(
            value=float(self.settings[name]), lower=lo, upper=hi, step_increment=step, page_increment=step * 10
        )
        scale = GimpUi.SpinScale.new(adj, "", 0)
        scale.set_hexpand(True)
        adj.connect("value-changed", lambda a: self.changed(name, float(a.get_value())))
        self.add(grid, f"{label} ({unit})", scale)

    def check(self, grid, name, label):
        btn = Gtk.CheckButton(label=label)
        btn.set_active(bool(self.settings[name]))
        btn.connect("toggled", lambda b: self.changed(name, b.get_active()))
        self.add(grid, "", btn)

    def changed(self, name, value):
        self.settings[name] = value
        if self.pending is None:
            self.pending = GLib.timeout_add(80, self.preview)

    def preview(self):
        self.pending = None
        F.apply(self.layer, self.kind, self.settings)
        Gimp.displays_flush()
        return False

    def run(self):
        response = self.dialog.run()
        if self.pending:
            GLib.source_remove(self.pending)
            self.pending = None
        self.dialog.destroy()
        return response == Gtk.ResponseType.OK


def new_fill_layer(image, kind, interactive):
    """Creates the layer, previews it in the dialog, and keeps it as one
    undo step on OK (the preview changes stay out of the history)."""
    label = F.KINDS[kind][0]
    settings = F.defaults(kind)
    if not interactive:
        image.undo_group_start()
        try:
            F.create(image, kind, settings)
        finally:
            image.undo_group_end()
        return True
    # the preview, frozen: no history for it; the selection stays until OK
    image.undo_freeze()
    try:
        layer = F.create(image, kind, settings, drop_selection=False)
        Gimp.displays_flush()
        dialog = FillDialog(image, layer, kind, settings, f"New {label} Layer")
        ok = dialog.run()
        final = dialog.settings
        image.remove_layer(layer)
    finally:
        image.undo_thaw()
    if ok:
        image.undo_group_start()
        try:
            F.create(image, kind, final)
        finally:
            image.undo_group_end()
    Gimp.displays_flush()
    return True


def edit_fill_layer(image, layer):
    kind = F.kind_of(layer)
    if kind is None:
        raise ValueError("Select a fill layer (Layer > New Fill Layer).")
    f = F.fill_filter(layer, kind)
    had_filter = f is not None
    original = F.read_settings(f, kind) if had_filter else F.defaults(kind)
    image.undo_freeze()
    try:
        dialog = FillDialog(image, layer, kind, original, f"{F.KINDS[kind][0]} Options")
        ok = dialog.run()
        final = dialog.settings
        # back to how the layer was: the preview is not history
        if had_filter:
            F.apply(layer, kind, original)
        else:
            previewed = F.fill_filter(layer, kind)
            if previewed is not None:
                previewed.delete()
    finally:
        image.undo_thaw()
    # a fill whose filter was removed gets it back on OK, as one undo step
    if ok and (final != original or not had_filter):
        image.undo_group_start()
        try:
            F.apply(layer, kind, final)
        finally:
            image.undo_group_end()
    Gimp.displays_flush()
    return True


def run(procedure, run_mode, image, drawables, config, data):
    name = procedure.get_name()
    interactive = run_mode == Gimp.RunMode.INTERACTIVE
    if interactive:
        GimpUi.init(name)
    try:
        if name == EDIT_PROC:
            layers = image.get_selected_layers()
            if not layers:
                raise ValueError("Select a fill layer first.")
            edit_fill_layer(image, layers[0])
        else:
            new_fill_layer(image, PROCS[name], interactive)
    except ValueError as e:
        return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error(str(e)))
    except Exception as e:  # say what went wrong instead of a silent return
        traceback.print_exc()
        return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error(f"{type(e).__name__}: {e}"))
    return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


class FillLayers(Gimp.PlugIn):
    def do_set_i18n(self, procname):
        return False

    def do_query_procedures(self):
        return list(PROCS) + [EDIT_PROC]

    def do_create_procedure(self, name):
        procedure = Gimp.ImageProcedure.new(self, name, Gimp.PDBProcType.PLUGIN, run, None)
        # filters need RGB or grayscale pixels (not indexed colours)
        procedure.set_image_types("RGB*, GRAY*")
        procedure.set_attribution("GIMPhoto", "GIMPhoto contributors", "2026")
        if name == EDIT_PROC:
            procedure.set_sensitivity_mask(Gimp.ProcedureSensitivityMask.DRAWABLE)
            procedure.set_menu_label("Layer Content _Options...")
            blurb = "Change a fill layer's colour, gradient or pattern"
            procedure.set_documentation(blurb, blurb + " (Photoshop's Layer Content Options).", name)
            # placed by GIMPhoto's menus too (patch 0018)
        else:
            kind = PROCS[name]
            procedure.set_sensitivity_mask(
                Gimp.ProcedureSensitivityMask.DRAWABLE
                | Gimp.ProcedureSensitivityMask.DRAWABLES
                | Gimp.ProcedureSensitivityMask.NO_DRAWABLES
            )
            label = {"solid": "_Solid Color...", "gradient": "_Gradient...", "pattern": "_Pattern..."}[kind]
            procedure.set_menu_label(label)
            blurb = f"A new {F.KINDS[kind][0].lower()} layer, masked by the selection"
            procedure.set_documentation(blurb, blurb + " (Photoshop's New Fill Layer).", name)
            # no menu path: GIMPhoto's menus place the New Fill Layer submenu
            # after New Adjustment Layer (patch 0018), which a path would
            # duplicate at the end of the Layer menu
        return procedure


Gimp.main(FillLayers.__gtype__, sys.argv)
