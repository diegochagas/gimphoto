#!/usr/bin/env python3
#
# Merge Layers: Photoshop's Ctrl+E, Layer > Merge Layers. Several selected
# layers become one; one layer merges down; a group merges into one layer.
# GIMPhoto's default shortcuts (defaults/photoshop-keymap.tsv) put it on
# Ctrl+E. One undo step. Logic: merge_layers.py.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.

import os
import sys

import gi

gi.require_version("Gimp", "3.0")
from gi.repository import Gimp, GLib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from merge_layers import merge_layers

PROC = "gimphoto-merge-layers"


def run(procedure, run_mode, image, drawables, config, data):
    image.undo_group_start()
    try:
        merge_layers(image)
    except (ValueError, GLib.Error) as e:
        message = getattr(e, "message", str(e))
        return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error(message))
    finally:
        image.undo_group_end()
    Gimp.displays_flush()
    return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


class MergeLayers(Gimp.PlugIn):
    def do_set_i18n(self, procname):
        return False

    def do_query_procedures(self):
        return [PROC]

    def do_create_procedure(self, name):
        procedure = Gimp.ImageProcedure.new(self, name, Gimp.PDBProcType.PLUGIN, run, None)
        procedure.set_image_types("*")
        procedure.set_attribution("GIMPhoto", "GIMPhoto contributors", "2026")
        procedure.set_sensitivity_mask(Gimp.ProcedureSensitivityMask.DRAWABLE | Gimp.ProcedureSensitivityMask.DRAWABLES)
        procedure.set_menu_label("Merge _Layers")
        blurb = "Merge the selected layers into one (one layer: merge down; a group: merge it)"
        procedure.set_documentation(blurb, blurb + " (Photoshop's Merge Layers).", name)
        procedure.add_menu_path("<Image>/Layer/[Structure]")
        return procedure


Gimp.main(MergeLayers.__gtype__, sys.argv)
