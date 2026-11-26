# mdtool

Markdown-Dateien und Ordner im Terminal lesen, anlegen, ändern, verschieben
und löschen. Für Debian und WSL, benötigt Python 3.10 oder neuer.

## Installation

```bash
sudo apt install pipx
pipx ensurepath          # danach ein neues Terminal öffnen
pipx install ./mdtool    # im Ordner oberhalb des Projekts ausführen
```

Aktualisieren nach Änderungen am Code: `pipx install --force ./mdtool`.

## Start

```bash
mdtool                   # aktueller Ordner
mdtool ~/notizen         # bestimmter Ordner
mdtool ~/notizen/todo.md # Datei direkt anzeigen
```

## Tasten

| Taste | Funktion |
|---|---|
| `↑` `↓` | Auswahl bewegen, rechts erscheint die Vorschau |
| `Enter` | Ordner auf-/zuklappen, bei Dateien in die Vorschau wechseln |
| `Tab` | zwischen Baum und Vorschau wechseln |
| `/` | suchen in Dateinamen und Text; `Enter` öffnet den Treffer im Editor |
| `n` / `o` | neue Datei / neuer Ordner im ausgewählten Ordner |
| `e` | bearbeiten (`Strg+S` speichert, `Esc` beendet) |
| `E` | im externen Editor öffnen (`$VISUAL`, `$EDITOR`, sonst `nano`) |
| `r` / `m` / `d` | umbenennen / verschieben / löschen |
| `.` | versteckte Dateien ein-/ausblenden |
| `F5` | neu einlesen |
| `q`, `Strg+Q` | beenden |

## Schreibhilfen im Editor

- `Enter` führt Aufzählungen, nummerierte Listen und Checkboxen fort. In einem
  leeren Punkt beendet `Enter` die Liste. In Codeblöcken passiert nichts davon.
- `[` wird zu `[ ]`, der Cursor steht direkt hinter der Klammer. Das nächste
  Zeichen ersetzt das Leerzeichen, `Leertaste` und `]` springen weiter.
- Beim Speichern einer geänderten Datei wird `updated:` im Frontmatter auf das
  heutige Datum gesetzt, falls das Feld vorhanden ist. Das gilt nicht für den
  externen Editor.

## Vorlagen

Neue Markdown-Dateien beginnen mit Frontmatter, neue Ordner erhalten eine
`.pandora.yaml`. Eigene Vorlagen gehören nach `~/.config/mdtool/templates/`:

```bash
mdtool --vorlagen        # kopiert die Standardvorlagen dorthin
```

Vorhandene Dateien werden dabei nicht überschrieben. Danach `datei.md` und
`ordner.yaml` dort anpassen. In `datei.md` werden `{{title}}` und `{{date}}`
ersetzt. Fehlt eine Datei dort, gilt die mitgelieferte Vorlage aus
`src/mdtool/templates/`.

## Gut zu wissen

- Das Tool arbeitet nur im Basisordner. Symlinks nach außen werden ausgeblendet.
- Angezeigt werden Ordner, Dateien mit `.md` oder `.markdown` sowie versteckte
  Dateien und Ordner (außer `.git`). Beim Anlegen wird `.md` ergänzt, außer der
  Name beginnt mit einem Punkt.
- Die Suche berücksichtigt nur angezeigte Dateien bis 2 MB und höchstens
  20 Treffer pro Datei.
- Bestehendes wird beim Anlegen, Umbenennen und Verschieben nie überschrieben.
  Wurde eine Datei inzwischen außerhalb geändert, fragt das Speichern nach.
- Löschen verschiebt in den Papierkorb. Ist er nicht nutzbar (unter WSL auf
  `/mnt/c` möglich), wird vor dem endgültigen Löschen noch einmal gefragt.
- Beim Löschen eines Ordners wird auch sein nicht sichtbarer Inhalt gezählt.
- Zeilenenden (LF/CRLF), BOM und Dateirechte bleiben erhalten. Gemischte
  Zeilenenden werden beim Speichern vereinheitlicht. Gelesen wird nur UTF-8.

## Entwicklung

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```
