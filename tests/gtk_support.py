"""What every interface test shares: GTK loaded safely, one application, waiting.

Import this before anything from gi. It imports the package first, which clears
the GTK paths that a Snap-packaged terminal exports and that otherwise crash
GTK as soon as it draws.

The interface tests need PyGObject and a display. Without them this module
raises unittest.SkipTest, which skips the whole test module that imported it,
unless T48_PROGRAMMER_REQUIRE_GTK is set, as the CI interface job sets it, so
that a broken GTK install fails the run instead of skipping the tests without
anyone noticing.
"""

from __future__ import annotations

import os
import time
import unittest
from collections.abc import Callable

REQUIRE_GTK = bool(os.environ.get("T48_PROGRAMMER_REQUIRE_GTK"))

try:
    from t48_programmer.application import ProgrammerApplication  # isort: skip
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gdk, GLib, Gtk
except (ImportError, ValueError) as error:
    if REQUIRE_GTK:
        raise
    raise unittest.SkipTest(f"PyGObject is not installed: {error}") from error

HAVE_DISPLAY = bool(Gtk.init_check()) and Gdk.Display.get_default() is not None
if REQUIRE_GTK and not HAVE_DISPLAY:
    raise RuntimeError("The interface tests need a display.")

# Every wait in the interface tests is bounded by this.
TIMEOUT = 15.0

_application: ProgrammerApplication | None = None


def shared_application() -> ProgrammerApplication:
    """One application for the whole run. D-Bus lets a process register one."""
    global _application
    if _application is None:
        _application = ProgrammerApplication(
            f"com.github.pclarke.T48Programmer.Test{os.getpid()}", unique=False
        )
        _application.register(None)
    return _application


def pump(condition: Callable[[], bool] | None = None, timeout: float = TIMEOUT) -> bool:
    """Run the main loop until condition() holds, and say whether it did.

    With no condition, deliver what is already pending and return.
    """
    context = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while True:
        while context.pending():
            context.iteration(False)
        if condition is None or condition():
            return True
        if time.monotonic() > deadline:
            return False
        time.sleep(0.005)


def wait_until(
    condition: Callable[[], bool], what: str, timeout: float = TIMEOUT
) -> None:
    if not pump(condition, timeout):
        raise AssertionError(f"Timed out waiting: {what}")
