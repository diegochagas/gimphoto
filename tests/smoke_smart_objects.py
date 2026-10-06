# Run by scripts/smoke inside the installed GIMPhoto (python-fu-eval):
# Smart Objects. Two layers of a saved image become one smart object (a link
# layer showing an XCF of their own, next to the image) at the same place;
# scaled to 15% and back it is still sharp (non-destructive, as Photoshop's);
# Replace Contents makes it show another file. In a PSD it is a Photoshop
# smart object (its contents embedded, on the same corners, rotated too),
# and opening that PSD gives a smart object back.
# Writes "ok" or a reason to the file in GIMPHOTO_SMOKE_OUT.
import json
import os
import subprocess
import tempfile

from gi.repository import Gegl, Gimp, Gio

PSD_TEXT = "/app/lib/gimp/3.0/plug-ins/psd-text"
NODE = "/app/lib/gimphoto/node/bin/node"


def rgb(drawable, x, y):
    return drawable.get_pixel(x, y).get_rgba()[:3]


def near(c, want, tol=0.08):
    return all(abs(a - b) <= tol for a, b in zip(c, want))


def filled_layer(img, name, x, y, w, h, colour):
    layer = Gimp.Layer.new(img, name, w, h, Gimp.ImageType.RGBA_IMAGE, 100, Gimp.LayerMode.NORMAL)
    img.insert_layer(layer, None, 0)
    layer.set_offsets(x, y)
    Gimp.context_set_foreground(Gegl.Color.new(colour))
    layer.edit_fill(Gimp.FillType.FOREGROUND)
    return layer


def run(proc_name, img, **props):
    proc = Gimp.get_pdb().lookup_procedure(proc_name)
    if proc is None:
        raise RuntimeError(f"{proc_name} is not registered")
    config = proc.create_config()
    config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
    config.set_property("image", img)
    config.set_core_object_array("drawables", img.get_selected_layers())
    for key, value in props.items():
        config.set_property(key, value)
    result = proc.run(config)
    if result.index(0) != Gimp.PDBStatusType.SUCCESS:
        raise RuntimeError(f"{proc_name} failed: {result.index(1) if result.length() > 1 else '?'}")


def flat(img, x, y):
    copy = img.duplicate()
    copy.flatten()
    value = rgb(copy.get_layers()[0], x, y)
    copy.delete()
    return value


def psd_smart_objects(tmp, psd):
    """The placed layers ag-psd finds in psd (as Photoshop will)."""
    out = os.path.join(tmp, "info.json")
    r = subprocess.run(
        [NODE, os.path.join(PSD_TEXT, "psd_text_info.mjs"), psd, out],
        capture_output=True,
        text=True,
        cwd=PSD_TEXT,
        timeout=120,
    )
    if r.returncode != 0:
        raise RuntimeError(f"ag-psd could not read {psd}: {r.stderr.strip()[-200:]}")
    return [lyr["smart"] for lyr in json.load(open(out))["layers"] if lyr.get("smart")]


def instances_round_trip(tmp, img, link):
    """Two smart objects showing one file are instances of one Photoshop
    smart object (one embedded file), and open again sharing one XCF; a
    file already in the smart objects folder is left alone."""
    twin = img.duplicate()
    first = [lyr for lyr in twin.get_layers() if isinstance(lyr, Gimp.LinkLayer)][0]
    second = first.copy()
    twin.insert_layer(second, None, 0)
    second.set_offsets(10, 10)
    psd = os.path.join(tmp, "twins.psd")
    Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, twin, Gio.File.new_for_path(psd), None)
    found = psd_smart_objects(tmp, psd)
    if len(found) != 2 or found[0]["id"] != found[1]["id"]:
        return f"twins.psd: {len(found)} smart objects, ids {[f['id'] for f in found]}: want 2 instances of one"
    folder = os.path.join(tmp, "twins smart objects")
    os.makedirs(folder, exist_ok=True)
    keep = os.path.join(folder, os.path.splitext(found[0]["file"])[0] + ".psd")
    open(keep, "w").write("mine")
    again = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(psd))
    paths = {lyr.get_file().get_path() for lyr in again.get_layers() if isinstance(lyr, Gimp.LinkLayer)}
    if len(paths) != 1:
        return f"twins.psd reopened: the instances show {sorted(paths)}, want one shared XCF"
    if not os.path.exists(keep) or open(keep).read() != "mine":
        return f"twins.psd reopened: {keep}, already in the folder, was overwritten or removed"
    return "ok"


def close(a, b, tol=1.5):
    return len(a) == len(b) and all(abs(x - y) <= tol for x, y in zip(a, b))


