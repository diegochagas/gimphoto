#!/usr/bin/env python3
#
# Generative Fill and Generate Image (local AI): Photoshop's Edit >
# Generative Fill and Edit > Generate Image.
#
#   Generative Fill: a prompt fills the selection (an empty prompt fills it
#   from its surroundings, Photoshop's content-aware behaviour). The window
#   makes three variations, shown as thumbnails and on the canvas as each
#   one is ready; the chosen one becomes a new layer masked to the
#   selection (non-destructive, as Photoshop's Generative Layer). Generate
#   again for three more.
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
# where); without it, a message says where to install it (linux-mint-setup).
#
# Run non-interactively (scripts), each procedure makes one variation with
# the given prompt and model and applies it.
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
import comfyui_service as service

FILL_PROC = "gimphoto-generative-fill"
IMAGE_PROC = "gimphoto-generate-image"
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
# Around the selection in the thumbnails, as a share of its larger side
THUMB_CONTEXT = 0.25
NAME_CHARS = 40


# ------------------------------------------------------------- backend


def backend():
    """(state, url) as comfyui-service found them at startup."""
    try:
        parasite = Gimp.get_parasite(service.PARASITE)
    except Exception:
        parasite = None
    if parasite is None:
        return "unknown", service.url_for(service.DEFAULT_PORT)
    info = json.loads(bytes(parasite.get_data()).decode())
    return info.get("state", "unknown"), info.get("url", service.url_for(service.DEFAULT_PORT))


def ready(state, url, what, waiting=None):
    """Raise a ComfyUIError saying what is missing, or wait while GIMPhoto's
    ComfyUI is still starting. Plain HTTP: safe in the worker thread."""
    if state == "missing" and not api.is_up(url):
        raise api.ComfyUIError(api.missing_message(what))
    if not api.wait_until_up(url, progress=waiting):
        raise api.ComfyUIError(
            f"The local AI (ComfyUI at {url}) is not answering. It starts with GIMPhoto; "
            "if it does not, see: systemctl --user status comfyui"
        )


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


def load_cropped(path, box):
    """A new image from the PNG at path, cropped to box (None: whole)."""
    img = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(path))
    if box:
        x, y, w, h = box
        img.crop(w, h, x, y)
    return img


def add_variation_layer(image, path, name, box=None, at=None, mask_path=None, size=None, place=(None, 0)):
    """The variation PNG as a new layer above the selected one: cropped to
    box (in the PNG), put at `at` (in the image) and masked by mask_path
    (Generative Fill), or scaled to size and at the canvas origin (Generate
    Image). place: the parent and position it goes in. Returns the layer."""
    src_image = load_cropped(path, box)
    try:
        layer = Gimp.Layer.new_from_drawable(src_image.get_layers()[0], image)
    finally:
        src_image.delete()
    layer.set_name(name)
    image.insert_layer(layer, *place)
    if size and (layer.get_width(), layer.get_height()) != size:
        layer.scale(size[0], size[1], False)
    layer.set_offsets(*(at or (0, 0)))
    if mask_path:
        # written into the mask before it is added: a mask made from a
        # selection would need the selection, which the person may have
        # changed while the window was open
        mask_image = load_cropped(mask_path, box)
        try:
            mask = layer.create_mask(Gimp.AddMaskType.WHITE)
            rect = Gegl.Rectangle.new(0, 0, layer.get_width(), layer.get_height())
            target = mask.get_buffer()
            mask_image.get_layers()[0].get_buffer().copy(rect, Gegl.AbyssPolicy.NONE, target, rect)
            target.flush()
        finally:
            mask_image.delete()
        if not layer.has_alpha():
            layer.add_alpha()
        layer.add_mask(mask)
    return layer


# ------------------------------------------------------------- jobs


