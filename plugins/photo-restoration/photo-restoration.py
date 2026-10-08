#!/usr/bin/env python3
#
# Photo Restoration (local AI): Photoshop's Filters > Neural Filters >
# Photo Restoration, for scanned photo prints.
#
# A local model redraws the whole picture with the damage painted over:
# white and brown blotches, flakes, stains, scratches, creases, specks, or,
# with "Chemical burns", gold/orange flakes and rusty blotches. Its pixels
# are then kept ONLY where the print was damaged (restore_mask.py next to
# this file): the result is a new layer "Photo Restoration" above the
# selected one, whose layer mask is the damage the model repaired, over the
# untouched scan; one undo step. Paint the mask black where the model
# changed something it should not have (a face, an expression) and white
# where damage was missed: the layer holds the model's whole picture,
# colour-matched to the scan.
#
# With a selection, only damage inside the selection is repaired.
#
# From gimp-setup's AI Restore Photo (github.com/diegochagas/gimp-setup,
# assets/plug-ins/ai-restore-photo, MIT): the same method and mask
# (restore_mask.py, vendored unchanged). In GIMPhoto: Photoshop's menu
# place, GIMPhoto's ComfyUI (found and started by the comfyui-service
# plug-in, its gimphoto-comfyui parasite), gimp-setup's ComfyUI client from
# plugins/comfyui-service, and numpy/scipy/Pillow shipped with the app
# (python-wheels.tsv).
#
# Models: FLUX.2 klein (fast, default) or Qwen-Image-Edit (slower; better on
# chemical burns, but it tends to repaint faces).
#
# Modern Photo (same menu, procedure gimphoto-modern-photo): the old photo
# redrawn as if taken today with a modern phone camera (sharp, clean, true
# colours; black and white comes back in colour unless asked not to), as a
# new layer "Modern Photo" above the photo. The whole layer is the model's:
# faces can change, so its mask can be painted black to bring the original
# back. Prompt and black-and-white check: modern_photo.py.
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
gi.require_version("Gegl", "0.4")
from gi.repository import Gegl, Gimp, Gio, GLib, GObject

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "comfyui-service"))
import comfyui_client as client
import gimphoto_ai as ai
import modern_photo
import restore_mask

PROC = "gimphoto-photo-restoration"
LAYER_NAME = "Photo Restoration"
MODERN_PROC = "gimphoto-modern-photo"
MODERN_LAYER_NAME = "Modern Photo"
# side of the thumbnail the black-and-white check looks at
SAMPLE = 64


# ------------------------------------------------------------- gimp helpers


def export_flat(image, path, sample=0):
    """The visible image (all layers, canvas size) as a PNG. With `sample`,
    also returns its pixels shrunk to sample x sample, as 8-bit RGB bytes."""
    dup = image.duplicate()
    try:
        Gimp.Selection.none(dup)
        dup.flatten()
        Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, dup, Gio.File.new_for_path(path), None)
        if not sample:
            return None
        dup.scale(sample, sample)
        buffer = dup.get_layers()[0].get_buffer()
        rect = Gegl.Rectangle.new(0, 0, sample, sample)
        return bytes(buffer.get(rect, 1.0, "R'G'B' u8", Gegl.AbyssPolicy.CLAMP))
    finally:
        dup.delete()


def add_result_layer(image, path, name, mask_type=Gimp.AddMaskType.ALPHA_TRANSFER):
    """The model's picture above the selected layer, with a layer mask (by
    default its alpha: the damage repaired), so the mask can be painted to
    add or drop areas."""
    selected = image.get_selected_layers()
    parent, position = None, 0
    if selected:
        parent, position = selected[0].get_parent(), image.get_item_position(selected[0])
    layer = Gimp.file_load_layer(Gimp.RunMode.NONINTERACTIVE, image, Gio.File.new_for_path(path))
    layer.set_name(name)
    image.insert_layer(layer, parent, position)
    layer.set_offsets(0, 0)
    mask = layer.create_mask(mask_type)
    layer.add_mask(mask)
    return layer, mask


def limit_to_selection(image, mask):
    """Black out the layer mask outside the selection."""
    sel = Gimp.Selection.save(image)
    Gimp.context_push()
    try:
        Gimp.Selection.invert(image)
        Gimp.context_set_foreground(Gegl.Color.new("black"))
        mask.edit_fill(Gimp.FillType.FOREGROUND)
    finally:
        Gimp.context_pop()
        image.select_item(Gimp.ChannelOps.REPLACE, sel)
        image.remove_channel(sel)


