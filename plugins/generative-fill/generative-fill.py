#!/usr/bin/env python3
#
# Generative Fill and Generate Image (local AI): Photoshop's Edit >
# Generative Fill and Edit > Generate Image.
#
#   Generative Fill: a prompt fills the selection (an empty prompt fills it
#   from its surroundings, Photoshop's content-aware behaviour). The window
#   makes three variations, shown as thumbnails and on the canvas as each
#   one is ready; the chosen one becomes a new layer masked to the
#   selection (non-destructive, as Photoshop's Generative Layer), also when
#   the window is just closed. Generate again for three more. The layer
#   keeps its variations (parasites, saved in the XCF): a double click on it
#   (or Layer > Edit Generative Fill) opens the window again to pick another
#   one or generate more.
#
#   A selection that is mostly empty (transparent, or canvas without any
#   layer: the image made larger) is completed instead: the picture is
#   continued into it, prompt optional (Photoshop's Generative Expand).
#
#   Generate Image: a prompt makes an image the size of the canvas, as a
#   new layer; three variations to pick from in the same way.
#
# The AI runs on this computer: Qwen-Image-Edit (default, best results,
# about a minute per variation on a 6 GB GPU) or FLUX.2 klein (about 15 s)
# on the local ComfyUI, through gimp-setup's ComfyUI client vendored in
# plugins/comfyui-service/comfyui_client.py. GIMPhoto's comfyui-service
# plug-in starts ComfyUI with GIMPhoto (its gimphoto-comfyui parasite says
# where); without it, a message says where to install it (local-ai-setup).
#
# Run non-interactively (scripts), each procedure makes one variation with
# the given prompt and model and applies it.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.

import base64
import json
import os
import shutil
import sys
import tempfile
import threading
import time

import gi

gi.require_version("Gimp", "3.0")
gi.require_version("GimpUi", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gegl, Gimp, GimpUi, Gio, GLib, GObject, Gtk

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "comfyui-service"))
import comfyui_api as api
import comfyui_client as client
import gimphoto_ai as ai

FILL_PROC = "gimphoto-generative-fill"
IMAGE_PROC = "gimphoto-generate-image"
EDIT_PROC = "gimphoto-generative-edit"
REMOVE_PROC = "gimphoto-remove"
# The Remove tool's brush: hard and round, so the area sent is the area
# painted (the client grows it a little for the model)
REMOVE_BRUSH = "2. Hardness 100"
# Each stroke is sent this much wider (a share of the brush, per side): a
# rim of the object left uncovered made the model draw it again (a banana
# came back with the strokes as painted; gone with 16 px more per side on a
# 90 px brush, while 32 px reached into the mug next to it)
REMOVE_GROW = 0.18
# An object SAM finds under a stroke is removed whole when the strokes
# cover at least this share of it (Photoshop's Remove: brush most of it),
# unless it is far bigger than what was painted (the table, the wall); it
# is grown a little, for its edge
REMOVE_OBJECT_COVER = 0.5
REMOVE_OBJECT_MAX = 4.0
REMOVE_OBJECT_GROW = 6
# Picture LaMa gets around the area, in px (at least; half the area's size
# when that is more): enough to fill from, without sending a whole photo
LAMA_CONTEXT = 256
# On a layer Generative Fill or Generate Image made: the job as JSON, the
# model's mask and each variation (PNG, the size of the layer), kept in the
# XCF so the window can open again (a double click on the layer)
META = "gimphoto-generative"
MASK_PARASITE = "gimphoto-generative-mask"
VARIATION_PARASITE = "gimphoto-generative-{}"
PARASITE_FLAGS = Gimp.PARASITE_PERSISTENT | Gimp.PARASITE_UNDOABLE
KEEP_VARIATIONS = 12
VARIATIONS = 3
MODELS = (
    ("qwen", "Qwen-Image-Edit: best results, about 1 min per variation"),
    ("klein", "FLUX.2 klein: fast, about 15 s per variation"),
)
# Share of the selection that must be empty (transparent or off the
# layers) for Generative Fill to continue the picture into it
EMPTY_SHARE = 0.5
# Continuing the picture: the vendored client's outpaint, made for FLUX.2
# klein (Qwen drew the picture again inside the blank band, see its notes);
# a prompt with "continue" is what selects it there
EXTEND_MODEL = "klein"
EXTEND_PROMPT = "continue the image"
# Picture sent around the empty area, in px: with more, the model copies
# what is near it (a second apple next to the first in 2 of 3 tries with
# the client's 256+ px, none of 3 with 64)
EXTEND_CONTEXT = 64
# Where the selection meets the picture, the new layer fades into it over
# this many px (the model's band is a little lighter and softer than the
# photo: a hard edge showed as a seam); the empty area stays covered
EXTEND_BLEND = 24
THUMB = 168
NAME_CHARS = 40


# ------------------------------------------------------------- backend


# ------------------------------------------------------------- pixels


def save_png(image, path):
    Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, Gio.File.new_for_path(path), None)


def crop_to(image, region):
    if region:
        x, y, w, h = region
        image.crop(w, h, x, y)


def visible_png(image, path, region=None):
    """The visible image (all layers), at its own size or cropped to
    region, as a PNG."""
    dup = image.duplicate()
    try:
        Gimp.Selection.none(dup)
        dup.flatten()
        crop_to(dup, region)
        save_png(dup, path)
    finally:
        dup.delete()


