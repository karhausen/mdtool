"""Modale Dialoge."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, OptionList
from textual.widgets.option_list import Option


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
