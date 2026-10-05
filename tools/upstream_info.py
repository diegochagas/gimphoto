#!/usr/bin/env python3
"""Facts the shell scripts need from Flathub's GIMP recipe.

tools/upstream_info.py gimp-source      "<git url> <tag> <commit>" of GIMP
tools/upstream_info.py gimp-version     e.g. "3.2.6", from the tag
tools/upstream_info.py flathub-patches  Flathub's own GIMP patches, one per
                                        line, relative to flatpak/
"""

import json
import sys
from pathlib import Path

UPSTREAM = Path(__file__).resolve().parent.parent / "flatpak" / "upstream" / "org.gimp.GIMP.json"


def gimp_module(manifest):
    for module in manifest["modules"]:
        if isinstance(module, dict) and module.get("name") == "gimp":
            return module
    sys.exit("Flathub's manifest has no 'gimp' module")


def main(argv):
    if len(argv) != 2:
        sys.exit(__doc__)
    module = gimp_module(json.loads(UPSTREAM.read_text()))
    git = next(s for s in module["sources"] if s.get("type") == "git")
    if argv[1] == "gimp-source":
        print(git["url"], git["tag"], git["commit"])
    elif argv[1] == "gimp-version":
        print(git["tag"].removeprefix("GIMP_").replace("_", "."))
    elif argv[1] == "flathub-patches":
        for source in module["sources"]:
            if source.get("type") == "patch":
                for path in source["paths"]:
                    print(f"upstream/{path}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
