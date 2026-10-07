# Run by scripts/smoke inside the installed GIMPhoto (python3 with GEGL):
# gegl:paint-select, which GIMPhoto builds for Quick Selection (Flathub's
# GEGL leaves it out), grows a stroke to the edges of what it is painted on.
# A 200x100 picture, red on the left and blue on the right; a short stroke
# in the red half selects the red half and nothing of the blue one.
# Prints "ok" or the reason.
import struct

import gi

gi.require_version("Gegl", "0.4")
from gi.repository import Gegl  # noqa: E402

Gegl.init(None)

W, H = 200, 100
RECT = Gegl.Rectangle.new(0, 0, W, H)


def buffer(fmt, color):
    buf = Gegl.Buffer.new(fmt, 0, 0, W, H)
    buf.set_color(RECT, Gegl.Color.new(color))
    return buf


def main():
    if not Gegl.has_operation("gegl:paint-select"):
        return "gegl:paint-select is missing"

    picture = buffer("R'G'B' float", "rgb(0.8, 0.1, 0.1)")
    picture.set_color(Gegl.Rectangle.new(100, 0, 100, H), Gegl.Color.new("rgb(0.1, 0.2, 0.8)"))
    selection = buffer("Y float", "rgb(0, 0, 0)")
    # grey: not painted; white: painted over (the tool's trimap)
    scribbles = buffer("Y float", "rgb(0.5, 0.5, 0.5)")
    scribbles.set_color(Gegl.Rectangle.new(30, 45, 30, 10), Gegl.Color.new("rgb(1, 1, 1)"))

    graph = Gegl.Node()
    src = graph.create_child("gegl:buffer-source")
    src.set_property("buffer", selection)
    aux = graph.create_child("gegl:buffer-source")
    aux.set_property("buffer", picture)
    aux2 = graph.create_child("gegl:buffer-source")
    aux2.set_property("buffer", scribbles)
    op = graph.create_child("gegl:paint-select")
    out = Gegl.Buffer.new("Y float", 0, 0, W, H)
    sink = graph.create_child("gegl:write-buffer")
    sink.set_property("buffer", out)
    src.connect_to("output", op, "input")
    aux.connect_to("output", op, "aux")
    aux2.connect_to("output", op, "aux2")
    op.connect_to("output", sink, "input")
    sink.process()

    def value(x, y):
        pixel = out.get(Gegl.Rectangle.new(x, y, 1, 1), 1.0, "Y float", Gegl.AbyssPolicy.NONE)
        return struct.unpack("f", bytes(pixel))[0]

    left = [value(x, y) for x in (5, 50, 95) for y in (5, 50, 95)]
    right = [value(x, y) for x in (105, 150, 195) for y in (5, 50, 95)]
    if min(left) < 0.5:
        return f"the painted red half is not all selected: {left}"
    if max(right) > 0.5:
        return f"the blue half is selected too: {right}"
    return "ok"


print(main())