def psd_round_trip(tmp, img, link, name):
    """Export img to name.psd: one smart object on link's corners, its
    contents embedded as a PSD; open it again: one link layer on the same
    corners, its contents an XCF in "name smart objects"."""
    corners = list(link.get_corners()[0])
    psd = os.path.join(tmp, name + ".psd")
    Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, img, Gio.File.new_for_path(psd), None)
    found = psd_smart_objects(tmp, psd)
    if len(found) != 1:
        return f"{name}.psd: {len(found)} smart objects in the file, want 1"
    smart = found[0]
    if not close(smart["corners"], corners):
        return f"{name}.psd: the smart object is placed on {smart['corners']}, want {corners}"
    if not smart["data"] or open(smart["data"], "rb").read(4) != b"8BPS":
        return f"{name}.psd: the smart object's contents are not an embedded PSD"
    again = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(psd))
    links = [lyr for lyr in again.get_layers() if isinstance(lyr, Gimp.LinkLayer)]
    if len(links) == 1 and links[0].get_name() != link.get_name():
        return f"{name}.psd reopened: the smart object is named {links[0].get_name()!r}, want {link.get_name()!r}"
    if len(links) != 1:
        names = [lyr.get_name() for lyr in again.get_layers()]
        return f"{name}.psd reopened: layers are {names}, want one smart object"
    path = links[0].get_file().get_path()
    if os.path.dirname(path) != os.path.join(tmp, name + " smart objects") or not path.endswith(".xcf"):
        return f"{name}.psd reopened: its contents are {path}"
    if not close(list(links[0].get_corners()[0]), corners):
        return f"{name}.psd reopened: on {list(links[0].get_corners()[0])}, want {corners}"
    return "ok"


def check(tmp):
    img = Gimp.Image.new(300, 200, Gimp.ImageBaseType.RGB)
    filled_layer(img, "Background", 0, 0, 300, 200, "#ffffff")
    red = filled_layer(img, "red", 40, 40, 100, 100, "#ff0000")
    blue = filled_layer(img, "blue", 120, 60, 80, 60, "#0000ff")
    xcf = os.path.join(tmp, "picture.xcf")
    Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, img, Gio.File.new_for_path(xcf), None)

    img.set_selected_layers([red, blue])
    run("smart-object-convert", img)
    layers = img.get_layers()
    links = [lyr for lyr in layers if isinstance(lyr, Gimp.LinkLayer)]
    if len(layers) != 2 or len(links) != 1:
        return f"convert: layers are {[lyr.get_name() for lyr in layers]}, want Background and one smart object"
    link = links[0]
    path = link.get_file().get_path()
    if os.path.dirname(path) != os.path.join(tmp, "picture smart objects") or not os.path.exists(path):
        return f"convert: the contents file is {path}, want it in 'picture smart objects' next to the image"
    inside = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, link.get_file())
    names = [lyr.get_name() for lyr in inside.get_layers()]
    inside.delete()
    if names != ["blue", "red"]:
        return f"convert: the layers inside are {names}, want blue and red"
    if (link.get_offsets()[1:], link.get_width(), link.get_height()) != ((40, 40), 160, 100):
        return f"convert: the smart object is at {link.get_offsets()[1:]} {link.get_width()}x{link.get_height()}"
    if not (near(flat(img, 50, 50), (1, 0, 0)) and near(flat(img, 190, 90), (0, 0, 1))):
        return "convert: the image does not look the same"
    # saved and opened again, the smart object keeps its name (GIMP renamed
    # link layers after their file when loading an XCF)
    link.set_name("Logo")
    Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, img, Gio.File.new_for_path(xcf), None)
    reopened = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(xcf))
    names = [lyr.get_name() for lyr in reopened.get_layers() if isinstance(lyr, Gimp.LinkLayer)]
    reopened.delete()
    if names != ["Logo"]:
        return f"picture.xcf reopened: the smart object is named {names}, want ['Logo']"

    # scaled down and back up: re-rendered from the file, still sharp
    # (scale() keeps the image origin fixed, so put it back in place)
    link.scale(24, 15, False)
    link.scale(160, 100, False)
    link.set_offsets(40, 40)
    edge = flat(img, 41, 41)
    if not near(edge, (1, 0, 0), 0.05):
        return f"scale 15% and back: the corner is {edge}, not sharp red (destructive?)"

    result = psd_round_trip(tmp, img, link, "upright")
    if result != "ok":
        return result
    again = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(os.path.join(tmp, "upright.psd")))
    if not (near(flat(again, 50, 50), (1, 0, 0)) and near(flat(again, 190, 90), (0, 0, 1))):
        return "upright.psd reopened: the smart object does not look the same"
    result = instances_round_trip(tmp, img, link)
    if result != "ok":
        return result
    rotated = img.duplicate()
    turned = [lyr for lyr in rotated.get_layers() if isinstance(lyr, Gimp.LinkLayer)][0]
    turned = turned.transform_rotate(0.5, True, 0, 0)
    c = list(turned.get_corners()[0])
    if abs(c[1] - c[3]) < 10:
        return f"rotated 0.5 rad: the smart object's corners are {c}, not rotated (kept non-destructively?)"
    result = psd_round_trip(tmp, rotated, turned, "rotated")
    if result != "ok":
        return result

    green = Gimp.Image.new(160, 100, Gimp.ImageBaseType.RGB)
    filled_layer(green, "g", 0, 0, 160, 100, "#00ff00")
    png = os.path.join(tmp, "green.png")
    Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, green, Gio.File.new_for_path(png), None)
    img.set_selected_layers([link])
    run("smart-object-replace", img, file=Gio.File.new_for_path(png))
    if not near(flat(img, 50, 50), (0, 1, 0)):
        return f"replace: the smart object shows {flat(img, 50, 50)}, not the green file"
    return "ok"


with tempfile.TemporaryDirectory() as tmp:
    try:
        result = check(tmp)
    except Exception as e:  # report, do not hang the batch run
        result = f"{type(e).__name__}: {e}"
open(os.environ["GIMPHOTO_SMOKE_OUT"], "w").write(result + "\n")
