# Run by scripts/smoke inside the installed GIMPhoto (python-fu-eval):
# PSD with editable text, both ways. A GIMP text layer with a Layer Style
# (stroke, radial gradient overlay) is exported to PSD: the file must hold
# a Photoshop Type layer with that text and those effects (read back by
# ag-psd, the way Photoshop will find them), and opening the PSD again must
# give an editable GIMP text layer with the same text and Layer Style.
# Writes "ok" or a reason to the file in GIMPHOTO_SMOKE_OUT.
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, "/app/lib/gimp/3.0/plug-ins/layer-style")
from gi.repository import Gegl, Gimp, Gio

import layer_style_engine as E

PLUG_INS = "/app/lib/gimp/3.0/plug-ins"

NODE = "/app/lib/gimphoto/node/bin/node"
PSD_TEXT = os.path.join(PLUG_INS, "psd-text")
TEXT = "GIMPhoto"


def make_image():
    img = Gimp.Image.new(400, 160, Gimp.ImageBaseType.RGB)
    bg = Gimp.Layer.new(img, "Background", 400, 160, Gimp.ImageType.RGB_IMAGE, 100, Gimp.LayerMode.NORMAL)
    img.insert_layer(bg, None, 0)
    Gimp.context_set_foreground(Gegl.Color.new("#ffffff"))
    bg.edit_fill(Gimp.FillType.FOREGROUND)
    font = Gimp.Font.get_by_name("Sans-serif Bold") or Gimp.context_get_font()
    text = Gimp.TextLayer.new(img, TEXT, font, 60.0, Gimp.Unit.pixel())
    img.insert_layer(text, None, 0)
    text.set_offsets(20, 40)
    E.apply_style(
        text,
        {
            "stroke": {**E.DEFAULTS["stroke"], "enabled": True, "size": 4, "color": "#ffffff"},
            "gradient_overlay": {**E.DEFAULTS["gradient_overlay"], "enabled": True, "style": "radial"},
        },
    )
    return img


def check(tmp):
    psd = os.path.join(tmp, "text.psd")
    Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, make_image(), Gio.File.new_for_path(psd), None)
    if not os.path.getsize(psd):
        return "no PSD written"

    # what Photoshop will find: a Type layer with the text and the effects
    info_path = os.path.join(tmp, "info.json")
    r = subprocess.run(
        [NODE, os.path.join(PSD_TEXT, "psd_text_info.mjs"), psd, info_path],
        capture_output=True,
        text=True,
        cwd=PSD_TEXT,
        timeout=120,
    )
    if r.returncode != 0:
        return f"ag-psd could not read the PSD: {r.stderr.strip()[-200:]}"
    layers = json.load(open(info_path))["layers"]
    typed = [lyr for lyr in layers if lyr.get("text")]
    if len(typed) != 1 or "".join(run["text"] for run in typed[0]["text"]["runs"]).strip() != TEXT:
        return f"the PSD has no Type layer saying {TEXT!r}: {[lyr.get('name') for lyr in layers]}"
    style = (typed[0].get("effects") or {}).get("style") or {}
    if not style.get("stroke") or (style.get("gradient_overlay") or {}).get("style") != "radial":
        return f"the Type layer's effects are not stroke + radial gradient overlay: {style}"

    # opening it again: an editable GIMP text layer with its Layer Style
    again = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(psd))
    texts = [lyr for lyr in again.get_layers() if isinstance(lyr, Gimp.TextLayer)]
    if len(texts) != 1 or texts[0].get_text() != TEXT:
        return f"reopened, no editable text layer saying {TEXT!r}: {[lyr.get_name() for lyr in again.get_layers()]}"
    reopened = E.read_style(texts[0])
    if not reopened.get("stroke", {}).get("enabled"):
        return f"reopened, the stroke is not a Layer Style: {reopened}"
    if reopened.get("gradient_overlay", {}).get("style") != "radial":
        return f"reopened, the gradient overlay is not radial: {reopened.get('gradient_overlay')}"
    return "ok"


with tempfile.TemporaryDirectory() as tmp:
    try:
        result = check(tmp)
    except Exception as e:  # report, do not hang the batch run
        result = f"{type(e).__name__}: {e}"
open(os.environ["GIMPHOTO_SMOKE_OUT"], "w").write(result + "\n")