def selection_png(image, path, region=None, blend=0):
    """The selection as a white-on-black PNG of the image's size or of
    region (soft edges kept). With blend, its edge is feathered by that many
    px where it meets the picture, while where the picture is empty
    (transparent, or no layer) it stays fully selected."""
    dup = image.duplicate()
    try:
        if blend:
            merged = dup.merge_visible_layers(Gimp.MergeType.CLIP_TO_IMAGE)
            if not merged.has_alpha():
                merged.add_alpha()
            merged.resize_to_image_size()
            selection = Gimp.Selection.save(dup)
            # the selected empty part: the selection minus the opaque pixels
            dup.select_item(Gimp.ChannelOps.SUBTRACT, merged)
            empty = Gimp.Selection.save(dup)
            dup.select_item(Gimp.ChannelOps.REPLACE, selection)
            Gimp.Selection.feather(dup, 2 * blend)
            dup.select_item(Gimp.ChannelOps.ADD, empty)
        w, h = dup.get_width(), dup.get_height()
        layer = Gimp.Layer.new(dup, "mask", w, h, Gimp.ImageType.RGB_IMAGE, 100, Gimp.LayerMode.NORMAL)
        dup.insert_layer(layer, None, 0)
        Gimp.context_push()
        try:
            Gimp.context_set_foreground(Gegl.Color.new("black"))
            layer.fill(Gimp.FillType.FOREGROUND)
            Gimp.context_set_foreground(Gegl.Color.new("white"))
            layer.edit_fill(Gimp.FillType.FOREGROUND)
        finally:
            Gimp.context_pop()
        Gimp.Selection.none(dup)
        dup.flatten()
        crop_to(dup, region)
        save_png(dup, path)
    finally:
        dup.delete()


def grown(box, margin, width, height):
    """box grown by margin on every side, inside width x height."""
    x, y, w, h = box
    x0, y0 = max(0, x - margin), max(0, y - margin)
    return x0, y0, min(width, x + w + margin) - x0, min(height, y + h + margin) - y0


def selection_box(image):
    """x, y, width, height of the selection, or None when there is none."""
    _ok, non_empty, x1, y1, x2, y2 = Gimp.Selection.bounds(image)
    if not non_empty or x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2 - x1, y2 - y1


def empty_share(image):
    """Share of the selection where the visible image is transparent or
    has no layer at all (0..1)."""
    dup = image.duplicate()
    try:
        layer = dup.merge_visible_layers(Gimp.MergeType.CLIP_TO_IMAGE)
        if layer is None:
            return 1.0
        if not layer.has_alpha():
            layer.add_alpha()
        # a merged layer can be smaller than the canvas: the rest is empty
        layer.resize_to_image_size()
        # the histogram counts only the selected pixels
        ok, *_stats, share = layer.histogram(Gimp.HistogramChannel.ALPHA, 0.0, 0.5)
        return share if ok else 0.0
    finally:
        dup.delete()


def layer_name(kind, prompt):
    prompt = " ".join((prompt or "").split())
    if not prompt:
        return kind
    if len(prompt) > NAME_CHARS:
        prompt = prompt[: NAME_CHARS - 1] + "…"
    return f"{kind}: {prompt}"


def crop_png(source, box, dest):
    """The PNG at source, cropped to box (x, y, w, h; None: whole), saved
    as dest. GdkPixbuf only: safe in the worker thread."""
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(source)
    if box:
        pixbuf = pixbuf.new_subpixbuf(*box)
    pixbuf.savev(dest, "png", [], [])


def add_variation_layer(image, path, name, at, place, mask_path=None, mask_from=None, size=None):
    """The variation PNG (already the layer's size) as a new layer at `at`
    in place (parent, position), masked by the PNG at mask_path or by a copy
    of the mask mask_from (Generative Fill), or scaled to size (Generate
    Image). Returns the layer."""
    src_image = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(path))
    try:
        layer = Gimp.Layer.new_from_drawable(src_image.get_layers()[0], image)
    finally:
        src_image.delete()
    layer.set_name(name)
    image.insert_layer(layer, *place)
    if size and (layer.get_width(), layer.get_height()) != size:
        layer.scale(size[0], size[1], False)
    layer.set_offsets(*at)
    if mask_path or mask_from:
        # written into the mask before it is added: a mask made from a
        # selection would need the selection, which the person may have
        # changed while the window was open
        mask = layer.create_mask(Gimp.AddMaskType.WHITE)
        rect = Gegl.Rectangle.new(0, 0, layer.get_width(), layer.get_height())
        target = mask.get_buffer()
        if mask_path:
            mask_image = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(mask_path))
            try:
                mask_image.get_layers()[0].get_buffer().copy(rect, Gegl.AbyssPolicy.NONE, target, rect)
            finally:
                mask_image.delete()
        else:
            mask_from.get_buffer().copy(rect, Gegl.AbyssPolicy.NONE, target, rect)
        target.flush()
        if not layer.has_alpha():
            layer.add_alpha()
        layer.add_mask(mask)
    return layer


def read_parasite(item, name, binary=False):
    parasite = item.get_parasite(name)
    if parasite is None:
        return None
    data = bytes(parasite.get_data())
    return base64.b64decode(data) if binary else data


def write_parasite(item, name, data, binary=False):
    """Parasite data goes through GObject as signed bytes (-128..127):
    binary data (PNGs) is stored as base64, which is ASCII."""
    if binary:
        data = base64.b64encode(data)
    item.attach_parasite(Gimp.Parasite.new(name, PARASITE_FLAGS, list(data)))


# ------------------------------------------------------------- jobs


