"""A search window over every chip minipro supports."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from .chips import search  # noqa: E402

# The T48 database holds some 28,000 names. A list that long is no use to read,
# so the window shows the best matches and says how many there are in all.
VISIBLE_LIMIT = 300


class ChipChooser(Adw.Window):
    """Type part of a name, pick a chip, and the callback receives it."""

    def __init__(
        self,
        parent: Gtk.Window,
        catalogue: tuple[str, ...],
        on_chosen: Callable[[str], None],
        initial_text: str = "",
    ) -> None:
        super().__init__(
            transient_for=parent,
            modal=True,
            title="Choose Chip",
            default_width=460,
            default_height=560,
        )
        self._catalogue = catalogue
        self._on_chosen = on_chosen

        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        self.set_content(view)
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for side in ("top", "bottom", "start", "end"):
            getattr(page, f"set_margin_{side}")(12)
        view.set_content(page)

        self.search_entry = Gtk.SearchEntry(
            placeholder_text="Part number, such as 27C256 or AT28C"
        )
        self.search_entry.connect("search-changed", self._search_changed)
        self.search_entry.connect("activate", self._choose_first)
        page.append(self.search_entry)

        self.names = Gtk.StringList()
        factory = Gtk.SignalListItemFactory()
        factory.connect(
            "setup",
            lambda _f, item: item.set_child(
                Gtk.Label(xalign=0, margin_start=8, margin_top=4, margin_bottom=4)
            ),
        )
        factory.connect(
            "bind",
            lambda _f, item: item.get_child().set_text(item.get_item().get_string()),
        )
        self._selection = Gtk.SingleSelection(model=self.names)
        chip_list = Gtk.ListView(
            model=self._selection, factory=factory, single_click_activate=True
        )
        chip_list.connect("activate", lambda _list, index: self.choose(index))
        scroller = Gtk.ScrolledWindow(vexpand=True, has_frame=True)
        scroller.set_child(chip_list)
        page.append(scroller)

        self._count = Gtk.Label(xalign=0)
        self._count.add_css_class("dim-label")
        page.append(self._count)

        self.search_entry.set_text(initial_text)
        self._search_changed(self.search_entry)

    def _search_changed(self, entry: Gtk.SearchEntry) -> None:
        text = entry.get_text()
        matches = search(self._catalogue, text, limit=len(self._catalogue))
        shown = matches[:VISIBLE_LIMIT]
        self.names.splice(0, self.names.get_n_items(), shown)
        if not self._catalogue:
            self._count.set_text("minipro listed no chips.")
        elif len(matches) > len(shown):
            self._count.set_text(
                f"Showing the first {len(shown):,} of {len(matches):,} matches. "
                "Type more of the name to narrow them."
            )
        else:
            self._count.set_text(f"{len(matches):,} matching chips")

    def _choose_first(self, _entry: Gtk.SearchEntry) -> None:
        if self.names.get_n_items():
            self.choose(0)

    def choose(self, index: int) -> None:
        name = self.names.get_string(index)
        self.close()
        self._on_chosen(name)
