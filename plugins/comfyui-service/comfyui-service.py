#!/usr/bin/env python3
#
# ComfyUI with GIMPhoto: starts the local ComfyUI when GIMPhoto opens and
# stops it when GIMPhoto closes, freeing the GPU and the RAM a loaded model
# holds. Only if GIMPhoto started it: a ComfyUI already running (started by
# hand, by a script or by GIMP's own launcher) keeps running.
#
# ComfyUI is the `comfyui` systemd user service that linux-mint-setup's
# ComfyUI steps install; GIMPhoto never installs it. Without that service
# GIMPhoto starts alone, and the global parasite "gimphoto-comfyui" says so to
# the AI tools.
#
# A persistent procedure without arguments: GIMP runs it once at startup and
# it stays until GIMP quits (the quit vfunc). The Flatpak sandbox cannot run
# systemctl, so it talks to systemd over the session bus (the manifest's
# --talk-name=org.freedesktop.systemd1). Nothing runs without a user
# interface (batch runs, scripts/smoke).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.

import json
import os
import sys

import gi

gi.require_version("Gimp", "3.0")
from gi.repository import Gimp, Gio, GLib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comfyui_service as cs

PROC = "gimphoto-comfyui-service"


def bus():
    return Gio.bus_get_sync(Gio.BusType.SESSION, None)


def call(connection, path, interface, method, args, reply):
    result = connection.call_sync(
        cs.SYSTEMD_BUS_NAME,
        path,
        interface,
        method,
        args,
        GLib.VariantType.new(reply),
        Gio.DBusCallFlags.NONE,
        5000,
        None,
    )
    return result.unpack()


def unit_property(connection, path, interface, name):
    return call(
        connection,
        path,
        "org.freedesktop.DBus.Properties",
        "Get",
        GLib.Variant("(ss)", (interface, name)),
        "(v)",
    )[0]


def publish(info):
    """Tell the AI tools what was found (global parasite, not saved)."""
    data = json.dumps(info).encode()
    try:
        Gimp.attach_parasite(Gimp.Parasite.new(cs.PARASITE, 0, list(data)))
    except Exception:
        # the AI tools then find nothing and check ComfyUI themselves
        pass


class ComfyuiService(Gimp.PlugIn):
    started = False

    def do_set_i18n(self, procname):
        return False

    def do_query_procedures(self):
        return [PROC]

    def do_create_procedure(self, name):
        procedure = Gimp.Procedure.new(self, name, Gimp.PDBProcType.PERSISTENT, self.run, None)
        procedure.set_documentation(
            "Start the local ComfyUI with GIMPhoto and stop it when GIMPhoto closes",
            "Starts the comfyui systemd user service (installed by linux-mint-setup) "
            "when GIMPhoto opens, if it is not running, and stops it when GIMPhoto "
            "quits, if GIMPhoto started it.",
            name,
        )
        procedure.set_attribution("GIMPhoto", "GIMPhoto contributors", "2026")
        return procedure

    def run(self, procedure, config, data):
        # no user interface (batch runs): leave ComfyUI alone. GIMP passes
        # plug-ins its window class only when it has a GUI (gimp_display_name
        # is not in the Python bindings)
        try:
            if Gimp.wm_class():
                self.start()
        except Exception as e:
            # no systemd user bus (another desktop, no permission): the AI
            # tools find ComfyUI missing; GIMPhoto starts anyway
            publish({"state": "missing", "error": str(e)})
        finally:
            # always: GIMP waits for it, and quit must reach do_quit
            procedure.persistent_ready()
        self.persistent_enable()
        while True:
            self.persistent_process(0)

    def start(self):
        connection = bus()
        path = call(
            connection, cs.SYSTEMD_PATH, cs.MANAGER_INTERFACE, "LoadUnit", GLib.Variant("(s)", (cs.SERVICE,)), "(o)"
        )[0]
        load = unit_property(connection, path, cs.UNIT_INTERFACE, "LoadState")
        active = unit_property(connection, path, cs.UNIT_INTERFACE, "ActiveState")
        port = cs.DEFAULT_PORT
        if load == "loaded":
            port = cs.port_from_exec_start(unit_property(connection, path, cs.SERVICE_INTERFACE, "ExecStart"))
        if cs.should_start(load, active):
            call(
                connection,
                cs.SYSTEMD_PATH,
                cs.MANAGER_INTERFACE,
                "StartUnit",
                GLib.Variant("(ss)", (cs.SERVICE, "replace")),
                "(o)",
            )
            self.started = True
        publish(cs.describe(load, active, self.started, port))

    def do_quit(self):
        if not self.started:
            return
        # GIMP kills a quitting plug-in 10 ms after asking it to quit: send
        # StopUnit without waiting for systemd's answer
        message = Gio.DBusMessage.new_method_call(
            cs.SYSTEMD_BUS_NAME, cs.SYSTEMD_PATH, cs.MANAGER_INTERFACE, "StopUnit"
        )
        message.set_body(GLib.Variant("(ss)", (cs.SERVICE, "replace")))
        message.set_flags(Gio.DBusMessageFlags.NO_REPLY_EXPECTED)
        try:
            connection = bus()
            connection.send_message(message, Gio.DBusSendMessageFlags.NONE)
            connection.flush_sync(None)
        except GLib.Error:
            pass


Gimp.main(ComfyuiService.__gtype__, sys.argv)