class Job:
    """One Generative Fill or Generate Image: what the model is given, the
    variations made so far (PNGs the size of the layer), and how the chosen
    one becomes the layer. A new job comes from the selection; Job.edit
    reopens one from the layer it made (its parasites)."""

    def __init__(self, image, kind, tmp, target=None):
        self.image = image
        self.kind = kind  # "fill" or "image"
        self.tmp = tmp
        self.target = target  # the layer being changed (Job.edit), or None
        self.prompt = ""
        self.model = MODELS[0][0]
        self.extend = False
        self.box = self.region = None
        self.layer_box = None  # in the model's PNG; None: all of it
        self.layer_at = (0, 0)
        self.size = (image.get_width(), image.get_height())
        self.image_png = self.mask_png = None
        self.layer_mask_path = None
        # the variations: PNGs the size of the layer, and the prompt and
        # model each was made with
        self.variations, self.prompts, self.models = [], [], []
        self.chosen = None
        # new layers go above the layer selected when the window opened:
        # previews change the selection, so it is remembered here
        self.selected = image.get_selected_layers()
        self.place = (None, 0)
        top = target or (self.selected[0] if self.selected else None)
        if top:
            self.place = (top.get_parent(), image.get_item_position(top))

    @classmethod
    def new(cls, image, kind, tmp):
        job = cls(image, kind, tmp)
        if kind == "image":
            return job
        job.extend = empty_share(image) > EMPTY_SHARE
        job.box = selection_box(image)
        local_box = job.box
        if job.extend:
            # only the empty area and a little picture around it
            job.region = grown(job.box, EXTEND_CONTEXT, *job.size)
            x, y, w, h = job.box
            local_box = (x - job.region[0], y - job.region[1], w, h)
        job.layer_box, job.layer_at = local_box, job.box[:2]
        image_path = os.path.join(tmp, "image.png")
        mask_path = os.path.join(tmp, "mask.png")
        visible_png(image, image_path, job.region)
        selection_png(image, mask_path, job.region)
        with open(image_path, "rb") as f:
            job.image_png = f.read()
        with open(mask_path, "rb") as f:
            job.mask_png = f.read()
        layer_mask = mask_path
        if job.extend:
            # the layer: a little more than the selection, fading into the
            # picture
            layer_mask = os.path.join(tmp, "layer-mask-full.png")
            selection_png(image, layer_mask, job.region, blend=EXTEND_BLEND)
            job.layer_box = grown(local_box, EXTEND_BLEND, *job.region[2:])
            job.layer_at = (job.region[0] + job.layer_box[0], job.region[1] + job.layer_box[1])
        job.layer_mask_path = os.path.join(tmp, "layer-mask.png")
        crop_png(layer_mask, job.layer_box, job.layer_mask_path)
        return job

    @classmethod
    def edit(cls, image, layer, tmp):
        """The job that made layer, from its parasites; the model is given
        the image as it is now, without that layer."""
        meta = json.loads(read_parasite(layer, META).decode())
        job = cls(image, meta["kind"], tmp, target=layer)
        job.prompt = meta.get("prompt", "")
        job.model = meta.get("model", job.model)
        job.extend = meta.get("extend", False)
        job.size = tuple(meta["size"])
        job.region = tuple(meta["region"]) if meta.get("region") else None
        job.layer_box = tuple(meta["layer_box"]) if meta.get("layer_box") else None
        # where the layer is now: it may have been moved since
        job.layer_at = tuple(layer.get_offsets()[1:]) if job.kind == "fill" else (0, 0)
        prompts = meta.get("prompts") or []
        models = meta.get("models") or []
        for i in range(meta["count"]):
            data = read_parasite(layer, VARIATION_PARASITE.format(i), binary=True)
            if data is None:
                continue
            path = os.path.join(tmp, f"variation-{i}.png")
            with open(path, "wb") as f:
                f.write(data)
            job.add(path, prompts[i] if i < len(prompts) else job.prompt, models[i] if i < len(models) else job.model)
        job.chosen = min(meta.get("chosen", 0), len(job.variations) - 1) if job.variations else None
        if job.kind == "fill":
            job.mask_png = read_parasite(layer, MASK_PARASITE, binary=True)
            image_path = os.path.join(tmp, "image.png")
            image.undo_freeze()
            visible = layer.get_visible()
            try:
                layer.set_visible(False)
                visible_png(image, image_path, job.region)
            finally:
                layer.set_visible(visible)
                image.undo_thaw()
            with open(image_path, "rb") as f:
                job.image_png = f.read()
        return job

    def add(self, path, prompt, model):
        self.variations.append(path)
        self.prompts.append(prompt)
        self.models.append(model)

    @property
    def title(self):
        return "Generative Fill" if self.kind == "fill" else "Generate Image"

    def make(self, url, prompt, model, progress=None):
        """One variation, stored the size of the layer; returns its path
        (worker thread: no GIMP calls)."""
        if self.extend:
            text = f"{EXTEND_PROMPT}, {prompt}" if prompt else EXTEND_PROMPT
            png = client.inpaint(EXTEND_MODEL, self.image_png, self.mask_png, text, url=url, progress=progress)
        elif self.kind == "fill":
            png = client.inpaint(model, self.image_png, self.mask_png, prompt or None, url=url, progress=progress)
        else:
            png = client.generate(prompt, *client.work_size(*self.size), url=url, progress=progress)
        stamp = time.monotonic_ns()
        full = os.path.join(self.tmp, f"full-{stamp}.png")
        path = os.path.join(self.tmp, f"variation-new-{stamp}.png")
        with open(full, "wb") as f:
            f.write(png)
        crop_png(full, self.layer_box, path)
        os.remove(full)
        return path

    def new_layer(self, path, prompt):
        """The variation at path as a new layer, where the result goes."""
        kind = "Generative Fill" if self.kind == "fill" else "Generated"
        name = layer_name(kind, prompt)
        if self.kind == "image":
            return add_variation_layer(self.image, path, name, (0, 0), self.place, size=self.size)
        if self.target is not None:
            return add_variation_layer(
                self.image, path, name, self.layer_at, self.place, mask_from=self.target.get_mask()
            )
        return add_variation_layer(self.image, path, name, self.layer_at, self.place, mask_path=self.layer_mask_path)

    def trim(self):
        """At most KEEP_VARIATIONS: the latest, and always the chosen one."""
        count = len(self.variations)
        if count <= KEEP_VARIATIONS:
            return
        keep = list(range(count - KEEP_VARIATIONS, count))
        if self.chosen not in keep:
            keep = [self.chosen] + keep[1:]
        self.variations = [self.variations[i] for i in keep]
        self.prompts = [self.prompts[i] for i in keep]
        self.models = [self.models[i] for i in keep]
        self.chosen = keep.index(self.chosen)

    def save(self, layer):
        """The job on the layer (parasites, kept in the XCF), so a double
        click on it opens the window again."""
        self.trim()
        meta = {
            "version": 1,
            "kind": self.kind,
            "prompt": self.prompts[self.chosen],
            "model": self.models[self.chosen],
            "prompts": self.prompts,
            "models": self.models,
            "extend": self.extend,
            "size": list(self.size),
            "region": list(self.region) if self.region else None,
            "layer_box": list(self.layer_box) if self.layer_box else None,
            "layer_at": list(self.layer_at),
            "chosen": self.chosen,
            "count": len(self.variations),
        }
        write_parasite(layer, META, json.dumps(meta).encode())
        if self.mask_png:
            write_parasite(layer, MASK_PARASITE, self.mask_png, binary=True)
        for i, path in enumerate(self.variations):
            with open(path, "rb") as f:
                write_parasite(layer, VARIATION_PARASITE.format(i), f.read(), binary=True)

    def commit(self):
        """The chosen variation as the layer, named after its prompt, in one
        undo step: a new layer, or (Job.edit) a new one in place of the
        target."""
        image = self.image
        prompt = self.prompts[self.chosen]
        image.undo_group_start()
        try:
            layer = self.new_layer(self.variations[self.chosen], prompt)
            self.save(layer)
            if self.target is not None:
                layer.set_visible(self.target.get_visible())
                layer.set_opacity(self.target.get_opacity())
                layer.set_mode(self.target.get_mode())
                image.remove_layer(self.target)
                # GIMP added " #1" while the old layer had the same name
                layer.set_name(layer_name("Generative Fill" if self.kind == "fill" else "Generated", prompt))
            image.set_selected_layers([layer])
        finally:
            image.undo_group_end()
        Gimp.displays_flush()
        return layer

    def thumbnail(self, path):
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
        scale = THUMB / float(max(pixbuf.get_width(), pixbuf.get_height()))
        return pixbuf.scale_simple(
            max(1, round(pixbuf.get_width() * scale)),
            max(1, round(pixbuf.get_height() * scale)),
            GdkPixbuf.InterpType.BILINEAR,
        )


