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
| `n` / `o` | neue Datei / neuer Ordner im ausgewählten Ordner |
| `e` | bearbeiten (`Strg+S` speichert, `Esc` beendet) |
| `E` | im externen Editor öffnen (`$VISUAL`, `$EDITOR`, sonst `nano`) |
| `r` / `m` / `d` | umbenennen / verschieben / löschen |
| `F5` | neu einlesen |
| `q`, `Strg+Q` | beenden |

## Gut zu wissen

- Das Tool arbeitet nur im Basisordner. Symlinks nach außen werden ausgeblendet.
- Angezeigt werden Ordner und Dateien mit `.md` oder `.markdown`, keine
  versteckten. Beim Anlegen wird `.md` automatisch ergänzt.
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
