#!/usr/bin/env python3
#
# GIMPhoto's AI selections (Select Subject, the Object Selection tool and
# Remove Background).
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
# Object Selection (gimphoto-object-select): run by GIMPhoto's Object
# Selection tool (a core patch: the toolbox tool) with the box the person
# dragged and the tool's selection mode; SAM 2.1 finds the object in the
# box, on the area around it at full detail.
#
# Remove Background (gimphoto-remove-background): Photoshop's Properties
# Quick Action. The selected layer's subject, found by the same BiRefNet
# model in that layer's own pixels, becomes its layer mask, not applied, as
# in Photoshop: the background is hidden, not deleted. One undo step.
#
# For the selections, what the model sees is the visible image (all
# layers), as Photoshop's "Sample All Layers". ComfyUI is found and started
# by GIMPhoto's comfyui-service plug-in (its gimphoto-comfyui parasite); the
# HTTP API is in comfyui_api.py next to it. Without ComfyUI, a message says where to
# install it (linux-mint-setup).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.

import os
import shutil
import sys
import tempfile

import gi

gi.require_version("Gimp", "3.0")
from gi.repository import Gegl, Gimp, Gio, GLib, GObject

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "comfyui-service"))
import comfyui_api as api
import gimphoto_ai as ai

SUBJECT_PROC = "gimphoto-select-subject"
OBJECT_PROC = "gimphoto-object-select"
REMOVE_BG_PROC = "gimphoto-remove-background"
# Context around the box, as a share of its larger side (at least
# MARGIN_MIN px): SAM needs to see where the object ends
MARGIN_SHARE = 0.25
MARGIN_MIN = 32
# Longest side sent: the model works at 1024 px, and the mask comes back at
# the size sent, scaled to the image
MAX_SIDE = 2048


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


def region_png(image, x, y, width, height, path):
    """The visible image inside the region, at most MAX_SIDE px, as a PNG;
    returns the scale it was sent at."""
    dup = image.duplicate()
    try:
        Gimp.Selection.none(dup)
        dup.flatten()
        dup.crop(width, height, x, y)
        scale = min(1.0, MAX_SIDE / float(max(width, height)))
        if scale < 1.0:
            dup.scale(max(1, round(width * scale)), max(1, round(height * scale)))
        Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, dup, Gio.File.new_for_path(path), None)
        return scale
    finally:
        dup.delete()


def select_from_mask(image, mask_path, operation, region=None):
    """The white part of the mask PNG becomes the selection (operation: a
    Gimp.ChannelOps), over region (x, y, width, height) or the whole image."""
    x, y, width, height = region or (0, 0, image.get_width(), image.get_height())
    selected = image.get_selected_layers()
    layer = Gimp.file_load_layer(Gimp.RunMode.NONINTERACTIVE, image, Gio.File.new_for_path(mask_path))
    image.insert_layer(layer, None, 0)
    try:
        if (layer.get_width(), layer.get_height()) != (width, height):
            layer.scale(width, height, False)
        layer.set_offsets(x, y)
        mask = layer.create_mask(Gimp.AddMaskType.COPY)
        layer.add_mask(mask)
        image.select_item(operation, mask)
    finally:
        image.remove_layer(layer)
        if selected:
            image.set_selected_layers(selected)


def select_subject(image, operation):
    url = ai.ready_url("Select Subject")

    def working(elapsed):
        Gimp.progress_set_text("Finding the subject (BiRefNet)... %d s, the first run loads the model" % elapsed)
        Gimp.progress_pulse()

    tmp = tempfile.mkdtemp(prefix="gimphoto-select-")
    Gimp.progress_init("Select Subject")
    try:
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