# ------------------------------------------------------------- window


class GenerateDialog:
    """Prompt, Generate, the variations as they come; the chosen one stays
    when the window is closed (Discard / Cancel throws the change away)."""

    def __init__(self, job):
        self.job = job
        self.state, self.url = ai.backend()
        self.stop = threading.Event()
        self.running = False
        self.preview = None
        self.hidden = False  # the target hidden under a preview (Job.edit)
        self.original = (job.chosen, len(job.variations))

        self.dialog = GimpUi.Dialog(title=job.title, role=job.title.lower().replace(" ", "-"))
        editing = job.target is not None
        self.dialog.add_button("_Cancel" if editing else "_Discard", Gtk.ResponseType.CANCEL)
        self.ok = self.dialog.add_button("_OK", Gtk.ResponseType.OK)
        self.ok.set_sensitive(False)
        self.dialog.set_default_size(760, -1)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, border_width=12)
        self.dialog.get_content_area().pack_start(box, True, True, 0)

        row = Gtk.Box(spacing=8)
        self.prompt = Gtk.Entry(text=job.prompt or "", hexpand=True, activates_default=False)
        if job.extend:
            placeholder = "Optional: what the rest of the picture has (empty: complete the image)"
        elif job.kind == "fill":
            placeholder = "Describe what to add (empty: fill from the surroundings or complete the image)"
        else:
            placeholder = "Describe the image to generate"
        self.prompt.set_placeholder_text(placeholder)
        self.prompt.connect("activate", lambda _w: self.generate())
        self.button = Gtk.Button(label="Generate")
        self.button.connect("clicked", lambda _w: self.stop_or_generate())
        row.pack_start(self.prompt, True, True, 0)
        row.pack_start(self.button, False, False, 0)
        box.pack_start(row, False, False, 0)

        self.model = Gtk.ComboBoxText()
        if job.kind == "fill":
            for key, label in MODELS:
                self.model.append(key, label)
            self.model.set_active_id(job.model if job.model in dict(MODELS) else MODELS[0][0])
            model_row = Gtk.Box(spacing=8)
            model_row.pack_start(Gtk.Label(label="Model:"), False, False, 0)
            model_row.pack_start(self.model, True, True, 0)
            box.pack_start(model_row, False, False, 0)
        if job.extend:
            self.model.set_active_id(EXTEND_MODEL)
            note = Gtk.Label(
                label="The selection is mostly empty: Generative Fill continues the picture into it "
                "(FLUX.2 klein, the model made for this).",
                xalign=0,
                wrap=True,
            )
            box.pack_start(note, False, False, 0)

        self.progress = Gtk.ProgressBar(show_text=True, text="")
        box.pack_start(self.progress, False, False, 0)

        self.flow = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.SINGLE, min_children_per_line=3, max_children_per_line=3, homogeneous=True
        )
        scroller = Gtk.ScrolledWindow(min_content_height=THUMB + 24)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.add(self.flow)
        box.pack_start(scroller, True, True, 0)

        # the variations it already has (Job.edit), the current one selected
        for path in job.variations:
            self.add_thumbnail(path)
        if job.chosen is not None:
            self.flow.select_child(self.flow.get_child_at_index(job.chosen))
            self.ok.set_sensitive(True)
        self.flow.connect("selected-children-changed", self.on_selected)

        self.dialog.show_all()
        self.model.set_sensitive(not job.extend)
        # GTK hides a focused entry's placeholder: start on Generate, so the
        # hint (what an empty prompt does) shows
        self.button.grab_focus()

    # -- running

    def stop_or_generate(self):
        if self.running:
            self.stop.set()
            self.progress.set_text("Stopping…")
            threading.Thread(target=client.cancel, args=(self.url,), daemon=True).start()
        else:
            self.generate()

    def generate(self):
        if self.running:
            return
        prompt = self.prompt.get_text().strip()
        if self.job.kind == "image" and not prompt:
            self.progress.set_text("Describe the image first")
            return
        model = self.model.get_active_id() or "klein"
        self.stop.clear()
        self.running = True
        self.button.set_label("Stop")
        self.prompt.set_sensitive(False)
        self.model.set_sensitive(False)
        threading.Thread(target=self.work, args=(prompt, model), daemon=True).start()

    def work(self, prompt, model):
        """Worker thread: HTTP and PNG files only; the window is updated
        with idle_add."""
        try:
            ai.wait_ready(
                self.state,
                self.url,
                self.job.title,
                waiting=lambda s: self.later(None, f"Starting the local AI… {s:.0f} s"),
            )
            for n in range(1, VARIATIONS + 1):
                if self.stop.is_set():
                    break
                started = time.monotonic()

                def tick(_elapsed, n=n, started=started):
                    if not self.stop.is_set():
                        self.later(
                            None,
                            f"Variation {n} of {VARIATIONS}: {time.monotonic() - started:.0f} s"
                            + ("" if n > 1 or model == "klein" else ", the first one loads the model"),
                        )

                path = self.job.make(self.url, prompt, model, progress=tick)
                if self.stop.is_set():
                    break
                GLib.idle_add(self.add_variation, path, prompt, model)
            self.later(False, "Stopped" if self.stop.is_set() else "Pick a variation, or Generate for more")
        except Exception as e:
            self.later(False, "Stopped" if self.stop.is_set() else str(e))

    def later(self, running, text):
        GLib.idle_add(self.update, running, text)

    def update(self, running, text):
        self.progress.set_text(text)
        if running is None:
            self.progress.pulse()
        else:
            self.running = False
            self.progress.set_fraction(0)
            self.button.set_label("Generate")
            self.prompt.set_sensitive(True)
            self.model.set_sensitive(not self.job.extend)
        return False

    # -- variations

    def add_thumbnail(self, path):
        image = Gtk.Image.new_from_pixbuf(self.job.thumbnail(path))
        image.set_tooltip_text(f"Variation {self.flow_count() + 1}")
        self.flow.add(image)
        image.show()
        return image

    def flow_count(self):
        return len(self.flow.get_children())

    def add_variation(self, path, prompt, model):
        self.job.add(path, prompt, model)
        image = self.add_thumbnail(path)
        if not self.flow.get_selected_children():
            self.flow.select_child(image.get_parent())
        return False

    def on_selected(self, flow):
        children = flow.get_selected_children()
        if not children:
            return
        self.job.chosen = children[0].get_index()
        self.ok.set_sensitive(True)
        self.show_preview()

    def show_preview(self):
        """The chosen variation on the canvas, outside the undo history.
        When reopened (Job.edit), the layer itself is only hidden under the
        preview, and shows again when its own variation is chosen."""
        image = self.job.image
        image.undo_freeze()
        try:
            self.remove_preview(frozen=True)
            target = self.job.target
            if target is not None and (self.job.chosen, len(self.job.variations)) == self.original:
                return
            if target is not None:
                self.hidden = target.get_visible()
                target.set_visible(False)
            self.preview = self.job.new_layer(self.job.variations[self.job.chosen], self.job.prompts[self.job.chosen])
        finally:
            image.undo_thaw()
            Gimp.displays_flush()

    def remove_preview(self, frozen=False):
        image = self.job.image
        if not frozen:
            image.undo_freeze()
        try:
            if self.preview is not None and self.preview.is_valid():
                image.remove_layer(self.preview)
            if self.hidden and self.job.target.is_valid():
                self.job.target.set_visible(True)
            selected = [layer for layer in self.job.selected if layer.is_valid()]
            if selected:
                image.set_selected_layers(selected)
        finally:
            self.preview = None
            self.hidden = False
            if not frozen:
                image.undo_thaw()

    # -- result

    def run(self):
        """True to keep the chosen variation (job.chosen). Closing the
        window keeps it, as OK does."""
        response = self.dialog.run()
        if self.running:
            self.stop.set()
            client.cancel(self.url)
        self.remove_preview()
        Gimp.displays_flush()
        self.dialog.destroy()
        if response == Gtk.ResponseType.CANCEL or self.job.chosen is None:
            return False
        if self.job.target is not None and (self.job.chosen, len(self.job.variations)) == self.original:
            return False  # nothing changed
        return True


