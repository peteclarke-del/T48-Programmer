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
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# The simulator, with chips of its own that are thrown away afterwards.
STATE = tempfile.TemporaryDirectory(prefix="t48-shots-")
os.environ["T48_PROGRAMMER_DEMO"] = "1"
os.environ["T48_PROGRAMMER_SIMULATOR_DELAY"] = "0"
os.environ["T48_PROGRAMMER_SIMULATOR_STATE"] = STATE.name

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


@dataclass(frozen=True)
class Shot:
    """One picture: the state to put the window in, and which window to draw.

    draws names an attribute of the main window that holds another window, for
    a picture of a dialog. unplugged takes the programmer away first.
    """

    name: str
    state: str
    draws: str = ""
    unplugged: bool = False


SHOTS = (
    Shot("01-start", "main"),
    Shot("02-guide", "guide"),
    Shot("03-result", "result"),
    Shot("05-help", "help"),
    Shot("06-offline", "main", unplugged=True),
    Shot("07-guide-burn", "guide-burn"),
    Shot("08-guide-banks", "guide-banks"),
    Shot("09-update", "app-update", draws="about_window"),
    Shot("10-guide-images", "guide-images"),
    Shot("11-fill-the-chip", "short-write", draws="last_dialog"),
)


def prepare(window: Gtk.Window, shot: Shot) -> Gtk.Window | None:
    """Put the window in the state for a shot. Returns a dialog to draw, if any."""
    os.environ["T48_PROGRAMMER_SIMULATOR_ABSENT"] = "1" if shot.unplugged else "0"
    window.set_default_size(WIDTH, HEIGHT)
    window.show_documentation_state(shot.state)
    return getattr(window, shot.draws) if shot.draws else None


def open_chooser(window: Gtk.Window) -> Gtk.Window:
    """The one picture that is not a state of the main window."""
    chooser = ChipChooser(window, load_catalogue("t48"), lambda _name: None)
    chooser.search_entry.set_text("27C")
    chooser.present()
    return chooser


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    application = ProgrammerApplication(
        "com.github.pclarke.T48Programmer.Screenshots", unique=False
    )
    steps = [
        (shot.name, lambda window, shot=shot: prepare(window, shot)) for shot in SHOTS
    ]
    steps.append(("04-choose-chip", open_chooser))

    def activate(_application: ProgrammerApplication) -> None:
        window = application.get_active_window()
        window.set_default_size(WIDTH, HEIGHT)
        pending = list(steps)
        extra: list[Gtk.Window] = []

        def capture(name: str, target: Gtk.Window, tries: int = 10) -> bool:
            # A dialog that opens as another window closes can take a few
            # frames to be drawn. Wait for it, within reason, and then fail.
            try:
                render(target, name)
            except RuntimeError:
                if tries == 0:
                    raise
                GLib.timeout_add(SETTLE_MILLISECONDS, capture, name, target, tries - 1)
                return GLib.SOURCE_REMOVE
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
    try:
        return application.run([])
    finally:
        STATE.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
