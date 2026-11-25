"""Textual-Oberfläche."""

from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import unquote, urlsplit

from textual import events, on, work
from textual.app import App, ComposeResult, SuspendNotSupported
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    ContentSwitcher,
    DirectoryTree,
    Footer,
    Label,
    Markdown,
    TextArea,
    Tree,
)

from .dialogs import ChoiceDialog, FolderDialog, NameDialog
from .store import (
    ConflictError,
    Document,
    Store,
    StoreError,
    TrashError,
    is_markdown,
)
from .typing_aids import (
    as_code,
    frontmatter_as_code,
    in_code_block,
    next_list_prefix,
)

PREVIEW_LIMIT = 500_000  # Zeichen; größere Dateien würden die Vorschau blockieren


class FileTree(DirectoryTree):
    """Zeigt Ordner, Markdown-Dateien und auf Wunsch Verstecktes."""

    def __init__(self, store: Store, **kwargs) -> None:
        super().__init__(store.root, **kwargs)
        self.store = store

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        return [path for path in paths if self.store.visible(path)]

    async def reveal(self, path: Path) -> bool:
        """Lädt den Baum neu und setzt den Cursor auf den Pfad."""
        await self.reload()
        node = self.root
        try:
            parts = path.relative_to(self.store.root).parts
        except ValueError:
            return False
        current = self.store.root
        for index, part in enumerate(parts):
            current = current / part
            child = next(
                (c for c in node.children if c.data and c.data.path == current), None
            )
            if child is None:
                return False
            if index < len(parts) - 1 and not child.is_expanded:
                await self.reload_node(child)
            node = child
        # Zeilennummern entstehen erst beim Aufbau des Baums.
        self.call_after_refresh(self.move_cursor, node)
        return True


class Editor(TextArea):
    BINDINGS = [
        Binding("ctrl+s", "app.save", "Speichern", priority=True),
        Binding("escape", "app.finish_edit", "Fertig", priority=True),
    ]

    async def _on_key(self, event: events.Key) -> None:
        # Textual ruft danach von selbst TextArea._on_key auf, außer bei
        # prevent_default().
        if self.selection.is_empty and self._assist(event):
            event.stop()
            event.prevent_default()

    def _assist(self, event: events.Key) -> bool:
        row, column = self.cursor_location
        line = self.document.get_line(row)
        before, after = line[:column], line[column:]
        in_empty_pair = before.endswith("[") and after.startswith(" ]")
        char = event.character

        if event.key == "enter":
            return self._continue_list(row, column, line)
        if event.key == "backspace" and in_empty_pair:
            self._put("", column - 1, column + 2)
            return True
        if char == "[":
            # Cursor bleibt direkt hinter der Klammer.
            self._put("[ ]", column, column)
            self.move_cursor((row, column + 1))
            return True
        if in_empty_pair and char == "]":
            self.move_cursor((row, column + 2))
            return True
        if in_empty_pair and char == " ":
            self.move_cursor((row, column + 1))
            return True
        if in_empty_pair and char and event.is_printable:
            self._put(char, column, column + 1)  # ersetzt das Leerzeichen
            return True
        if char == "]" and after.startswith("]") and "[" in before:
            self.move_cursor((row, column + 1))
            return True
        return False

    def _put(self, text: str, start: int, end: int) -> None:
        row = self.cursor_location[0]
        self.replace(text, (row, start), (row, end), maintain_selection_offset=False)

    def _continue_list(self, row: int, column: int, line: str) -> bool:
        prefix = next_list_prefix(line, column)
        if prefix is None:
            return False
        if in_code_block([self.document.get_line(i) for i in range(row)]):
            return False
        if prefix:
            self._put("\n" + prefix, column, column)
        else:
            self._put("", 0, len(line))  # leerer Punkt: Liste beenden
        return True


