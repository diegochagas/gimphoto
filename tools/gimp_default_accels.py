#!/usr/bin/env python3
"""GIMP's default keyboard shortcuts, read from its source.

    tools/gimp_default_accels.py [work/gimp]    print "action<TAB>accel,accel" lines

Two sources in GIMP 3.2's code:
  - action tables in app/actions/*-actions.c:
        { "image-duplicate", ICON, NC_(...), NULL, { "<primary>D", NULL }, ...
  - tool registrations in app/tools/*.c, whose action is "tools-<name>":
        "gimp-rect-select-tool", ..., N_("_Rectangle Select"), "R",
Used by tools/make_keymap.py to unbind GIMP's own use of every key the
Photoshop keymap takes.
"""

import re
import sys
from pathlib import Path

# { "action-name", ... { "accel", ..., NULL } ... }: the first brace list of
# strings (or accel macros) after the name, before the next entry's line
# (an entry's first line is its name and icon, a macro, NULL or a string;
# an accel list like { "1", "KP_1", NULL } goes on)
START = r'^\s*\{\s*"[a-z0-9][a-z0-9-]*"\s*,\s*(?:[A-Z][A-Z0-9_]*|"[^"]*")\s*,\s*(?:/\*[^\n]*\*/)?\s*$'
ENTRY = re.compile(
    r'^\s*\{\s*"([a-z0-9][a-z0-9-]*)"\s*,(?=\s*(?:[A-Z][A-Z0-9_]*|"[^"]*")\s*,\s*(?:/\*[^\n]*\*/)?\s*$)(.*?)(?='
    + START
    + r"|^\};)",
    re.S | re.M,
)
ACCELS = re.compile(r'\{\s*((?:(?:"[^"]*"|[A-Z][A-Z0-9_]*(?:\s*\("[^"]*"\))?)\s*,\s*)*)NULL\s*\}')
ACCEL = re.compile(r'"([^"]*)"|([A-Z][A-Z0-9_]*)')
# #define NAME "accel": the first definition wins (the non-macOS branch)
DEFINE = re.compile(r'^#define\s+([A-Z][A-Z0-9_]*)\s+"([^"]*)"', re.M)
TOOL = re.compile(r'"gimp-([a-z0-9-]+)-tool"\s*,(?:[^;]*?)N_\("[^"]*"\)\s*,\s*("[^"]*"|NULL)', re.S)


def action_accels(source):
    result = {}
    for path in sorted((source / "app" / "actions").glob("*-actions.c")):
        text = path.read_text(errors="replace")
        macros = {}
        for macro, value in DEFINE.findall(text):
            macros.setdefault(macro, value)
        for name, body in ENTRY.findall(text):
            m = ACCELS.search(body)
            if not m:
                continue
            accels = [lit or macros.get(macro, "") for lit, macro in ACCEL.findall(m.group(1))]
            result.setdefault(name, [])
            result[name] += [a for a in accels if a and a not in result[name]]
    return result


def tool_accels(source):
    result = {}
    for path in sorted((source / "app" / "tools").glob("*.c")):
        for name, accel in TOOL.findall(path.read_text(errors="replace")):
            result["tools-" + name] = [] if accel == "NULL" else [accel.strip('"')]
    return result


def default_accels(source):
    accels = action_accels(Path(source))
    accels.update(tool_accels(Path(source)))
    return accels


def main(argv):
    source = Path(argv[1] if len(argv) > 1 else "work/gimp")
    if not (source / "app" / "actions").is_dir():
        sys.exit(f"{source} is not a GIMP source tree (run scripts/source)")
    for name, accels in sorted(default_accels(source).items()):
        print(f"{name}\t{','.join(accels)}")


if __name__ == "__main__":
    main(sys.argv)