class Job:
    """What one Generate makes, and how its result becomes a layer."""

    def __init__(self, image, kind, tmp):
        self.image = image
        self.kind = kind  # "fill" or "image"
        self.tmp = tmp
        self.box = self.local_box = self.region = None
        self.layer_box = self.layer_at = None
        self.image_png = self.mask_png = None
        self.size = (image.get_width(), image.get_height())
        # new layers go above the layer selected when the window opened:
        # previews change the selection, so it is remembered here
        self.selected = image.get_selected_layers()
        self.place = (None, 0)
        if self.selected:
            top = self.selected[0]
            self.place = (top.get_parent(), image.get_item_position(top))
        self.extend = kind == "fill" and empty_share(image) > EMPTY_SHARE
        if kind == "fill":
            self.box = self.local_box = selection_box(image)
            if self.extend:
                # only the empty area and a little picture around it
                self.region = grown(self.box, EXTEND_CONTEXT, *self.size)
                x, y, w, h = self.box
                self.local_box = (x - self.region[0], y - self.region[1], w, h)
            self.image_path = os.path.join(tmp, "image.png")
            self.mask_path = os.path.join(tmp, "mask.png")
            visible_png(image, self.image_path, self.region)
            selection_png(image, self.mask_path, self.region)
            # the layer: the selection, or a little more where it fades
            # into the picture
            self.layer_mask_path = self.mask_path
            self.layer_box, self.layer_at = self.local_box, self.box[:2]
            if self.extend:
                self.layer_mask_path = os.path.join(tmp, "layer-mask.png")
                selection_png(image, self.layer_mask_path, self.region, blend=EXTEND_BLEND)
                rw, rh = self.region[2:]
                self.layer_box = grown(self.local_box, EXTEND_BLEND, rw, rh)
                self.layer_at = (self.region[0] + self.layer_box[0], self.region[1] + self.layer_box[1])
            with open(self.image_path, "rb") as f:
                self.image_png = f.read()
            with open(self.mask_path, "rb") as f:
                self.mask_png = f.read()

    @property
    def title(self):
        return "Generative Fill" if self.kind == "fill" else "Generate Image"

    def make(self, url, prompt, model, progress=None):
        """One variation as PNG bytes (worker thread: no GIMP calls)."""
        if self.extend:
            prompt = f"{EXTEND_PROMPT}, {prompt}" if prompt else EXTEND_PROMPT
            return client.inpaint(EXTEND_MODEL, self.image_png, self.mask_png, prompt, url=url, progress=progress)
        if self.kind == "fill":
            return client.inpaint(model, self.image_png, self.mask_png, prompt or None, url=url, progress=progress)
        w, h = client.work_size(*self.size)
        return client.generate(prompt, w, h, url=url, progress=progress)

    def apply(self, path, prompt):
        if self.kind == "fill":
            return add_variation_layer(
                self.image,
                path,
                layer_name("Generative Fill", prompt),
                self.layer_box,
                self.layer_at,
                self.layer_mask_path,
                place=self.place,
            )
        return add_variation_layer(self.image, path, layer_name("Generated", prompt), size=self.size, place=self.place)

    def thumbnail(self, path):
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
        if self.local_box:
            x, y, w, h = self.local_box
            margin = round(THUMB_CONTEXT * max(w, h))
            x0, y0 = max(0, x - margin), max(0, y - margin)
            x1 = min(pixbuf.get_width(), x + w + margin)
            y1 = min(pixbuf.get_height(), y + h + margin)
            pixbuf = pixbuf.new_subpixbuf(x0, y0, x1 - x0, y1 - y0)
        scale = THUMB / float(max(pixbuf.get_width(), pixbuf.get_height()))
        return pixbuf.scale_simple(
            max(1, round(pixbuf.get_width() * scale)),
            max(1, round(pixbuf.get_height() * scale)),
            GdkPixbuf.InterpType.BILINEAR,
        )


# ------------------------------------------------------------- window


