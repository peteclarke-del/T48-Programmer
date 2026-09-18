"""Protection against GTK settings inherited from a Snap-packaged program.

A terminal inside a Snap, such as the one in a Snap build of VS Code, exports
paths to that Snap's private GTK and gdk-pixbuf modules. A system Python that
loads one of them pulls the Snap's C library into the process and dies with a
symbol lookup error as soon as GTK draws its first icon. The launcher clears
these variables, but the tests and the screenshot tool start Python directly,
so the package clears them as well, before anything imports GTK.
"""

from __future__ import annotations

import os

_TOOLKIT_VARIABLES = (
    "GTK_PATH",
    "GTK_EXE_PREFIX",
    "GTK_IM_MODULE_FILE",
    "GDK_PIXBUF_MODULE_FILE",
    "GDK_PIXBUF_MODULEDIR",
    "GIO_MODULE_DIR",
    "GSETTINGS_SCHEMA_DIR",
    "LOCPATH",
)


def scrub_snap_environment(environment: dict[str, str] | None = None) -> None:
    """Remove toolkit paths that point into a Snap. Other values are kept."""
    environment = os.environ if environment is None else environment
    for name in _TOOLKIT_VARIABLES:
        if "/snap/" in environment.get(name, ""):
            del environment[name]
    library_path = environment.get("LD_LIBRARY_PATH", "")
    if "/snap/" in library_path:
        kept = [part for part in library_path.split(":") if "/snap/" not in part]
        environment["LD_LIBRARY_PATH"] = ":".join(part for part in kept if part)
