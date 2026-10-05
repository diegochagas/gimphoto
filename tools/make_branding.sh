#!/usr/bin/env bash
# Render GIMPhoto's icon and splash screen from their sources (Inkscape).
#
#   tools/make_branding.sh
#
# branding/icon-source.svg   -> branding/icon.svg (text as paths, so it looks
#                               the same without the font) and
#                               branding/icons/<size>.png
# branding/splash-source.svg -> branding/splash.png
# The rendered files are committed; the build installs them over GIMP's
# (tools/make_manifest.py, module gimphoto-defaults). Font: DejaVu Sans Bold.
set -euo pipefail
cd "$(dirname "$0")/../branding"

sizes=(16 22 24 32 36 48 64 72 96 128 192 256 512)
inkscape --export-text-to-path --export-plain-svg --export-filename=icon.svg icon-source.svg
inkscape --export-filename=splash.png splash-source.svg
mkdir -p icons
for size in "${sizes[@]}"; do
    inkscape -w "$size" -h "$size" --export-filename="icons/$size.png" icon.svg
done
echo "rendered branding/icon.svg, branding/icons/*.png, branding/splash.png"