class GenerateDialog:
    """Prompt, Generate, the variations as they come, OK to keep one."""

    def __init__(self, job, prompt, model):
        self.job = job
        self.state, self.url = backend()
        self.stop = threading.Event()
        self.running = False
        self.paths = []
        self.preview = None
        self.chosen = None

        self.dialog = GimpUi.Dialog(title=job.title, role=job.title.lower().replace(" ", "-"))
        self.dialog.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        self.ok = self.dialog.add_button("_OK", Gtk.ResponseType.OK)
        self.ok.set_sensitive(False)
        self.dialog.set_default_size(760, -1)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, border_width=12)
        self.dialog.get_content_area().pack_start(box, True, True, 0)

        row = Gtk.Box(spacing=8)
        self.prompt = Gtk.Entry(text=prompt or "", hexpand=True, activates_default=False)
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
            self.model.set_active_id(model if model in dict(MODELS) else MODELS[0][0])
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
        self.flow.connect("selected-children-changed", self.on_selected)
        scroller = Gtk.ScrolledWindow(min_content_height=THUMB + 24)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.add(self.flow)
        box.pack_start(scroller, True, True, 0)

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
        """Worker thread: HTTP only; the window is updated with idle_add."""
        try:
            ready(
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

                png = self.job.make(self.url, prompt, model, progress=tick)
                if self.stop.is_set():
                    break
                path = os.path.join(self.job.tmp, f"variation-{len(self.paths) + n}-{time.monotonic_ns()}.png")
                with open(path, "wb") as f:
                    f.write(png)
                GLib.idle_add(self.add_variation, path, prompt)
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

    def add_variation(self, path, prompt):
        self.paths.append((path, prompt))
        image = Gtk.Image.new_from_pixbuf(self.job.thumbnail(path))
        image.set_tooltip_text(f"Variation {len(self.paths)}")
        self.flow.add(image)
        image.show()
        if not self.flow.get_selected_children():
            self.flow.select_child(image.get_parent())
        return False

    def on_selected(self, flow):
        children = flow.get_selected_children()
        if not children:
            return
        index = children[0].get_index()
        self.chosen = self.paths[index]
        self.ok.set_sensitive(True)
        self.show_preview()

    def show_preview(self):
        """The chosen variation on the canvas, outside the undo history."""
        image = self.job.image
        image.undo_freeze()
        try:
            self.remove_preview(frozen=True)
            path, prompt = self.chosen
            self.preview = self.job.apply(path, prompt)
        finally:
            image.undo_thaw()
        Gimp.displays_flush()

    def remove_preview(self, frozen=False):
        if self.preview is None:
            return
        image = self.job.image
        if not frozen:
            image.undo_freeze()
        try:
            if self.preview.is_valid():
                image.remove_layer(self.preview)
            selected = [layer for layer in self.job.selected if layer.is_valid()]
            if selected:
                image.set_selected_layers(selected)
        finally:
            self.preview = None
            if not frozen:
                image.undo_thaw()

    # -- result

    def run(self):
        """The chosen (path, prompt), or None."""
        response = self.dialog.run()
        if self.running:
            self.stop.set()
            client.cancel(self.url)
        self.remove_preview()
        Gimp.displays_flush()
        self.dialog.destroy()
        return self.chosen if response == Gtk.ResponseType.OK else None


# ------------------------------------------------------------- procedures


def apply_result(job, path, prompt):
    image = job.image
    image.undo_group_start()
    try:
        layer = job.apply(path, prompt)
        image.set_selected_layers([layer])
    finally:
        image.undo_group_end()
    Gimp.displays_flush()


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
        job = Job(image, kind, tmp)
        if run_mode == Gimp.RunMode.INTERACTIVE:
            GimpUi.init("generative-fill")
            chosen = GenerateDialog(job, prompt, model).run()
            if chosen is None:
                return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())
            path, prompt = chosen
            config.set_property("prompt", prompt)
        else:
            if kind == "image" and not prompt.strip():
                raise api.ComfyUIError("Generate Image needs a prompt.")
            state, url = backend()
            Gimp.progress_init(job.title)
            ready(state, url, job.title)
            path = os.path.join(tmp, "variation.png")
            with open(path, "wb") as f:
                f.write(job.make(url, prompt, model, progress=lambda _s: Gimp.progress_pulse()))
        apply_result(job, path, prompt)
    except Exception as e:
        return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error(str(e)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


def run_fill(procedure, run_mode, image, drawables, config, data):
    return run_job("fill", procedure, run_mode, image, config)


def run_image(procedure, run_mode, image, drawables, config, data):
    return run_job("image", procedure, run_mode, image, config)


class GenerativeFill(Gimp.PlugIn):
    def do_set_i18n(self, procname):
        return False

    def do_query_procedures(self):
        return [FILL_PROC, IMAGE_PROC]

    def do_create_procedure(self, name):
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


Gimp.main(GenerativeFill.__gtype__, sys.argv)