# ------------------------------------------------------------- procedures


def run_job(kind, procedure, run_mode, image, config):
    prompt = config.get_property("prompt") or ""
    model = config.get_property("model") if kind == "fill" else "klein"
    if kind == "fill" and selection_box(image) is None:
        return procedure.new_return_values(
            Gimp.PDBStatusType.EXECUTION_ERROR,
            GLib.Error("Generative Fill fills a selection: select the area to fill first."),
        )
    tmp = tempfile.mkdtemp(prefix="gimphoto-generate-")
    try:
        job = Job.new(image, kind, tmp)
        job.prompt, job.model = prompt, model
        if run_mode == Gimp.RunMode.INTERACTIVE:
            GimpUi.init("generative-fill")
            if not GenerateDialog(job).run():
                return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())
            config.set_property("prompt", job.prompts[job.chosen])
            if kind == "fill":
                config.set_property("model", job.models[job.chosen])
        else:
            if kind == "image" and not prompt.strip():
                raise api.ComfyUIError("Generate Image needs a prompt.")
            state, url = ai.backend()
            Gimp.progress_init(job.title)
            ai.wait_ready(state, url, job.title)
            job.add(job.make(url, prompt, model, progress=lambda _s: Gimp.progress_pulse()), prompt, model)
            job.chosen = 0
        job.commit()
    except Exception as e:
        return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error(str(e)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


def run_fill(procedure, run_mode, image, drawables, config, data):
    return run_job("fill", procedure, run_mode, image, config)


def run_image(procedure, run_mode, image, drawables, config, data):
    return run_job("image", procedure, run_mode, image, config)


def run_edit(procedure, run_mode, image, drawables, config, data):
    layer = drawables[0] if len(drawables) == 1 else None
    if not isinstance(layer, Gimp.Layer) or layer.get_parasite(META) is None:
        return procedure.new_return_values(
            Gimp.PDBStatusType.EXECUTION_ERROR,
            GLib.Error("This layer was not made by Generative Fill or Generate Image."),
        )
    if run_mode != Gimp.RunMode.INTERACTIVE:
        return procedure.new_return_values(
            Gimp.PDBStatusType.CALLING_ERROR, GLib.Error("Editing a generated layer needs the window.")
        )
    tmp = tempfile.mkdtemp(prefix="gimphoto-generate-")
    try:
        job = Job.edit(image, layer, tmp)
        GimpUi.init("generative-fill")
        if GenerateDialog(job).run():
            job.commit()
    except Exception as e:
        return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error(str(e)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


# ------------------------------------------------------------- Remove tool


def paint_strokes(layer, strokes, grow=0.0):
    """The strokes painted white on layer, each brush wider by grow (a
    share of its size, per side)."""
    Gimp.context_push()
    try:
        Gimp.context_set_foreground(Gegl.Color.new("white"))
        Gimp.context_set_brush(Gimp.Brush.get_by_name(REMOVE_BRUSH))
        Gimp.context_set_opacity(100.0)
        Gimp.context_set_paint_mode(Gimp.LayerMode.NORMAL)
        Gimp.context_enable_dynamics(False)
        for stroke in strokes:
            points = [float(v) for v in stroke["points"]]
            if len(points) < 2:
                continue
            if len(points) == 2:  # a click: one dab
                points = points * 2
            Gimp.context_set_brush_size(float(stroke["size"]) * (1 + 2 * grow))
            Gimp.paintbrush_default(layer, points)
    finally:
        Gimp.context_pop()


def stroke_box(stroke, width, height):
    """The box around a stroke, its brush included, inside the image."""
    xs, ys = stroke["points"][0::2], stroke["points"][1::2]
    r = float(stroke["size"]) / 2
    x0, y0 = max(0, int(min(xs) - r)), max(0, int(min(ys) - r))
    x1, y1 = min(width, int(max(xs) + r) + 1), min(height, int(max(ys) + r) + 1)
    return x0, y0, x1, y1


def black_layer(image, name):
    layer = Gimp.Layer.new(
        image, name, image.get_width(), image.get_height(), Gimp.ImageType.RGB_IMAGE, 100, Gimp.LayerMode.NORMAL
    )
    image.insert_layer(layer, None, 0)
    Gimp.context_push()
    Gimp.context_set_foreground(Gegl.Color.new("black"))
    layer.fill(Gimp.FillType.FOREGROUND)
    Gimp.context_pop()
    return layer


def white_share(image, layer):
    """(pixels selected, share of them that are white on layer)."""
    ok, _mean, _std, _median, pixels, _count, share = layer.histogram(Gimp.HistogramChannel.VALUE, 0.5, 1.0)
    return (pixels, share) if ok else (0, 0.0)


def remove_mask(image, strokes, path, url=None, image_png=None):
    """What the Remove tool removes, white on black, the image's size, as a
    PNG. For each stroke, with url: the object SAM 2.1 finds under it, when
    the strokes cover most of it (Photoshop's Remove: brush most of an
    object, all of it goes), plus the stroke as painted; otherwise (no
    object, or no SAM) the stroke a little wider than painted, so no rim of
    what it covers is left. Returns the area's box, or None when empty."""
    w, h = image.get_width(), image.get_height()
    tmp = Gimp.Image.new(w, h, Gimp.ImageBaseType.RGB)
    try:
        painted = black_layer(tmp, "painted")
        paint_strokes(painted, strokes)
        mask = black_layer(tmp, "mask")
        tmp.select_color(Gimp.ChannelOps.REPLACE, painted, Gegl.Color.new("white"))
        painted_px = white_share(tmp, painted)[0]
        sam_path = os.path.join(os.path.dirname(path), "object.png")
        use_sam = bool(url and painted_px)
        for stroke in strokes:
            found_object = False
            if use_sam:
                try:
                    found = api.segment(url, image_png, [list(stroke_box(stroke, w, h))])
                except api.ComfyUIError:
                    use_sam = False  # no SAM (model set "sam"): the strokes alone
                else:
                    with open(sam_path, "wb") as f:
                        f.write(found)
                    obj = Gimp.file_load_layer(Gimp.RunMode.NONINTERACTIVE, tmp, Gio.File.new_for_path(sam_path))
                    tmp.insert_layer(obj, None, 0)
                    if (obj.get_width(), obj.get_height()) != (w, h):
                        obj.scale(w, h, False)
                    tmp.select_color(Gimp.ChannelOps.REPLACE, obj, Gegl.Color.new("white"))
                    object_px, covered = white_share(tmp, painted)
                    if object_px and covered >= REMOVE_OBJECT_COVER and object_px <= REMOVE_OBJECT_MAX * painted_px:
                        found_object = True
                        Gimp.Selection.grow(tmp, REMOVE_OBJECT_GROW)
                        Gimp.context_push()
                        Gimp.context_set_foreground(Gegl.Color.new("white"))
                        mask.edit_fill(Gimp.FillType.FOREGROUND)
                        Gimp.context_pop()
                    tmp.remove_layer(obj)
                    Gimp.Selection.none(tmp)
            paint_strokes(mask, [stroke], 0.0 if found_object else REMOVE_GROW)
        tmp.select_color(Gimp.ChannelOps.REPLACE, mask, Gegl.Color.new("white"))
        box = selection_box(tmp)
        Gimp.Selection.none(tmp)
        tmp.remove_layer(painted)
        save_png(tmp, path)
        return box
    finally:
        tmp.delete()


def composite_into(image, layer, picture_path, mask_path, box, origin=(0, 0)):
    """The picture over the layer where the mask is white, inside box (image
    coordinates): a layer of it, masked, merged down into the layer (GIMP
    operations: a plug-in's GEGL has no operations loaded). The picture and
    the mask cover the image from origin."""
    x, y, w, h = grown(box, 2, image.get_width(), image.get_height())
    ox, oy = origin
    picture = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(picture_path))
    mask_image = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(mask_path))
    try:
        picture.crop(w, h, x - ox, y - oy)
        mask_image.crop(w, h, x - ox, y - oy)
        patch = Gimp.Layer.new_from_drawable(picture.get_layers()[0], image)
        # right above the layer, to be merged down into it
        image.insert_layer(patch, layer.get_parent(), image.get_item_position(layer))
        patch.set_offsets(x, y)
        if not patch.has_alpha():
            patch.add_alpha()
        mask = patch.create_mask(Gimp.AddMaskType.WHITE)
        rect = Gegl.Rectangle.new(0, 0, w, h)
        target = mask.get_buffer()
        mask_image.get_layers()[0].get_buffer().copy(rect, Gegl.AbyssPolicy.NONE, target, rect)
        target.flush()
        patch.add_mask(mask)
    finally:
        picture.delete()
        mask_image.delete()
    # keeps the layer's name, position and size
    try:
        return image.merge_down(patch, Gimp.MergeType.CLIP_TO_BOTTOM_LAYER)
    except Exception:
        image.remove_layer(patch)  # not left behind as a stray layer
        raise


