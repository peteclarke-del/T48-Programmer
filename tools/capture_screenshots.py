#!/usr/bin/env python3
"""Render the documentation screenshots from the real window.

Not a test. It starts the application against the bundled simulator, walks it
to each screen, and draws the window through GTK's own renderer into
docs/images. Pictures taken by hand drift from the program as soon as anything
moves. These can be regenerated whenever it changes.

    python3 tools/capture_screenshots.py        # needs a display

Nothing depends on a compositor or a screenshot tool, and no window has to be
brought to the front.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

os.environ["T48_PROGRAMMER_DEMO"] = "1"
os.environ["T48_PROGRAMMER_SIMULATOR_DELAY"] = "0"
os.environ["T48_PROGRAMMER_SIMULATOR_STATE"] = tempfile.mkdtemp(prefix="t48-shots-")

# The package comes first: importing it clears a Snap's GTK paths.
from t48_programmer.application import ProgrammerApplication  # noqa: E402, I001

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk  # noqa: E402

from t48_programmer.chip_chooser import ChipChooser  # noqa: E402
from t48_programmer.chips import load_catalogue  # noqa: E402

OUT = ROOT / "docs" / "images"
WIDTH, HEIGHT = 820, 860
SETTLE_MILLISECONDS = 900


def render(window: Gtk.Window, name: str) -> None:
    width, height = window.get_width(), window.get_height()
    paintable = Gtk.WidgetPaintable.new(window)
    snapshot = Gtk.Snapshot()
    paintable.snapshot(snapshot, width, height)
    node = snapshot.to_node()
    if node is None:
        raise RuntimeError(f"{name}: the window has not been drawn yet.")
    window.get_renderer().render_texture(node, None).save_to_png(
        str(OUT / f"{name}.png")
    )
    print(f"docs/images/{name}.png")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    application = ProgrammerApplication(
        "com.github.pclarke.T48Programmer.Screenshots", unique=False
    )

    def open_chooser(window: Gtk.Window) -> Gtk.Window:
        chooser = ChipChooser(window, load_catalogue("t48"), lambda _name: None, "27C")
        chooser.present()
        return chooser

    def show_offline(window: Gtk.Window) -> None:
        os.environ["T48_PROGRAMMER_SIMULATOR_ABSENT"] = "1"
        window.set_default_size(WIDTH, HEIGHT)
        window.show_documentation_state("main")
        window.show_dashboard()

    def show_update(window: Gtk.Window) -> Gtk.Window:
        os.environ["T48_PROGRAMMER_SIMULATOR_ABSENT"] = "0"
        window.show_documentation_state("app-update")
        return window.about_window

    # Each step prepares a screen and returns the window to draw, or None for
    # the main window.
    steps = [
        ("01-start", lambda window: window.show_documentation_state("main")),
        ("02-guide", lambda window: window.show_documentation_state("guide")),
        ("07-guide-burn", lambda window: window.show_documentation_state("guide-burn")),
        (
            "08-guide-banks",
            lambda window: window.show_documentation_state("guide-banks"),
        ),
        ("03-result", lambda window: window.show_documentation_state("result")),
        ("04-choose-chip", open_chooser),
        ("05-help", lambda window: window.show_documentation_state("help")),
        ("06-offline", show_offline),
        ("09-update", show_update),
    ]

    def activate(_application: ProgrammerApplication) -> None:
        window = application.get_active_window()
        window.set_default_size(WIDTH, HEIGHT)
        pending = list(steps)
        extra: list[Gtk.Window] = []

        def capture(name: str, target: Gtk.Window) -> bool:
            render(target, name)
            for other in extra:
                other.close()
            extra.clear()
            return advance()

        def advance() -> bool:
            if not pending:
                application.quit()
                return GLib.SOURCE_REMOVE
            name, prepare = pending.pop(0)
            target = prepare(window)
            if target is not None:
                extra.append(target)
            GLib.timeout_add(SETTLE_MILLISECONDS, capture, name, target or window)
            return GLib.SOURCE_REMOVE

        GLib.timeout_add(SETTLE_MILLISECONDS, advance)

    application.connect_after("activate", activate)
    os.environ["T48_PROGRAMMER_DOCUMENTATION_STATE"] = "main"
    return application.run([])


if __name__ == "__main__":
    raise SystemExit(main())