def layer_png(layer, path):
    """The layer's own pixels (transparent parts on white), at most MAX_SIDE
    px, as a PNG."""
    w, h = layer.get_width(), layer.get_height()
    tmp = Gimp.Image.new(w, h, Gimp.ImageBaseType.RGB)
    try:
        copy = Gimp.Layer.new_from_drawable(layer, tmp)
        tmp.insert_layer(copy, None, 0)
        copy.set_offsets(0, 0)
        if copy.get_mask():
            copy.remove_mask(Gimp.MaskApplyMode.DISCARD)
        tmp.flatten()
        scale = min(1.0, MAX_SIDE / float(max(w, h)))
        if scale < 1.0:
            tmp.scale(max(1, round(w * scale)), max(1, round(h * scale)))
        Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, tmp, Gio.File.new_for_path(path), None)
    finally:
        tmp.delete()


def set_layer_mask(image, layer, mask_path):
    """The mask PNG, scaled to the layer, becomes the layer's mask (an
    existing one is replaced). Its pixels are written into the new mask
    before it is added: a mask made from a selection would stop at the
    canvas (a layer can be larger), and copy/paste would change the
    clipboard."""
    w, h = layer.get_width(), layer.get_height()
    # loaded in its own image: in the person's (maybe indexed) image the
    # matte's greys would be turned into palette colours
    matte_image = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(mask_path))
    try:
        if (matte_image.get_width(), matte_image.get_height()) != (w, h):
            matte_image.scale(w, h)
        matte = matte_image.get_layers()[0]
        mask = layer.create_mask(Gimp.AddMaskType.WHITE)
        rect = Gegl.Rectangle.new(0, 0, w, h)
        target = mask.get_buffer()
        matte.get_buffer().copy(rect, Gegl.AbyssPolicy.NONE, target, rect)
        target.flush()
    finally:
        matte_image.delete()
    if layer.get_mask():
        layer.remove_mask(Gimp.MaskApplyMode.DISCARD)
    if not layer.has_alpha():
        layer.add_alpha()
    layer.add_mask(mask)
    layer.set_show_mask(False)
    layer.set_edit_mask(False)


def remove_background(image, layer):
    """The subject of the layer becomes its layer mask (not applied); an
    existing mask is replaced. One undo step."""
    url = ai.ready_url("Remove Background")

    def working(elapsed):
        Gimp.progress_set_text("Finding the subject (BiRefNet)... %d s, the first run loads the model" % elapsed)
        Gimp.progress_pulse()

    tmp = tempfile.mkdtemp(prefix="gimphoto-removebg-")
    Gimp.progress_init("Remove Background")
    try:
        png = os.path.join(tmp, "layer.png")
        layer_png(layer, png)
        with open(png, "rb") as f:
            mask_png = api.subject(url, f.read(), progress=working)
        mask_path = os.path.join(tmp, "mask.png")
        with open(mask_path, "wb") as f:
            f.write(mask_png)
        image.undo_group_start()
        try:
            set_layer_mask(image, layer, mask_path)
        finally:
            image.undo_group_end()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        Gimp.progress_end()
    Gimp.displays_flush()


def run_remove_background(procedure, run_mode, image, drawables, config, data):
    layers = [d for d in drawables if isinstance(d, Gimp.Layer)]
    if len(drawables) != 1 or len(layers) != 1:
        return procedure.new_return_values(
            Gimp.PDBStatusType.CALLING_ERROR, GLib.Error("Remove Background works on one layer: select only one.")
        )
    try:
        remove_background(image, layers[0])
    except Exception as e:
        return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error(str(e)))
    return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


def object_region(image, box):
    """The box with the context SAM needs around it, inside the image."""
    x, y, width, height = box
    margin = max(MARGIN_MIN, round(MARGIN_SHARE * max(width, height)))
    rx, ry = max(0, x - margin), max(0, y - margin)
    rw = min(image.get_width(), x + width + margin) - rx
    rh = min(image.get_height(), y + height + margin) - ry
    return rx, ry, rw, rh


