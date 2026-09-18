"""Native GTK view for the bundled user and technical guide."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk  # noqa: E402

from .help_content import HELP_TOPICS, HelpTopic  # noqa: E402


def _text(label: str, *css_classes: str, **properties: object) -> Gtk.Label:
    widget = Gtk.Label(label=label, xalign=0, wrap=True, **properties)
    for css_class in css_classes:
        widget.add_css_class(css_class)
    return widget


class HelpView(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.set_vexpand(True)
        self._topic_list = Gtk.ListBox(
            selection_mode=Gtk.SelectionMode.SINGLE,
            activate_on_single_click=True,
            width_request=240,
        )
        self._topic_list.add_css_class("navigation-sidebar")
        self._topic_list.connect("row-selected", self._topic_selected)
        for topic in HELP_TOPICS:
            row = Gtk.ListBoxRow()
            label = _text(topic.title)
            for side in ("top", "bottom"):
                getattr(label, f"set_margin_{side}")(10)
            for side in ("start", "end"):
                getattr(label, f"set_margin_{side}")(12)
            row.set_child(label)
            self._topic_list.append(row)
        navigation = Gtk.ScrolledWindow(width_request=240)
        navigation.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        navigation.set_child(self._topic_list)
        self.append(navigation)
        self.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        self._article = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=16,
            margin_top=24,
            margin_bottom=32,
            margin_start=32,
            margin_end=32,
        )
        article_scroller = Gtk.ScrolledWindow(hexpand=True)
        article_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        article_scroller.set_child(self._article)
        self.append(article_scroller)
        self._topic_list.select_row(self._topic_list.get_row_at_index(0))

    def _topic_selected(self, _list: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        if row is not None:
            self._show_topic(HELP_TOPICS[row.get_index()])

    def _show_topic(self, topic: HelpTopic) -> None:
        while child := self._article.get_first_child():
            self._article.remove(child)
        self._article.append(_text(topic.title, "title-1"))
        self._article.append(_text(topic.summary, "dim-label"))
        for section in topic.sections:
            self._article.append(_text(section.heading, "title-3", margin_top=8))
            for paragraph in section.paragraphs:
                self._article.append(
                    _text(paragraph, selectable=True, max_width_chars=88)
                )
            for number, step in enumerate(section.steps, start=1):
                line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                marker = _text(str(number), "heading", valign=Gtk.Align.START)
                marker.set_size_request(24, -1)
                line.append(marker)
                line.append(_text(step, hexpand=True, max_width_chars=82))
                self._article.append(line)
