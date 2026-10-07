# ComfyUI with GIMPhoto (AI backend)

**Issue:** [#37](https://github.com/diegochagas/gimphoto/issues/37) ·
**Plug-in:** [`plugins/comfyui-service/`](../../plugins/comfyui-service/)

GIMPhoto's AI tools (Generative Fill, Remove tool, Select Subject, Object
Selection, Remove Background, Photo Restoration) run on a **local
[ComfyUI](https://github.com/comfyanonymous/ComfyUI)**: open-weight image
models on this machine, with no accounts or uploads. ComfyUI holds GPU
memory and many GB of RAM while it runs, so it should run only while
GIMPhoto is open.

GIMPhoto **does not install ComfyUI**.
[linux-mint-setup's ComfyUI steps](https://github.com/diegochagas/linux-mint-setup#local-ai-image-models-comfyui)
install it, with its models, as the `comfyui` systemd user service (not
started at boot). GIMPhoto starts and stops that service:

| | Plain GIMP | GIMPhoto |
|---|---|---|
| GIMPhoto opens | ComfyUI stays stopped; the AI tools fail until it is started by hand | ComfyUI is started, if it is not running |
| GIMPhoto closes | ComfyUI keeps the GPU and RAM until it is stopped by hand | ComfyUI is stopped, if GIMPhoto started it |
| ComfyUI started by hand, a script or GIMP's launcher | — | left running when GIMPhoto closes |
| No `comfyui` service | — | GIMPhoto starts alone, and records ComfyUI as missing (with where to install it) for the AI tools |

In use (the `comfyui` service of linux-mint-setup, on a test machine):

```text
$ systemctl --user is-active comfyui
inactive
  (open GIMPhoto)
$ systemctl --user is-active comfyui
active
  (close GIMPhoto)
$ systemctl --user is-active comfyui
inactive
```

Nothing to set up: when the service is there, it is used. Its address
comes from the service (`--port` of its command, 8188 by default).

## How it works

- **Plug-in** `plugins/comfyui-service/`: a persistent procedure without
  arguments (`gimphoto-comfyui-service`), which GIMP runs once at startup
  and which stays until GIMP quits.
  - At startup it looks up `comfyui.service` on the user's systemd. If the
    service exists and is not running, it starts it (`StartUnit`). Batch
    runs without a user interface leave it alone.
  - It stores what it found in the global parasite `gimphoto-comfyui`,
    which the AI tools read: `missing`, `started` or `running`, and the
    address.
  - When GIMP quits it stops the service (`StopUnit`), only if it started
    it. GIMP gives a quitting plug-in 10 ms, so the request is sent
    without waiting for systemd's answer.
- **Sandbox:** a Flatpak cannot run `systemctl` on the host. The plug-in
  talks to systemd over the session bus, which needs one permission added
  by the manifest generator: `--talk-name=org.freedesktop.systemd1`.
  Nothing else is opened: no `flatpak-spawn --host`.
- The decisions (when to start, which port, what to tell the tools) are
  plain functions in `comfyui_service.py`.
- **Tests:** unit tests for those functions in
  `tests/test_comfyui_service.py`. The generator's tests pin the one extra
  permission. `scripts/smoke` checks that:
  - the procedure is registered;
  - the installed app has the permission;
  - the batch runs did not start or stop ComfyUI. It counts the service's
    starts and stops in systemd's journal, because a batch run that started
    it would also stop it on quit.

## Limits

- If GIMPhoto crashes, or is killed, ComfyUI keeps running: stop it with
  `systemctl --user stop comfyui`.
- A GIMP and a GIMPhoto open together share one ComfyUI. Whichever started
  it stops it when it closes, even if the other is still open.
- The AI tools that use it come with their own issues: [Select Subject](select-subject.md)
  is the first; #30–#34 follow.
- The service name is fixed (`comfyui`), as linux-mint-setup installs it.
- `GIMPHOTO_COMFYUI=off` in GIMPhoto's environment (`flatpak run
  --env=GIMPHOTO_COMFYUI=off …`) leaves ComfyUI alone even with a user
  interface, as `scripts/smoke` does for its GUI runs.
