"""Hilfe-Fenster mit allen Tasten."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Label, Markdown

from . import __version__

HELP = """\
## Dateibaum

- `↑ ↓`: Auswahl bewegen, rechts erscheint die Vorschau
- `Enter`: Ordner auf-/zuklappen, bei Dateien in die Vorschau wechseln
- `Tab`: zwischen Baum und Vorschau wechseln
- `/`: suchen in Dateinamen und Text, filtern mit feld:wert
- `n`: neue Markdown-Datei im ausgewählten Ordner
- `o`: neuer Ordner (mit .policy.yaml)
- `e`: Datei bearbeiten
- `E`: Datei im externen Editor öffnen ($VISUAL, $EDITOR, sonst nano)
- `f`: Frontmatter einfügen, falls die Markdown-Datei keines hat
- `s`: Status setzen (active, waiting, done, archived)
- `p`: Priorität setzen (low, normal, high)
- `r`: umbenennen
- `m`: verschieben
- `d`: löschen (in den Papierkorb)
- `g`: Git: alles committen, holen und hochladen
- `.`: versteckte Dateien ein-/ausblenden
- `F5`: Baum neu einlesen
- `h`, `?`, `F1`: diese Hilfe
- `q`, `Strg+Q`: beenden

## Editor

- `Strg+S`: speichern, setzt updated: im Frontmatter auf heute
- `Esc`: Editor schließen, fragt bei ungespeicherten Änderungen
- `Strg+Z` / `Strg+Y`: rückgängig / wiederholen
- `Enter`: führt Listen und Checkboxen fort, im leeren Punkt endet die Liste
- `[`: wird zu [ ], das nächste Zeichen ersetzt das Leerzeichen
- `Strg+T`: Checkbox ab-/aufhaken, macht aus der Zeile sonst eine Checkbox
- `F1`: diese Hilfe

## Suche und Dialoge

- `↑ ↓`: Treffer oder Ordner wählen, auch während des Tippens
- `Enter`: übernehmen bzw. Treffer öffnen
- `Esc`: abbrechen
- `← →`: zwischen den Schaltflächen wechseln

Filter in der Suche: `status:active`, `priority:high`, `tag:projekt`.
Mehrere Bedingungen müssen alle passen, `owner:` findet leere Felder.

## Vorlagen

`mdtool --vorlagen` kopiert die Vorlagen nach `~/.config/mdtool/templates/`.
Dort angepasste Vorlagen gelten für neue Dateien, neue Ordner und für `f`.
"""


class HelpDialog(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Schließen"),
        Binding("q", "dismiss(None)", show=False),
        Binding("h", "dismiss(None)", show=False),
        Binding("question_mark", "dismiss(None)", show=False),
        Binding("f1", "dismiss(None)", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog help"):
            yield Label(f"mdtool {__version__}: Tasten", classes="dialog-title")
            with VerticalScroll():
                yield Markdown(HELP, open_links=False)
            yield Label(
                "↑↓ blättern · Esc, h oder q: schließen", classes="hint", markup=False
            )

    def on_mount(self) -> None:
        self.query_one(VerticalScroll).focus()
