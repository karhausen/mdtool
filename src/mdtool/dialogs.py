"""Modale Dialoge."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from itertools import islice

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, OptionList
from textual.widgets.option_list import Option
from textual.worker import get_current_worker


class NameDialog(ModalScreen[str | None]):
    """Fragt einen Namen ab; None bedeutet Abbruch."""

    BINDINGS = [Binding("escape", "dismiss(None)", "Abbrechen")]

    def __init__(self, title: str, value: str = "") -> None:
        super().__init__()
        self._title_text = title
        self._value = value

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self._title_text, classes="dialog-title", markup=False)
            yield Input(value=self._value, select_on_focus=False)
            yield Label("Enter: übernehmen · Esc: abbrechen", classes="hint")

    @on(Input.Submitted)
    def _submit(self, event: Input.Submitted) -> None:
        event.stop()
        self.dismiss(event.value)


class ChoiceDialog(ModalScreen[str | None]):
    """Stellt eine Frage; die erste Antwort ist vorausgewählt."""

    BINDINGS = [
        Binding("escape", "dismiss(None)", "Abbrechen"),
        Binding("left", "app.focus_previous", show=False),
        Binding("right", "app.focus_next", show=False),
    ]

    def __init__(
        self, title: str, choices: list[tuple[str, str]], danger: str | None = None
    ) -> None:
        super().__init__()
        self._title_text = title
        self._choices = choices
        self._danger = danger

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self._title_text, classes="dialog-title", markup=False)
            with Horizontal(classes="buttons"):
                for key, label in self._choices:
                    variant = "error" if key == self._danger else "default"
                    yield Button(label, id=key, variant=variant)

    @on(Button.Pressed)
    def _choose(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(event.button.id)


class FolderDialog(ModalScreen[int | None]):
    """Wählt einen Ordner aus einer Liste; liefert dessen Index."""

    BINDINGS = [Binding("escape", "dismiss(None)", "Abbrechen")]

    def __init__(self, title: str, folders: list[str]) -> None:
        super().__init__()
        self._title_text = title
        self._folders = folders
        self._shown: list[int] = []

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self._title_text, classes="dialog-title", markup=False)
            yield Input(placeholder="Ordner filtern …")
            yield OptionList(markup=False)
            yield Label(
                "Tippen: filtern · ↑↓: wählen · Enter: übernehmen · Esc: abbrechen",
                classes="hint",
            )

    def on_mount(self) -> None:
        self._fill("")

    def _fill(self, query: str) -> None:
        query = query.casefold()
        options = self.query_one(OptionList)
        self._shown = [
            i for i, name in enumerate(self._folders) if query in name.casefold()
        ]
        options.clear_options()
        options.add_options(Option(self._folders[i]) for i in self._shown)
        if self._shown:
            options.highlighted = 0

    def on_key(self, event) -> None:
        # Pfeiltasten steuern die Liste, auch während im Filter getippt wird.
        if event.key in ("up", "down") and isinstance(self.focused, Input):
            options = self.query_one(OptionList)
            if event.key == "up":
                options.action_cursor_up()
            else:
                options.action_cursor_down()
            event.stop()

    @on(Input.Changed)
    def _filter(self, event: Input.Changed) -> None:
        self._fill(event.value)

    @on(Input.Submitted)
    def _submit(self, event: Input.Submitted) -> None:
        event.stop()
        index = self.query_one(OptionList).highlighted
        if index is not None and index < len(self._shown):
            self.dismiss(self._shown[index])

    @on(OptionList.OptionSelected)
    def _selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.dismiss(self._shown[event.option_index])


class SearchDialog(ModalScreen):
    """Suche mit Trefferliste; liefert den gewählten Treffer."""

    MAX_HITS = 300
    BINDINGS = [Binding("escape", "dismiss(None)", "Abbrechen")]

    def __init__(
        self,
        search: Callable[[str, Callable[[], bool]], Iterator],
        label: Callable[[object], str],
        query: str = "",
    ) -> None:
        super().__init__()
        self._search = search
        self._label = label
        self._query = query
        self._hits: list = []

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog search"):
            yield Label("Suchen in Dateinamen und Text", classes="dialog-title")
            yield Input(value=self._query, placeholder="mindestens 2 Zeichen …")
            yield Label("", id="status", classes="hint", markup=False)
            yield OptionList(markup=False)
            yield Label(
                "↑↓: wählen · Enter: öffnen · Esc: abbrechen", classes="hint"
            )

    def on_mount(self) -> None:
        self._start(self._query)

    def on_key(self, event) -> None:
        if event.key in ("up", "down", "pageup", "pagedown") and isinstance(
            self.focused, Input
        ):
            options = self.query_one(OptionList)
            action = {
                "up": options.action_cursor_up,
                "down": options.action_cursor_down,
                "pageup": options.action_page_up,
                "pagedown": options.action_page_down,
            }[event.key]
            action()
            event.stop()

    @on(Input.Changed)
    def _changed(self, event: Input.Changed) -> None:
        self._start(event.value)

    def _start(self, query: str) -> None:
        self._query = query
        if len(query.strip()) < 2:
            self.workers.cancel_group(self, "search")
            self._show([], "")
            return
        self.query_one("#status", Label).update("Suche läuft …")
        self._run(query)

    @work(thread=True, exclusive=True, group="search")
    def _run(self, query: str) -> None:
        worker = get_current_worker()
        time.sleep(0.15)  # erst suchen, wenn das Tippen kurz pausiert
        if worker.is_cancelled:
            return
        hits = list(
            islice(self._search(query, lambda: worker.is_cancelled), self.MAX_HITS + 1)
        )
        if worker.is_cancelled:
            return
        more = len(hits) > self.MAX_HITS
        hits = hits[: self.MAX_HITS]
        if not hits:
            status = "Keine Treffer."
        else:
            status = f"{len(hits)}{'+' if more else ''} Treffer"
        self.app.call_from_thread(self._show, hits, status)

    def _show(self, hits: list, status: str) -> None:
        if not self.is_attached:  # Dialog wurde inzwischen geschlossen
            return
        self._hits = hits
        self.query_one("#status", Label).update(status)
        options = self.query_one(OptionList)
        options.clear_options()
        options.add_options(Option(self._label(hit)) for hit in hits)
        if hits:
            options.highlighted = 0

    @on(Input.Submitted)
    def _submit(self, event: Input.Submitted) -> None:
        event.stop()
        index = self.query_one(OptionList).highlighted
        if index is not None and index < len(self._hits):
            self.dismiss((self._query, self._hits[index]))

    @on(OptionList.OptionSelected)
    def _selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.dismiss((self._query, self._hits[event.option_index]))
