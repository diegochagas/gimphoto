# The local ComfyUI behind GIMPhoto's AI tools: found, started and stopped
# through its systemd user service (`comfyui`, installed by linux-mint-setup's
# steps/comfyui), over the session bus. GIMPhoto never installs it.
#
# The decisions are plain functions (no GIMP, no D-Bus) so the unit tests in
# tests/test_comfyui_service.py cover them; comfyui-service.py does the calls.

SERVICE = "comfyui.service"
DEFAULT_PORT = 8188

# systemd's names on the session bus
SYSTEMD_BUS_NAME = "org.freedesktop.systemd1"
SYSTEMD_PATH = "/org/freedesktop/systemd1"
MANAGER_INTERFACE = "org.freedesktop.systemd1.Manager"
UNIT_INTERFACE = "org.freedesktop.systemd1.Unit"
SERVICE_INTERFACE = "org.freedesktop.systemd1.Service"

# global parasite where the other plug-ins (the AI tools) read what was found
PARASITE = "gimphoto-comfyui"

# ActiveState values in which the service needs no start
RUNNING_STATES = ("active", "activating", "reloading")


def port_from_exec_start(exec_start):
    """The --port of the service's ExecStart (systemd's a(sasbttttuii): one
    (path, argv, ...) per command line), else ComfyUI's default."""
    for command in exec_start or ():
        argv = list(command[1]) if len(command) > 1 else []
        for i, arg in enumerate(argv):
            value = None
            if arg == "--port" and i + 1 < len(argv):
                value = argv[i + 1]
            elif arg.startswith("--port="):
                value = arg.split("=", 1)[1]
            if value is not None and value.isdigit():
                return int(value)
    return DEFAULT_PORT


def url_for(port):
    return f"http://127.0.0.1:{port}"


def should_start(load_state, active_state):
    """Start the service only when it exists and is not running already."""
    return load_state == "loaded" and active_state not in RUNNING_STATES


def describe(load_state, active_state, started, port):
    """What the AI tools need to know, stored in the PARASITE as JSON:
    state "missing" (not installed), "started" (by GIMPhoto, booting or up)
    or "running" (started by someone else, left running on quit)."""
    if load_state != "loaded":
        return {"state": "missing", "install": "linux-mint-setup's ComfyUI steps (steps/comfyui)"}
    return {"state": "started" if started else "running", "url": url_for(port), "active": active_state}