def remove(image, layer, strokes, model):
    """What the Remove tool's strokes cover is removed from the layer, the
    background filled in by the local AI from the visible image."""
    state, url = ai.backend()
    tmp = tempfile.mkdtemp(prefix="gimphoto-remove-")
    Gimp.progress_init("Remove")
    try:
        image_path = os.path.join(tmp, "image.png")
        visible_png(image, image_path)
        ai.wait_ready(state, url, "The Remove tool")
        with open(image_path, "rb") as f:
            image_png = f.read()
        Gimp.progress_set_text("Finding the objects under the strokes…")
        mask_path = os.path.join(tmp, "mask.png")
        box = remove_mask(image, strokes, mask_path, url, image_png)
        if box is None:
            return
        with open(mask_path, "rb") as f:
            mask_png = f.read()

        def working(elapsed):
            Gimp.progress_set_text("Removing… %d s" % elapsed)
            Gimp.progress_pulse()

        origin = (0, 0)
        if model == "lama":
            # made for this: fills from around the area, adds nothing. It
            # works at the size it is given: only the area and some picture
            # around it (a whole 24 MP photo would not fit a 6 GB GPU)
            x, y, w, h = grown(box, max(LAMA_CONTEXT, max(box[2:]) // 2), image.get_width(), image.get_height())
            origin = (x, y)
            crop_png(image_path, (x, y, w, h), os.path.join(tmp, "image-crop.png"))
            crop_png(mask_path, (x, y, w, h), os.path.join(tmp, "mask-crop.png"))
            with open(os.path.join(tmp, "image-crop.png"), "rb") as f:
                crop_image = f.read()
            with open(os.path.join(tmp, "mask-crop.png"), "rb") as f:
                crop_mask = f.read()
            result = api.remove(url, crop_image, crop_mask, progress=working)
        else:
            # no prompt: the client's removal (the area hidden from the
            # model, filled from around it; again the other way when it
            # comes back flat)
            result = client.inpaint(model, image_png, mask_png, None, url=url, progress=working)
        result_path = os.path.join(tmp, "result.png")
        with open(result_path, "wb") as f:
            f.write(result)
        selected = image.get_selected_layers()
        image.undo_group_start()
        try:
            if model == "lama":
                mask_path = os.path.join(tmp, "mask-crop.png")
            merged = composite_into(image, layer, result_path, mask_path, box, origin)
            image.set_selected_layers([merged if s == layer else s for s in selected] or [merged])
        finally:
            image.undo_group_end()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        Gimp.progress_end()
    Gimp.displays_flush()


def run_remove(procedure, config, data):
    image = config.get_property("image")
    drawable = config.get_property("drawable")
    layer = drawable.get_parent() if isinstance(drawable, Gimp.LayerMask) else drawable
    try:
        if not isinstance(layer, Gimp.Layer) or layer.is_group():
            raise api.ComfyUIError("The Remove tool works on a pixel layer: select one (not a layer group).")
        if layer.get_lock_content():
            raise api.ComfyUIError("The layer's pixels are locked: unlock them to remove from it.")
        strokes = json.loads(config.get_property("strokes") or "[]")
        model = config.get_property("model") or "lama"
        remove(image, layer, strokes, model if model in ("lama", "klein", "qwen") else "lama")
    except Exception as e:
        return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error(str(e)))
    return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


class GenerativeFill(Gimp.PlugIn):
    def do_set_i18n(self, procname):
        return False

    def do_query_procedures(self):
        return [FILL_PROC, IMAGE_PROC, EDIT_PROC, REMOVE_PROC]

    def do_create_procedure(self, name):
        if name == REMOVE_PROC:
            return self.remove_procedure(name)
        if name == EDIT_PROC:
            return self.edit_procedure(name)
        fill = name == FILL_PROC
        procedure = Gimp.ImageProcedure.new(self, name, Gimp.PDBProcType.PLUGIN, run_fill if fill else run_image, None)
        procedure.set_image_types("*")
        procedure.set_sensitivity_mask(
            Gimp.ProcedureSensitivityMask.DRAWABLE
            | Gimp.ProcedureSensitivityMask.DRAWABLES
            | Gimp.ProcedureSensitivityMask.NO_DRAWABLES
        )
        if fill:
            procedure.set_menu_label("_Generative Fill…")
            procedure.set_documentation(
                "Fill the selection from a prompt (AI)",
                "Like Photoshop's Generative Fill: the selection is filled following the prompt "
                "(empty: from its surroundings), as a new layer masked to the selection, on the "
                "local ComfyUI (Qwen-Image-Edit or FLUX.2 klein). Three variations to pick from.",
                name,
            )
        else:
            procedure.set_menu_label("Generate _Image…")
            procedure.set_documentation(
                "Generate an image from a prompt (AI)",
                "Like Photoshop's Generate Image: an image the size of the canvas, made from the "
                "prompt on the local ComfyUI (FLUX.2 klein), as a new layer. Three variations to "
                "pick from.",
                name,
            )
        procedure.set_attribution("GIMPhoto", "GIMPhoto contributors", "2026")
        # after Fill and Stroke, as in Photoshop
        procedure.add_menu_path("<Image>/Edit/[Stroke]")
        flags = GObject.ParamFlags.READWRITE
        procedure.add_string_argument("prompt", "Prompt", "What to generate", "", flags)
        if fill:
            procedure.add_string_argument(
                "model", "Model", "qwen (Qwen-Image-Edit) or klein (FLUX.2 klein)", "qwen", flags
            )
        return procedure

    def remove_procedure(self, name):
        """Run by GIMPhoto's Remove tool (a core patch) with its strokes; no
        menu entry."""
        procedure = Gimp.Procedure.new(self, name, Gimp.PDBProcType.PLUGIN, run_remove, None)
        procedure.set_documentation(
            "Remove what the strokes cover (AI)",
            "Like Photoshop's Remove tool: what the strokes cover is removed from the layer and "
            "the background filled in, by the local AI (FLUX.2 klein or Qwen-Image-Edit) from the "
            "visible image. Run by GIMPhoto's Remove tool.",
            name,
        )
        procedure.set_attribution("GIMPhoto", "GIMPhoto contributors", "2026")
        flags = GObject.ParamFlags.READWRITE
        procedure.add_enum_argument("run-mode", "Run mode", "", Gimp.RunMode, Gimp.RunMode.NONINTERACTIVE, flags)
        procedure.add_image_argument("image", "Image", "", False, flags)
        procedure.add_drawable_argument("drawable", "Drawable", "The layer to remove from", False, flags)
        procedure.add_string_argument(
            "strokes",
            "Strokes",
            'JSON: [{"size": brush px, "points": [x0, y0, x1, y1, ...]}, ...] in image pixels',
            "[]",
            flags,
        )
        procedure.add_string_argument(
            "model", "Model", "lama (Big-LaMa, default), klein (FLUX.2 klein) or qwen (Qwen-Image-Edit)", "lama", flags
        )
        return procedure

    def edit_procedure(self, name):
        """Layer > Edit Generative Fill, and a double click on such a layer
        (GIMPhoto's Layers dock patch runs this action)."""
        procedure = Gimp.ImageProcedure.new(self, name, Gimp.PDBProcType.PLUGIN, run_edit, None)
        procedure.set_image_types("*")
        procedure.set_sensitivity_mask(Gimp.ProcedureSensitivityMask.DRAWABLE)
        procedure.set_menu_label("Edit _Generative Fill…")
        procedure.set_documentation(
            "Change a generated layer's variation (AI)",
            "Opens the Generative Fill or Generate Image window of a layer they made, with its "
            "variations: pick another one, or generate more.",
            name,
        )
        procedure.set_attribution("GIMPhoto", "GIMPhoto contributors", "2026")
        procedure.add_menu_path("<Image>/Layer")
        return procedure


# a module when tests/smoke_generative_layer.py loads it inside GIMPhoto
if __name__ == "__main__":
    Gimp.main(GenerativeFill.__gtype__, sys.argv)
