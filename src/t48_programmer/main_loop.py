"""Handing a result from a worker thread to the GTK thread."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib  # noqa: E402


def call_on_main_loop(function: Callable[..., Any], *arguments: Any) -> None:
    """Call ``function(*arguments)`` once on the GTK main loop.

    GLib.idle_add is the usual way, but its default priority is the lowest in
    the main loop, below redrawing. On a display with no frame pacing, such as
    Xvfb or a slow remote session, an animated spinner keeps the loop busy with
    redraws for ever, and an idle callback never runs. The window then sits on
    "Looking for the programmer" with the answer waiting behind it. Results are
    not idle work, so they are queued at the default priority.
    """

    def call() -> bool:
        function(*arguments)
        return GLib.SOURCE_REMOVE

    GLib.idle_add(call, priority=GLib.PRIORITY_DEFAULT)