def select_object(image, box, operation):
    """box: x, y, width, height in image pixels."""
    url = ai.ready_url("Object Selection")

    def working(elapsed):
        Gimp.progress_set_text("Finding the object (SAM 2.1)... %d s, the first run loads the model" % elapsed)
        Gimp.progress_pulse()

    region = object_region(image, box)
    rx, ry = region[:2]
    tmp = tempfile.mkdtemp(prefix="gimphoto-object-")
    Gimp.progress_init("Object Selection")
    try:
        png = os.path.join(tmp, "region.png")
        scale = region_png(image, *region, png)
        x, y, w, h = box
        local = [(x - rx) * scale, (y - ry) * scale, (x + w - rx) * scale, (y + h - ry) * scale]
        with open(png, "rb") as f:
            mask_png = api.segment(url, f.read(), [local], progress=working)
        mask = os.path.join(tmp, "mask.png")
        with open(mask, "wb") as f:
            f.write(mask_png)
        image.undo_group_start()
        try:
            select_from_mask(image, mask, operation, region)
        finally:
            image.undo_group_end()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        Gimp.progress_end()
    Gimp.displays_flush()


def run_object(procedure, config, data):
    image = config.get_property("image")
    try:
        operation = Gimp.ChannelOps(config.get_property("operation"))
        box = tuple(config.get_property(k) for k in ("x", "y", "width", "height"))
        select_object(image, box, operation)
    except Exception as e:
        return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error(str(e)))
    return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


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
        return [SUBJECT_PROC, OBJECT_PROC, REMOVE_BG_PROC]

    def do_create_procedure(self, name):
        if name == OBJECT_PROC:
            return self.object_procedure(name)
        if name == REMOVE_BG_PROC:
            return self.remove_background_procedure(name)
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

    def remove_background_procedure(self, name):
        """Layer > Remove Background, and the Properties panel's Quick Action."""
        procedure = Gimp.ImageProcedure.new(self, name, Gimp.PDBProcType.PLUGIN, run_remove_background, None)
        procedure.set_image_types("*")
        procedure.set_sensitivity_mask(Gimp.ProcedureSensitivityMask.DRAWABLE)
        procedure.set_menu_label("Remove Bac_kground")
        procedure.set_documentation(
            "Hide the background of the layer (AI)",
            "Like Photoshop's Remove Background: the subject of the selected layer "
            "becomes its layer mask (BiRefNet on the local ComfyUI), not applied, so "
            "nothing is deleted. An existing layer mask is replaced.",
            name,
        )
        procedure.set_attribution("GIMPhoto", "GIMPhoto contributors", "2026")
        procedure.add_menu_path("<Image>/Layer")
        return procedure

    def object_procedure(self, name):
        """Run by the Object Selection tool (no menu entry)."""
        procedure = Gimp.Procedure.new(self, name, Gimp.PDBProcType.PLUGIN, run_object, None)
        procedure.set_documentation(
            "Select the object inside a box (AI)",
            "Like Photoshop's Object Selection tool: the object inside the box "
            "becomes the selection, combined by the operation (SAM 2.1 on the local "
            "ComfyUI). Run by GIMPhoto's Object Selection tool.",
            name,
        )
        procedure.set_attribution("GIMPhoto", "GIMPhoto contributors", "2026")
        flags = GObject.ParamFlags.READWRITE
        procedure.add_enum_argument("run-mode", "Run mode", "", Gimp.RunMode, Gimp.RunMode.NONINTERACTIVE, flags)
        procedure.add_image_argument("image", "Image", "", False, flags)
        procedure.add_int_argument(
            "operation", "Operation", "Gimp.ChannelOps: 0 add, 1 subtract, 2 replace, 3 intersect", 0, 3, 2, flags
        )
        for key in ("x", "y", "width", "height"):
            procedure.add_int_argument(key, key, "The box, in image pixels", 0, 2**31 - 1, 0, flags)
        return procedure


Gimp.main(AiSelect.__gtype__, sys.argv)
