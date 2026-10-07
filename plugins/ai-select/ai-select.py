#!/usr/bin/env python3
#
# Select Subject (AI): Photoshop's Select > Subject. The main subject of the
# image becomes the selection, in one click, with a local model: BiRefNet
# (a salient-object model: it finds the main subject anywhere in the
# picture) on the local ComfyUI. Its soft mask keeps soft edges soft.
#
#   Select > Subject, and the Properties panel's Quick Action. Shift held
#   while clicking adds to the selection, as in Photoshop; otherwise the
#   selection is replaced. One undo step.
#
# What the model sees is the visible image (all layers), as Photoshop's
# "Sample All Layers". ComfyUI is found and started by GIMPhoto's
# comfyui-service plug-in (its gimphoto-comfyui parasite); the HTTP API is
# in comfyui_api.py next to it. Without ComfyUI, a message says where to
# install it (linux-mint-setup).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.

import json
import os
import shutil
import sys
import tempfile

import gi

gi.require_version("Gimp", "3.0")
from gi.repository import Gimp, Gio, GLib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "comfyui-service"))
import comfyui_api as api
import comfyui_service as service

SUBJECT_PROC = "gimphoto-select-subject"
# Longest side sent: the model works at 1024 px, and the mask comes back at
# the size sent, scaled to the image
MAX_SIDE = 2048
DEFAULT_URL = service.url_for(service.DEFAULT_PORT)


def backend():
    """(state, url) as comfyui-service found them at startup."""
    try:
        parasite = Gimp.get_parasite(service.PARASITE)
    except Exception:
        parasite = None
    if parasite is None:
        # a run without a user interface (scripts): try the usual address
        return "unknown", DEFAULT_URL
    info = json.loads(bytes(parasite.get_data()).decode())
    return info.get("state", "unknown"), info.get("url", DEFAULT_URL)


def shift_held():
    """Shift down while the command was given (X11; False elsewhere)."""
    try:
        gi.require_version("GimpUi", "3.0")
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk, GimpUi

        # a plug-in process has no display until GTK is set up
        GimpUi.init("ai-select")
        display = Gdk.Display.get_default()
        if display is None:
            return False
        state = Gdk.Keymap.get_for_display(display).get_modifier_state()
        return bool(state & Gdk.ModifierType.SHIFT_MASK)
    except Exception:
        return False


def visible_png(image, path):
    """The visible image (all layers), at most MAX_SIDE px, as a PNG."""
    dup = image.duplicate()
    try:
        Gimp.Selection.none(dup)
        dup.flatten()
        w, h = dup.get_width(), dup.get_height()
        scale = min(1.0, MAX_SIDE / float(max(w, h)))
        if scale < 1.0:
            dup.scale(max(1, round(w * scale)), max(1, round(h * scale)))
        Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, dup, Gio.File.new_for_path(path), None)
        return dup.get_width(), dup.get_height()
    finally:
        dup.delete()


def select_from_mask(image, mask_path, operation):
    """The white part of the mask PNG, over the whole image, becomes the
    selection (operation: replace or add)."""
    selected = image.get_selected_layers()
    layer = Gimp.file_load_layer(Gimp.RunMode.NONINTERACTIVE, image, Gio.File.new_for_path(mask_path))
    image.insert_layer(layer, None, 0)
    try:
        if (layer.get_width(), layer.get_height()) != (image.get_width(), image.get_height()):
            layer.scale(image.get_width(), image.get_height(), False)
        layer.set_offsets(0, 0)
        mask = layer.create_mask(Gimp.AddMaskType.COPY)
        layer.add_mask(mask)
        image.select_item(operation, mask)
    finally:
        image.remove_layer(layer)
        if selected:
            image.set_selected_layers(selected)


def select_subject(image, operation):
    state, url = backend()
    # "missing": GIMPhoto found no comfyui service; a ComfyUI started some
    # other way may still be answering
    if state == "missing" and not api.is_up(url):
        raise api.ComfyUIError(api.missing_message("Select Subject"))

    def waiting(elapsed):
        Gimp.progress_set_text("Starting the local AI... %d s" % elapsed)
        Gimp.progress_pulse()

    def working(elapsed):
        Gimp.progress_set_text("Finding the subject (BiRefNet)... %d s, the first run loads the model" % elapsed)
        Gimp.progress_pulse()

    tmp = tempfile.mkdtemp(prefix="gimphoto-select-")
    Gimp.progress_init("Select Subject")
    try:
        if not api.wait_until_up(url, progress=waiting):
            raise api.ComfyUIError(
                f"The local AI (ComfyUI at {url}) is not answering. It starts with GIMPhoto; "
                "if it does not, see: systemctl --user status comfyui"
            )
        png = os.path.join(tmp, "image.png")
        visible_png(image, png)
        with open(png, "rb") as f:
            mask_png = api.subject(url, f.read(), progress=working)
        mask = os.path.join(tmp, "mask.png")
        with open(mask, "wb") as f:
            f.write(mask_png)
        image.undo_group_start()
        try:
            select_from_mask(image, mask, operation)
        finally:
            image.undo_group_end()
        if Gimp.Selection.is_empty(image):
            Gimp.message("Select Subject found no subject in this image.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        Gimp.progress_end()
    Gimp.displays_flush()


def run(procedure, run_mode, image, drawables, config, data):
    operation = Gimp.ChannelOps.REPLACE
    if run_mode == Gimp.RunMode.INTERACTIVE and shift_held():
        operation = Gimp.ChannelOps.ADD
    try:
        select_subject(image, operation)
    except Exception as e:
        return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error(str(e)))
    return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


class AiSelect(Gimp.PlugIn):
    def do_set_i18n(self, procname):
        return False

    def do_query_procedures(self):
        return [SUBJECT_PROC]

    def do_create_procedure(self, name):
        procedure = Gimp.ImageProcedure.new(self, name, Gimp.PDBProcType.PLUGIN, run, None)
        procedure.set_image_types("*")
        procedure.set_sensitivity_mask(
            Gimp.ProcedureSensitivityMask.DRAWABLE
            | Gimp.ProcedureSensitivityMask.DRAWABLES
            | Gimp.ProcedureSensitivityMask.NO_DRAWABLES
        )
        procedure.set_menu_label("Su_bject")
        procedure.set_documentation(
            "Select the main subject of the image (AI)",
            "Like Photoshop's Select > Subject: the main subject of the visible image "
            "becomes the selection (BiRefNet on the local ComfyUI). Shift adds to the "
            "selection.",
            name,
        )
        procedure.set_attribution("GIMPhoto", "GIMPhoto contributors", "2026")
        procedure.add_menu_path("<Image>/Select")
        return procedure


Gimp.main(AiSelect.__gtype__, sys.argv)
