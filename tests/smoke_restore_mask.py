# Run by scripts/smoke with the installed GIMPhoto's python3: Photo
# Restoration's damage mask (plugins/photo-restoration/restore_mask.py) on
# the numpy, scipy and Pillow shipped in the app (python-wheels.tsv). A grey
# "scan" with a white blotch, and the "model's" picture with the blotch
# painted over: the mask covers the blotch, and nothing else of the scan.
# Prints "ok" or the reason.
import os
import sys
import tempfile

PLUGIN = os.environ.get("GIMPHOTO_PHOTO_RESTORATION", "/app/lib/gimp/3.0/plug-ins/photo-restoration")
sys.path.insert(0, PLUGIN)


def main():
    try:
        import numpy as np
        from PIL import Image

        import restore_mask
    except ImportError as e:
        return f"cannot import: {e}"
    tmp = tempfile.mkdtemp(prefix="gimphoto-smoke-restore-")
    rng = np.random.default_rng(0)
    # a textured grey print, so the alignment has something to lock onto
    scan = np.clip(128 + rng.normal(0, 12, (240, 320, 3)), 0, 255).astype(np.uint8)
    model = scan.copy()
    scan[100:140, 150:200] = 250  # the blotch on the print
    paths = [os.path.join(tmp, n) for n in ("scan.png", "model.png", "out.png")]
    Image.fromarray(scan).save(paths[0])
    Image.fromarray(model).save(paths[1])
    regions, _share = restore_mask.process(*paths)
    alpha = np.asarray(Image.open(paths[2]))[..., 3]
    if regions != 1:
        return f"{regions} repaired regions, not 1"
    if alpha[120, 175] < 200:
        return "the blotch is not in the mask"
    if alpha[20, 20] or alpha[220, 300]:
        return "the mask covers undamaged parts of the scan"
    return "ok"


print(main())
