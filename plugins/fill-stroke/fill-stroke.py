#!/usr/bin/env python3
#
# Edit > Fill (Shift+F5) and Edit > Stroke, Photoshop's dialogs.
#
#   Fill...    Contents (Foreground Color, Background Color, Color,
#              Content-Aware, Pattern, History, Black, 50% Gray, White),
#              Mode, Opacity, Preserve Transparency
#   Stroke...  Width, Color, Location (Inside, Center, Outside), Mode,
#              Opacity, Preserve Transparency
#
# GIMP's own dialogs for its procedures: the last settings are remembered,
# and scripts run them with arguments. Content-Aware fills from around the
# selection with the local LaMa (the Remove tool's model, nothing
# uploaded). Logic: fill_stroke.py.
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
from gi.repository import Gegl, Gimp, GimpUi, GLib, GObject

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fill_stroke as F

FILL_PROC = "gimphoto-fill"
STROKE_PROC = "gimphoto-stroke"


def choice(entries):
    c = Gimp.Choice.new()
    for i, (key, label, *_rest) in enumerate(entries):
        c.add(key, i, label, "")
    return c


def sensitive_if(dialog, widget, prop, values):
    """widget usable only when prop is one of values (GIMP's own way, so
    the dialog follows the choice as it changes)."""
    try:
        array = Gimp.ValueArray.new(len(values))
        for value in values:
            gvalue = GObject.Value(GObject.TYPE_STRING, value)
            array.append(gvalue)
        dialog.set_sensitive_if_in(widget, None, prop, array, True)
    except Exception:  # an older GimpUi: everything stays usable
        traceback.print_exc()


def run_dialog(procedure, config, fields, title):
    GimpUi.init(procedure.get_name())
    dialog = GimpUi.ProcedureDialog(procedure=procedure, config=config, title=title)
    dialog.fill(fields)
    if procedure.get_name() == FILL_PROC:
        sensitive_if(dialog, "color", "contents", ["color"])
        sensitive_if(dialog, "pattern", "contents", ["pattern"])
    ok = dialog.run()
    dialog.destroy()
    return ok


def run(procedure, run_mode, image, drawables, config, data):
    name = procedure.get_name()
    is_fill = name == FILL_PROC
    if run_mode == Gimp.RunMode.INTERACTIVE:
        if is_fill:
            fields = ["contents", "color", "pattern", "mode", "opacity", "preserve-transparency"]
        else:
            fields = ["width", "color", "location", "mode", "opacity", "preserve-transparency"]
        if not run_dialog(procedure, config, fields, "Fill" if is_fill else "Stroke"):
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())
    get = config.get_property
    try:
        if not drawables:
            raise ValueError("Select a layer, a layer mask or a channel.")
        for drawable in drawables:
            F.check_drawable(drawable)
        if is_fill and get("contents") == "content-aware" and len(drawables) > 1:
            # one AI run fills one layer (a second would see the first fill)
            raise ValueError("Content-Aware fills one layer at a time: select one.")
        image.undo_group_start()
        try:
            for drawable in drawables:
                if is_fill:
                    F.fill(
                        image,
                        drawable,
                        get("contents"),
                        color=get("color"),
                        pattern=get("pattern"),
                        mode=get("mode"),
                        opacity=get("opacity"),
                        preserve=get("preserve-transparency"),
                    )
                else:
                    F.stroke(
                        image,
                        drawable,
                        get("width"),
                        color=get("color"),
                        location=get("location"),
                        mode=get("mode"),
                        opacity=get("opacity"),
                        preserve=get("preserve-transparency"),
                    )
        finally:
            image.undo_group_end()
    except ValueError as e:
        return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error(str(e)))
    except Exception as e:  # say what went wrong instead of a silent return
        traceback.print_exc()
        return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error(f"{type(e).__name__}: {e}"))
    Gimp.displays_flush()
    return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


class FillStroke(Gimp.PlugIn):
    def do_set_i18n(self, procname):
        return False

    def do_query_procedures(self):
        return [FILL_PROC, STROKE_PROC]

    def do_create_procedure(self, name):
        procedure = Gimp.ImageProcedure.new(self, name, Gimp.PDBProcType.PLUGIN, run, None)
        procedure.set_image_types("*")
        procedure.set_sensitivity_mask(Gimp.ProcedureSensitivityMask.DRAWABLE | Gimp.ProcedureSensitivityMask.DRAWABLES)
        procedure.set_attribution("GIMPhoto", "GIMPhoto contributors", "2026")
        flags = GObject.ParamFlags.READWRITE
        black = Gegl.Color.new("black")
        if name == FILL_PROC:
            procedure.set_menu_label("_Fill...")
            procedure.set_documentation(
                "Fill the selection, Photoshop's way",
                "Photoshop's Edit > Fill: the selection (the whole layer when there is none) "
                "filled with a colour, a pattern, the image as last saved (History) or from "
                "around it by the local AI (Content-Aware), with a mode and an opacity, "
                "optionally keeping the layer's transparency.",
                name,
            )
            procedure.add_choice_argument(
                "contents", "Co_ntents", "What to fill with", choice(F.CONTENTS), "foreground", flags
            )
            procedure.add_color_argument("color", "Color", "The colour, for Contents: Color", False, black, flags)
            procedure.add_pattern_argument(
                "pattern", "_Pattern", "The pattern, for Contents: Pattern", False, None, True, flags
            )
        else:
            procedure.set_menu_label("_Stroke...")
            procedure.set_documentation(
                "Stroke the selection, Photoshop's way",
                "Photoshop's Edit > Stroke: a line of the given width and colour along the "
                "selection's edge (the layer's shape when nothing is selected), inside, centred "
                "on or outside it, with a mode and an opacity, optionally keeping the layer's "
                "transparency.",
                name,
            )
            procedure.add_int_argument("width", "_Width", "Width of the stroke, in px", 1, 250, 3, flags)
            procedure.add_color_argument("color", "Color", "Colour of the stroke", False, black, flags)
            procedure.add_choice_argument(
                "location", "Loc_ation", "Where the stroke goes", choice(F.LOCATIONS), "center", flags
            )
        # after the label (GIMP refuses a menu path without one): GIMP's own
        # fill and stroke section of the Edit menu
        procedure.add_menu_path("<Image>/Edit/[Stroke]")
        procedure.add_choice_argument("mode", "_Mode", "Blending mode", choice(F.MODES), "normal", flags)
        procedure.add_double_argument("opacity", "Opac_ity", "Opacity, in %", 0.0, 100.0, 100.0, flags)
        procedure.add_boolean_argument(
            "preserve-transparency",
            "Preserve _Transparency",
            "Leave the layer's transparent pixels transparent",
            False,
            flags,
        )
        return procedure


Gimp.main(FillStroke.__gtype__, sys.argv)
