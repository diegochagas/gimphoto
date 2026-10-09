#!/usr/bin/env bash
# Run by scripts/smoke: opening an image while GIMPhoto is open hands it to
# the open GIMPhoto (a new tab) instead of starting another one, as GIMP
# does. GIMP finds the running instance through a name on the session bus,
# which a Flatpak may only own under its app ID.
#
# Everything happens on a private session bus (dbus-run-session) and a
# private X display (Xvfb), with a throwaway profile, so the GIMPhoto the
# person has open is never reached. Steps: start GIMPhoto with a window;
# wait for it to own its bus name; open an image with a second launch, which
# must hand it over and exit; ask the first GIMPhoto (a batch command, which
# a launch also hands over) which images it has open; quit it.
#
#   tests/smoke_single_instance.sh APP_ID REPORT
#
# Writes "ok", "skip: <why>" or the reason it failed to REPORT.
set -uo pipefail

app="$1"
report="$2"
bus_name="$app.UI"

xvfb="${GIMPHOTO_XVFB:-$(command -v Xvfb || true)}"
[[ -x "$xvfb" ]] || xvfb="$(dirname "$0")/../work/xvfb/root/usr/bin/Xvfb"
if [[ ! -x "$xvfb" ]] || ! command -v dbus-run-session >/dev/null || ! command -v gdbus >/dev/null; then
    echo "skip: needs Xvfb, dbus-run-session and gdbus" >"$report"
    exit 0
fi

tmp_root="${GIMPHOTO_SMOKE_TMP:-$PWD/work}"
mkdir -p "$tmp_root"
dir="$(mktemp -d "$tmp_root/single-instance.XXXXXX")"
trap 'rm -rf "$dir"' EXIT
cp "$(dirname "$0")/fixtures/clipping-mask.xcf" "$dir/image.xcf"
mkdir -p "$dir/profile"

export app bus_name dir xvfb report
# the script runs inside the private session: its variables are its own
# shellcheck disable=SC2016
dbus-run-session -- bash -c '
    set -uo pipefail
    fail() { echo "$1" >"$report"; }
    # a display number nothing uses yet
    n=90
    while [[ -e "/tmp/.X11-unix/X$n" || -e "/tmp/.X$n-lock" ]]; do n=$((n + 1)); done
    display=":$n"
    "$xvfb" "$display" -screen 0 1280x800x24 -nolisten tcp >/dev/null 2>&1 &
    xvfb_pid=$!
    export DISPLAY="$display"
    run=(flatpak run --filesystem="$dir" --env=GIMP3_DIRECTORY="$dir/profile" --env=GIMPHOTO_COMFYUI=off "$app")
    "${run[@]}" --no-splash >"$dir/first.log" 2>&1 &
    first=$!
    owner() {
        gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
            --method org.freedesktop.DBus.NameHasOwner "$bus_name" 2>/dev/null | grep -q true
    }
    for _ in $(seq 120); do owner && break; sleep 1; done
    if ! owner; then
        fail "the running GIMPhoto does not own $bus_name on the session bus: $(grep -m1 "could not be acquired" "$dir/first.log")"
    elif ! timeout 60 "${run[@]}" "$dir/image.xcf" >"$dir/second.log" 2>&1; then
        fail "a second launch with an image did not hand it over and exit (it started its own GIMPhoto)"
    elif ! timeout 60 "${run[@]}" --batch-interpreter=python-fu-eval \
        -b "from gi.repository import Gimp; open(\"$dir/open.txt\", \"w\").write(\"|\".join(i.get_file().get_basename() for i in Gimp.get_images() if i.get_file()))" \
        >"$dir/third.log" 2>&1; then
        fail "a batch command was not handed to the running GIMPhoto"
    else
        for _ in $(seq 30); do [[ -s "$dir/open.txt" ]] && break; sleep 1; done
        if [[ "$(cat "$dir/open.txt" 2>/dev/null)" == image.xcf ]]; then
            echo ok >"$report"
        else
            fail "the running GIMPhoto has [$(cat "$dir/open.txt" 2>/dev/null)] open, not the image the second launch passed"
        fi
    fi
    # quit the test GIMPhoto, then make sure nothing is left
    timeout 30 "${run[@]}" --batch-interpreter=python-fu-eval \
        -b "from gi.repository import Gimp; p = Gimp.get_pdb().lookup_procedure(\"gimp-quit\"); c = p.create_config(); c.set_property(\"force\", True); p.run(c)" \
        >/dev/null 2>&1 || true
    for _ in $(seq 20); do kill -0 "$first" 2>/dev/null || break; sleep 1; done
    kill "$first" 2>/dev/null
    wait "$first" 2>/dev/null
    kill "$xvfb_pid" 2>/dev/null
' >"$dir/session.log" 2>&1
[[ -s "$report" ]] || echo "did not run" >"$report"