def restore(image, model, damage, threshold, min_area):
    _ok, has_selection, _x1, _y1, _x2, _y2 = Gimp.Selection.bounds(image)
    tmpdir = tempfile.mkdtemp(prefix="gimphoto-restore-")
    Gimp.progress_init("Photo Restoration")
    try:
        url = ai.ready_url("Photo Restoration")
        scan = os.path.join(tmpdir, "scan.png")
        raw = os.path.join(tmpdir, "model.png")
        repaired = os.path.join(tmpdir, "repaired.png")

        Gimp.progress_set_text("Preparing the photo...")
        export_flat(image, scan)
        with open(scan, "rb") as f:
            scan_png = f.read()

        def progress(elapsed):
            Gimp.progress_set_text(
                "Repairing the photo (%s)... %d s, the first run loads the model" % (client.MODELS[model], elapsed)
            )
            Gimp.progress_pulse()

        result = client.restore(model, scan_png, burns=(damage == "burns"), url=url, progress=progress)
        with open(raw, "wb") as f:
            f.write(result)

        Gimp.progress_set_text("Finding the damage the model repaired...")
        Gimp.progress_pulse()
        regions, share = restore_mask.process(scan, raw, repaired, threshold, min_area)

        image.undo_group_start()
        try:
            layer, mask = add_result_layer(image, repaired, LAYER_NAME)
            if has_selection:
                limit_to_selection(image, mask)
            image.set_selected_layers([layer])
        finally:
            image.undo_group_end()
        Gimp.displays_flush()
        if regions == 0:
            Gimp.message(
                "The model changed nothing above the sensitivity threshold, so the layer mask is "
                'empty. Lower "Sensitivity threshold" or paint the mask white where you want the repair.'
            )
        elif share > 0.5:
            Gimp.message(
                "The repair covers %d%% of the photo. Check faces and people: paint the "
                '"%s" layer mask black where the model invented or changed something.' % (share * 100, LAYER_NAME)
            )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        Gimp.progress_end()


def modernize(image, model, black_and_white):
    _ok, has_selection, _x1, _y1, _x2, _y2 = Gimp.Selection.bounds(image)
    tmpdir = tempfile.mkdtemp(prefix="gimphoto-modern-")
    Gimp.progress_init("Modern Photo")
    try:
        url = ai.ready_url("Modern Photo")
        photo = os.path.join(tmpdir, "photo.png")
        modern = os.path.join(tmpdir, "modern.png")

        Gimp.progress_set_text("Preparing the photo...")
        pixels = export_flat(image, photo, SAMPLE)
        monochrome = modern_photo.is_monochrome(pixels)
        with open(photo, "rb") as f:
            photo_png = f.read()

        def progress(elapsed):
            Gimp.progress_set_text(
                "Taking the photo again (%s)... %d s, the first run loads the model" % (client.MODELS[model], elapsed)
            )
            Gimp.progress_pulse()

        result = modern_photo.modernize(
            model, photo_png, monochrome, black_and_white == "keep", url=url, progress=progress
        )
        with open(modern, "wb") as f:
            f.write(result)

        image.undo_group_start()
        try:
            # black and white scans often open in Grayscale mode, where the
            # colour result would turn grey again
            if image.get_base_type() != Gimp.ImageBaseType.RGB:
                image.convert_rgb()
            layer, mask = add_result_layer(image, modern, MODERN_LAYER_NAME, Gimp.AddMaskType.WHITE)
            if has_selection:
                limit_to_selection(image, mask)
            image.set_selected_layers([layer])
        finally:
            image.undo_group_end()
        Gimp.displays_flush()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        Gimp.progress_end()


# ------------------------------------------------------------- plug-in


def run(procedure, run_mode, image, drawables, config, data):
    if run_mode == Gimp.RunMode.INTERACTIVE:
        gi.require_version("GimpUi", "3.0")
        from gi.repository import GimpUi

        GimpUi.init(procedure.get_name())
        dialog = GimpUi.ProcedureDialog(procedure=procedure, config=config)
        dialog.fill(None)
        if not dialog.run():
            dialog.destroy()
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())
        dialog.destroy()

    try:
        if procedure.get_name() == MODERN_PROC:
            modernize(image, config.get_property("model"), config.get_property("black-and-white"))
        else:
            restore(
                image,
                config.get_property("model"),
                config.get_property("damage"),
                config.get_property("threshold"),
                config.get_property("min-area"),
            )
    except Exception as e:
        return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error(str(e)))
    return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


