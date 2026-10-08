# Modern Photo (local AI): what the model is asked, and whether the photo is
# black and white. Plain Python, no GIMP, no numpy: tests/test_modern_photo.py
# runs it with the gate.
#
# The prompt is photo-restore's modernize-photos one
# (github.com/diegochagas/photo-restore, modernize-photos/scripts/modernize.py).

import math

import comfyui_client as client

PROMPT = (
    "Turn this old photo into the same scene photographed today with a modern iPhone (latest Pro model, "
    "main 24 mm camera): tack-sharp focus and fine detail, clean low-noise image with no film grain, "
    "Smart HDR dynamic range with detail in the highlights and shadows, accurate white balance and "
    "natural, true-to-life colours, natural skin texture, crisp edges. Remove everything that makes it "
    "look old: fading, yellowing, colour casts, blur, softness, grain, dust, scratches, stains, creases, "
    "light leaks and the print's paper texture. Keep every person exactly as they are - same face, "
    "identity, age, expression, gaze, hair and pose - and keep their clothes, every object, the place, "
    "the lighting direction, the time of day and the framing. Only the photographic quality changes: "
    "do not modernise clothes, hairstyles, cars or objects, and do not add or remove anyone or anything. "
    "No text, no borders, no watermark."
)
COLORIZE = (
    " The original is black and white: give it realistic, natural colours, as the iPhone would have "
    "captured them in that place and era."
)
KEEP_BW = " Keep it black and white, as the iPhone's black-and-white photo style would render it."

# Spread of the colours around the photo's overall tint (YCbCr chroma):
# black and white or sepia prints stay below ~4.5, faded colour prints are
# above ~7.
MONOCHROME_SPREAD = 5.5


def is_monochrome(rgb):
    """True for a black and white or toned (sepia) photo: `rgb` is 8-bit RGB
    pixels (a small thumbnail is enough). One tint over the whole photo does
    not count as colour; colours that differ from each other do."""
    n = len(rgb) // 3
    if n == 0:
        return True
    cbs, crs = [], []
    for i in range(0, n * 3, 3):
        r, g, b = rgb[i], rgb[i + 1], rgb[i + 2]
        cbs.append(-0.1687 * r - 0.3313 * g + 0.5 * b)
        crs.append(0.5 * r - 0.4187 * g - 0.0813 * b)
    mean_cb, mean_cr = sum(cbs) / n, sum(crs) / n
    variance = sum((cb - mean_cb) ** 2 + (cr - mean_cr) ** 2 for cb, cr in zip(cbs, crs)) / n
    return math.sqrt(variance) < MONOCHROME_SPREAD


def prompt(monochrome, keep_bw):
    if not monochrome:
        return PROMPT
    return PROMPT + (KEEP_BW if keep_bw else COLORIZE)


def modernize(model, image_png, monochrome, keep_bw, url, progress=None):
    """The photo redrawn as if taken today; PNG bytes of the image's size.
    The whole picture is the model's, as gimp-setup's client restore() does
    for repairs (its whole-image edit graph)."""
    width, height = client.png_size(image_png)
    image_name = client._upload(url, "modern.png", image_png)
    work_w, work_h = client.work_size(width, height)
    graph = client._edit_graph(url, model, image_name, prompt(monochrome, keep_bw), work_w, work_h, width, height)
    return client._run(url, graph, progress)["out"]