class MdToolApp(App[None]):
    TITLE = "mdtool"
    ENABLE_COMMAND_PALETTE = False

    CSS = """
    #main { height: 1fr; }
    FileTree { width: 32%; min-width: 22; max-width: 50; border: round $primary; }
    FileTree:focus { border: round $accent; }
    #right { width: 1fr; border: round $primary; }
    #right:focus-within { border: round $accent; }
    #path { width: 1fr; height: 1; padding: 0 1; background: $panel; text-style: bold; }
    ContentSwitcher { height: 1fr; }
    Editor { border: none; height: 1fr; }
    Editor:focus { border: none; }
    ModalScreen { align: center middle; }
    .dialog {
        width: 70; max-width: 95%; height: auto; max-height: 90%;
        padding: 1 2; background: $surface; border: round $accent;
    }
    .dialog-title { width: 1fr; height: auto; margin-bottom: 1; }
    .dialog .hint { color: $text-muted; margin-top: 1; width: 1fr; }
    .dialog OptionList { height: auto; max-height: 14; }
    .buttons { height: auto; }
    .buttons Button { margin-right: 1; }
    """

    BINDINGS = [
        Binding("n", "new_file", "Neu"),
        Binding("o", "new_folder", "Ordner"),
        Binding("e", "edit", "Bearbeiten"),
        Binding("E", "external_edit", "Extern"),
        Binding("r", "rename", "Umbenennen"),
        Binding("m", "move", "Verschieben"),
        Binding("d", "delete", "Löschen"),
        Binding("full_stop", "toggle_hidden", "Versteckte", show=False),
        Binding("f5", "refresh", "Neu laden", show=False),
        Binding("q", "quit", "Ende"),
    ]

    def __init__(self, store: Store, start: Path | None = None) -> None:
        super().__init__()
        self.store = store
        self.start = start
        self.shown: Path | None = None  # Datei in der Vorschau
        self.editing: Path | None = None
        self.document: Document | None = None
        self.saved_text = ""

    # -- Aufbau --------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Horizontal(id="main"):
            yield FileTree(self.store, id="tree")
            with Vertical(id="right"):
                yield Label("", id="path", markup=False)
                with ContentSwitcher(initial="preview"):
                    with VerticalScroll(id="preview"):
                        yield Markdown(id="markdown", open_links=False)
                    yield Editor(
                        id="editor", tab_behavior="indent", show_line_numbers=True
                    )
        yield Footer(compact=True, show_command_palette=False)

    async def on_mount(self) -> None:
        self.tree_view.focus()
        if self.start is not None:
            await self.tree_view.reveal(self.start)

    @property
    def tree_view(self) -> FileTree:
        return self.query_one(FileTree)

    @property
    def editor(self) -> Editor:
        return self.query_one(Editor)

    @property
    def dirty(self) -> bool:
        return self.editing is not None and self.editor.text != self.saved_text

    def fail(self, error: Exception | str) -> None:
        self.notify(str(error), severity="error", markup=False)

    def info(self, message: str) -> None:
        self.notify(message, markup=False)

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        blocked = {
            "new_file",
            "new_folder",
            "edit",
            "external_edit",
            "rename",
            "move",
            "delete",
            "refresh",
            "toggle_hidden",
        }
        return not (action in blocked and self.editing is not None)

    # -- Auswahl und Vorschau --------------------------------------------------

    @property
    def selected(self) -> Path:
        node = self.tree_view.cursor_node
        return node.data.path if node and node.data else self.store.root

    @property
    def selected_folder(self) -> Path:
        path = self.selected
        return path if path.is_dir() else path.parent

    def selected_file(self) -> Path | None:
        path = self.selected
        if path.is_dir():
            self.info("Bitte zuerst eine Datei auswählen.")
            return None
        return path

    def selected_entry(self) -> Path | None:
        path = self.selected
        if path == self.store.root:
            self.info("Der Basisordner selbst kann nicht verändert werden.")
            return None
        return path

    @on(Tree.NodeHighlighted)
    def _highlighted(self, event: Tree.NodeHighlighted) -> None:
        if event.node.data is not None and self.editing is None:
            self.show_preview(event.node.data.path)

    @on(DirectoryTree.FileSelected)
    def _file_selected(self) -> None:
        self.query_one("#preview").focus()

    @work(exclusive=True, group="preview")
    async def show_preview(self, path: Path) -> None:
        # Kurze Pause, damit schnelles Blättern nicht jede Datei rendert.
        await asyncio.sleep(0.05)
        self.query_one("#path", Label).update(self.store.rel(path))
        self.shown = None
        if path.is_dir():
            text = "*Ordner. Mit* `n` *legst du hier eine neue Datei an, mit* `o` *einen Ordner.*"
        else:
            try:
                text = (await asyncio.to_thread(self.store.read, path)).text
                self.shown = path
                if not text.strip():
                    text = "*Leere Datei. Mit* `e` *bearbeiten.*"
                elif len(text) > PREVIEW_LIMIT:
                    text = "*Zu groß für die Vorschau. Mit* `e` *bearbeiten.*"
                elif is_markdown(path):
                    text = frontmatter_as_code(text)
                else:
                    text = as_code(text, path.suffix.lstrip("."))
            except StoreError as error:
                text = f"**Fehler:** {error}"
        await self.query_one("#markdown", Markdown).update(text)
        self.query_one("#preview").scroll_home(animate=False)

    @on(Markdown.LinkClicked)
    async def _link(self, event: Markdown.LinkClicked) -> None:
        href = event.href
        try:
            parts = urlsplit(href)
        except ValueError:
            return
        if parts.scheme in ("http", "https"):
            self.open_url(href)
            return
        if parts.scheme or parts.netloc:
            self.info(f"Link wird nicht unterstützt: {href}")
            return
        if not parts.path:
            event.markdown.goto_anchor(unquote(parts.fragment))
            return
        if self.shown is None:
            return
        target = Path(os.path.normpath(self.shown.parent / unquote(parts.path)))
        if not self.store.visible(target) or not await self.tree_view.reveal(target):
            self.info(f"Link-Ziel nicht gefunden: {href}")

    # -- Bearbeiten ------------------------------------------------------------

    def action_edit(self) -> None:
        path = self.selected_file()
        if path is None:
            return
        try:
            document = self.store.read(path)
        except StoreError as error:
            self.fail(error)
            return
        self.workers.cancel_group(self, "preview")
        self.editor.load_text(document.text)
        # Der Editor kann seltene Sonderzeichen (z. B. Seitenvorschub) beim Laden
        # in Zeilenumbrüche wandeln; verglichen wird daher mit seinem Stand.
        self.saved_text = self.editor.text
        if self.saved_text != document.text:
            self.notify(
                "Die Datei enthält besondere Zeilentrenner. Beim Speichern werden "
                "sie zu normalen Zeilenumbrüchen.",
                severity="warning",
            )
        self.document = document
        self.editing = path
        self.tree_view.disabled = True
        self.query_one(ContentSwitcher).current = "editor"
        self.editor.focus()
        self._update_path()
        self.refresh_bindings()

    @on(TextArea.Changed)
    def _update_path(self) -> None:
        if self.editing is not None:
            mark = " ● ungespeichert" if self.dirty else ""
            self.query_one("#path", Label).update(
                f"✎ {self.store.rel(self.editing)}{mark}"
            )

    async def _save(self) -> bool:
        """Speichert; bei einem Konflikt wird nachgefragt."""
        if self.editing is None or self.document is None:
            return True
        text = self.editor.text
        if text == self.saved_text:
            return True
        try:
            try:
                document = self.store.write(self.editing, text, self.document)
            except ConflictError as error:
                choice = await self.push_screen_wait(
                    ChoiceDialog(
                        f"{error}\nMit deinem Stand überschreiben?",
                        [("cancel", "Abbrechen"), ("force", "Überschreiben")],
                        danger="force",
                    )
                )
                if choice != "force":
                    return False
                document = self.store.write(
                    self.editing, text, self.document, force=True
                )
        except StoreError as error:
            self.fail(error)
            return False
        self.document = document
        self.saved_text = text
        self._update_path()
        self.info("Gespeichert.")
        return True

    async def _resolve_changes(self) -> bool:
        """Fragt bei ungespeicherten Änderungen nach; False bedeutet Abbruch."""
        if not self.dirty:
            return True
        choice = await self.push_screen_wait(
            ChoiceDialog(
                "Es gibt ungespeicherte Änderungen.",
                [
                    ("save", "Speichern"),
                    ("discard", "Verwerfen"),
                    ("cancel", "Abbrechen"),
                ],
                danger="discard",
            )
        )
        if choice == "save":
            return await self._save()
        return choice == "discard"

    @work(exclusive=True, group="action")
    async def action_save(self) -> None:
        await self._save()

    @work(exclusive=True, group="action")
    async def action_finish_edit(self) -> None:
        if self.editing is None or not await self._resolve_changes():
            return
        path = self.editing
        self.editing = None
        self.document = None
        self.query_one(ContentSwitcher).current = "preview"
        self.tree_view.disabled = False
        self.tree_view.focus()
        self.refresh_bindings()
        await self._show(path)

    def action_external_edit(self) -> None:
        path = self.selected_file()
        if path is None:
            return
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "nano"
        try:
            command = [*shlex.split(editor), str(path)]
            with self.suspend():
                subprocess.run(command, check=False)
        except SuspendNotSupported:
            self.fail("Dieses Terminal unterstützt keinen externen Editor.")
        except (OSError, ValueError) as error:
            self.fail(f"Editor „{editor}“ konnte nicht gestartet werden: {error}")
        self.show_preview(path)

    # -- Dateien und Ordner ----------------------------------------------------

    async def _show(self, path: Path) -> None:
        await self.tree_view.reveal(path)
        self.show_preview(path)

    @work(exclusive=True, group="action")
    async def action_new_file(self) -> None:
        folder = self.selected_folder
        name = await self.push_screen_wait(
            NameDialog(f"Neue Datei in {self.store.rel(folder)}")
        )
        if name is None:
            return
        try:
            path = self.store.create_file(folder, name)
        except StoreError as error:
            self.fail(error)
            return
        await self._show(path)
        self.info(f"Angelegt: {self.store.rel(path)}")

    @work(exclusive=True, group="action")
    async def action_new_folder(self) -> None:
        folder = self.selected_folder
        name = await self.push_screen_wait(
            NameDialog(f"Neuer Ordner in {self.store.rel(folder)}")
        )
        if name is None:
            return
        try:
            path = self.store.create_folder(folder, name)
        except StoreError as error:
            self.fail(error)
            return
        await self._show(path)
        self.info(f"Angelegt: {self.store.rel(path)}")

    @work(exclusive=True, group="action")
    async def action_rename(self) -> None:
        path = self.selected_entry()
        if path is None:
            return
        name = await self.push_screen_wait(
            NameDialog(f"{self.store.rel(path)} umbenennen", path.name)
        )
        if name is None:
            return
        try:
            target = self.store.rename(path, name)
        except StoreError as error:
            self.fail(error)
            return
        await self._show(target)

    @work(exclusive=True, group="action")
    async def action_move(self) -> None:
        path = self.selected_entry()
        if path is None:
            return
        folders, truncated = await asyncio.to_thread(self.store.folders)
        # Der Ordner selbst, seine Unterordner und der jetzige Ort scheiden aus.
        folders = [
            f for f in folders if f != path.parent and not f.is_relative_to(path)
        ]
        if truncated:
            self.info("Sehr viele Ordner: Die Liste ist unvollständig.")
        if not folders:
            self.info("Es gibt keinen anderen Ordner.")
            return
        index = await self.push_screen_wait(
            FolderDialog(
                f"{self.store.rel(path)} verschieben nach …",
                [
                    ". (Basisordner)" if f == self.store.root else self.store.rel(f)
                    for f in folders
                ],
            )
        )
        if index is None:
            return
        try:
            target = self.store.move(path, folders[index])
        except StoreError as error:
            self.fail(error)
            return
        await self._show(target)
        self.info(f"Verschoben: {self.store.rel(target)}")

    @work(exclusive=True, group="action")
    async def action_delete(self) -> None:
        path = self.selected_entry()
        if path is None:
            return
        name = self.store.rel(path)
        if path.is_symlink():
            question = f"Link {name} entfernen? Das Ziel bleibt erhalten."
            label = "Link entfernen"
        else:
            question = f"{name} in den Papierkorb verschieben?"
            label = "In den Papierkorb"
            if path.is_dir():
                total, hidden = await asyncio.to_thread(self.store.count_contents, path)
                question += f"\nDer Ordner enthält {total} Einträge"
                question += f", davon {hidden} hier nicht sichtbare." if hidden else "."
        choice = await self.push_screen_wait(
            ChoiceDialog(
                question, [("cancel", "Abbrechen"), ("trash", label)], danger="trash"
            )
        )
        if choice != "trash":
            return
        try:
            try:
                self.store.trash(path)
            except TrashError as error:
                choice = await self.push_screen_wait(
                    ChoiceDialog(
                        f"{error}\n\n{name} stattdessen ENDGÜLTIG löschen?",
                        [("cancel", "Abbrechen"), ("delete", "Endgültig löschen")],
                        danger="delete",
                    )
                )
                if choice != "delete":
                    return
                self.store.delete(path)
        except StoreError as error:
            self.fail(error)
            return
        await self._show(path.parent)
        self.info(f"Gelöscht: {name}")

    @work(exclusive=True, group="action")
    async def action_refresh(self) -> None:
        path = self.selected
        await self._show(path if path.exists() else self.store.root)

    @work(exclusive=True, group="action")
    async def action_toggle_hidden(self) -> None:
        path = self.selected
        self.store.show_hidden = not self.store.show_hidden
        state = "eingeblendet" if self.store.show_hidden else "ausgeblendet"
        await self._show(path if self.store.listed(path) else self.store.root)
        self.info(f"Versteckte Dateien {state}.")

    async def action_quit(self) -> None:
        # Bei offenem Dialog wird erst dieser beantwortet.
        if self.dirty and len(self.screen_stack) > 1:
            return
        self._quit()

    @work(exclusive=True, group="action")
    async def _quit(self) -> None:
        if await self._resolve_changes():
            self.exit()