def add_model_argument(procedure, flags):
    model = Gimp.Choice.new()
    model.add("klein", 0, "FLUX.2 klein (local, fast)", "")
    model.add("qwen", 1, "Qwen-Image-Edit (local, slower)", "")
    procedure.add_choice_argument("model", "_Model", "Local AI model to use", model, "klein", flags)


def add_photo_restoration(procedure, name, flags):
    procedure.set_attribution("GIMPhoto", "GIMPhoto and gimp-setup contributors", "2026")
    procedure.set_menu_label("_Photo Restoration…")
    procedure.set_documentation(
        "Repair a damaged photo print with a local AI model",
        "Like Photoshop's Photo Restoration neural filter: blotches, flakes, stains, "
        "scratches and specks of a scanned print are repainted by a local model; its pixels "
        "are kept only where the print was damaged, as a new layer whose mask can be painted "
        "to add or drop areas. With a selection, only damage inside it is repaired.",
        name,
    )
    add_model_argument(procedure, flags)
    damage = Gimp.Choice.new()
    damage.add("general", 0, "Blotches, flakes, stains, scratches, specks", "")
    damage.add("burns", 1, "Chemical burns (gold/orange flakes, rusty blotches)", "")
    procedure.add_choice_argument(
        "damage",
        "_Damage",
        "What the print suffers from; chemical burns usually need Qwen-Image-Edit",
        damage,
        "general",
        flags,
    )
    procedure.add_int_argument(
        "threshold",
        "_Sensitivity threshold",
        "How much the model must have changed a spot (0-255) for it to count as repaired "
        "damage: lower catches faint damage (white on white) but also takes changes that "
        "are not damage",
        5,
        80,
        int(restore_mask.THRESHOLD),
        flags,
    )
    procedure.add_int_argument(
        "min-area",
        "Smallest _repair (px)",
        "Changed spots smaller than this are ignored unless the change is strong (a moved highlight, a redrawn button)",
        0,
        100000,
        restore_mask.MIN_AREA,
        flags,
    )


def add_modern_photo(procedure, name, flags):
    procedure.set_attribution("GIMPhoto", "GIMPhoto and photo-restore contributors", "2026")
    procedure.set_menu_label("_Modern Photo…")
    procedure.set_documentation(
        "Make an old photo look as if it were taken today, with a local AI model",
        "The old photo is redrawn by a local model as if taken today with a modern phone "
        "camera: sharp, clean, true colours, no grain, fading or damage; black and white "
        "comes back in colour unless asked not to. The result is a new layer above the "
        "photo; the model can change faces, so its mask can be painted black to bring the "
        "original back. With a selection, the layer shows only inside it.",
        name,
    )
    add_model_argument(procedure, flags)
    black_and_white = Gimp.Choice.new()
    black_and_white.add("colourise", 0, "Bring them back in colour", "")
    black_and_white.add("keep", 1, "Keep them black and white", "")
    procedure.add_choice_argument(
        "black-and-white",
        "_Black and white photos",
        "What to do with a black and white or sepia photo (a colour photo stays in colour)",
        black_and_white,
        "colourise",
        flags,
    )


class PhotoRestoration(Gimp.PlugIn):
    def do_set_i18n(self, procname):
        return False

    def do_query_procedures(self):
        return [PROC, MODERN_PROC]

    def do_create_procedure(self, name):
        procedure = Gimp.ImageProcedure.new(self, name, Gimp.PDBProcType.PLUGIN, run, None)
        # Modern Photo also takes Grayscale scans (converted to RGB for the result)
        procedure.set_image_types("RGB*, GRAY*" if name == MODERN_PROC else "RGB*")
        procedure.set_sensitivity_mask(Gimp.ProcedureSensitivityMask.DRAWABLE)
        flags = GObject.ParamFlags.READWRITE
        if name == MODERN_PROC:
            add_modern_photo(procedure, name, flags)
        else:
            add_photo_restoration(procedure, name, flags)
        # Photoshop's place: Filters > Neural Filters (after the menu label)
        procedure.add_menu_path("<Image>/Filters/Neural Filters")
        return procedure


if __name__ == "__main__":
    Gimp.main(PhotoRestoration.__gtype__, sys.argv)
