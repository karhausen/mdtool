"""Dateioperationen, beschränkt auf einen Basisordner (ohne Oberfläche)."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from send2trash import send2trash

from .metadata import describe, fields, matches, parse_filter
from .templating import FOLDER_FILE, TemplateError, folder_settings, frontmatter

MARKDOWN_SUFFIXES = {".md", ".markdown"}
BOM = b"\xef\xbb\xbf"


class StoreError(Exception):
    """Fehler mit einer Meldung, die direkt angezeigt werden kann."""


class ConflictError(StoreError):
    """Die Datei wurde seit dem Öffnen außerhalb des Tools verändert."""


class TrashError(StoreError):
    """Der Papierkorb ist für diesen Ort nicht nutzbar."""


@dataclass(frozen=True)
class Document:
    text: str  # Zeilenenden immer "\n"
    newline: str
    bom: bool
    fingerprint: str


SEARCH_MAX_BYTES = 2_000_000
SEARCH_HITS_PER_FILE = 20


@dataclass(frozen=True)
class Hit:
    path: Path
    line: int | None  # None: Treffer im Dateinamen
    column: int
    text: str


def is_markdown(path: Path) -> bool:
    return path.suffix.lower() in MARKDOWN_SUFFIXES


def is_hidden(name: str) -> bool:
    return name.startswith(".")


def _fingerprint(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reason(error: OSError) -> str:
    return error.strerror or str(error)


class Store:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.show_hidden = True
        if not self.root.is_dir():
            raise StoreError(f"Kein Ordner: {self.root}")

    # -- Pfade ---------------------------------------------------------------

    def rel(self, path: Path) -> str:
        if path == self.root:
            return "."
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)

    def contains(self, path: Path) -> bool:
        """Liegt das Ziel (nach Auflösen von Symlinks) im Basisordner?"""
        try:
            return Path(path).resolve().is_relative_to(self.root)
        except (OSError, RuntimeError):
            return False

    def visible(self, path: Path) -> bool:
        """Soll der Eintrag im Baum erscheinen?"""
        try:
            if not self._shows_name(path.name) or not self.contains(path):
                return False
            return path.is_dir() or is_markdown(path) or is_hidden(path.name)
        except OSError:
            return False

    def _shows_name(self, name: str) -> bool:
        # Git-Interna bleiben immer ausgeblendet.
        return name != ".git" and (self.show_hidden or not is_hidden(name))

    def listed(self, path: Path) -> bool:
        """Sichtbar, und liegt auch jeder Ordner darüber im sichtbaren Bereich?"""
        if path == self.root:
            return True
        try:
            parts = path.relative_to(self.root).parts
        except ValueError:
            return False
        return all(map(self._shows_name, parts)) and self.visible(path)

    def _target(self, path: Path) -> Path:
        """Ziel zum Lesen oder Schreiben: Symlinks werden aufgelöst."""
        if not self.contains(path):
            raise StoreError("Der Pfad liegt außerhalb des Basisordners.")
        return Path(path).resolve()

    def _entry(self, path: Path) -> Path:
        """Der Eintrag selbst: ein Symlink am Ende wird nicht aufgelöst."""
        path = Path(path)
        entry = path.parent.resolve() / path.name
        if entry == self.root:
            raise StoreError("Der Basisordner selbst kann nicht verändert werden.")
        if path.name in ("", ".", "..") or not entry.is_relative_to(self.root):
            raise StoreError("Der Pfad liegt außerhalb des Basisordners.")
        return entry

    @staticmethod
    def _clean_name(name: str) -> str:
        name = name.strip()
        if not name:
            raise StoreError("Der Name darf nicht leer sein.")
        if name in (".", "..", ".git"):
            raise StoreError(f"Der Name „{name}“ ist nicht erlaubt.")
        if any(c in "/\\" or not c.isprintable() for c in name):
            raise StoreError("Der Name enthält unzulässige Zeichen.")
        return name

    @classmethod
    def _file_name(cls, name: str) -> str:
        name = cls._clean_name(name)
        if is_hidden(name) or is_markdown(Path(name)):
            return name
        return f"{name}.md"

    # -- Lesen und Schreiben -------------------------------------------------

    def read(self, path: Path) -> Document:
        target = self._target(path)
        try:
            data = target.read_bytes()
        except OSError as error:
            raise StoreError(f"Lesen fehlgeschlagen: {_reason(error)}") from error
        bom = data.startswith(BOM)
        try:
            text = data.removeprefix(BOM).decode("utf-8")
        except UnicodeDecodeError as error:
            raise StoreError("Die Datei ist nicht in UTF-8 kodiert.") from error
        crlf = text.count("\r\n")
        newline = "\r\n" if crlf > text.count("\n") - crlf else "\n"
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        return Document(text, newline, bom, _fingerprint(data))

    def write(
        self, path: Path, text: str, base: Document, *, force: bool = False
    ) -> Document:
        """Speichert atomar und behält Zeilenenden, BOM und Dateirechte bei."""
        target = self._target(path)
        try:
            if not force:
                current = target.read_bytes() if target.exists() else None
                if current is None or _fingerprint(current) != base.fingerprint:
                    raise ConflictError(
                        "Die Datei wurde außerhalb des Tools geändert oder gelöscht."
                    )
            data = text.replace("\n", base.newline).encode("utf-8")
            if base.bom:
                data = BOM + data
            self._replace(target, data)
        except OSError as error:
            raise StoreError(f"Speichern fehlgeschlagen: {_reason(error)}") from error
        return Document(text, base.newline, base.bom, _fingerprint(data))

    @staticmethod
    def _replace(target: Path, data: bytes) -> None:
        if target.exists() and not os.access(target, os.W_OK):
            raise PermissionError(None, "Die Datei ist schreibgeschützt")
        fd, temp = tempfile.mkstemp(prefix=".mdtool-", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if target.exists():
                shutil.copymode(target, temp)
            else:
                umask = os.umask(0)
                os.umask(umask)
                os.chmod(temp, 0o666 & ~umask)
            os.replace(temp, target)
        except BaseException:
            Path(temp).unlink(missing_ok=True)
            raise

    # -- Anlegen, Umbenennen, Verschieben, Löschen ---------------------------

    def create_file(self, folder: Path, name: str) -> Path:
        path = self._entry(self._target(folder) / self._file_name(name))
        try:
            content = frontmatter(path.stem) if is_markdown(path) else ""
        except TemplateError as error:
            raise StoreError(str(error)) from error
        try:
            with open(path, "x", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
        except FileExistsError:
            raise StoreError(f"„{path.name}“ existiert bereits.") from None
        except OSError as error:
            raise StoreError(f"Anlegen fehlgeschlagen: {_reason(error)}") from error
        return path

    def create_folder(self, folder: Path, name: str) -> Path:
        path = self._entry(self._target(folder) / self._clean_name(name))
        try:
            path.mkdir()
        except FileExistsError:
            raise StoreError(f"„{path.name}“ existiert bereits.") from None
        except OSError as error:
            raise StoreError(f"Anlegen fehlgeschlagen: {_reason(error)}") from error
        try:
            (path / FOLDER_FILE).write_text(folder_settings(), "utf-8", newline="\n")
        except TemplateError as error:
            raise StoreError(f"Ordner angelegt, aber {FOLDER_FILE} fehlt: {error}") from error
        except OSError as error:
            raise StoreError(
                f"Ordner angelegt, aber {FOLDER_FILE} fehlt: {_reason(error)}"
            ) from error
        return path

    def rename(self, path: Path, name: str) -> Path:
        entry = self._entry(path)
        name = self._clean_name(name) if entry.is_dir() else self._file_name(name)
        return self._move(entry, entry.parent / name)

    def move(self, path: Path, folder: Path) -> Path:
        entry = self._entry(path)
        folder = self._target(folder)
        if not folder.is_dir():
            raise StoreError("Das Ziel ist kein Ordner.")
        if not entry.is_symlink() and folder.is_relative_to(entry):
            raise StoreError("Ein Ordner kann nicht in sich selbst verschoben werden.")
        return self._move(entry, folder / entry.name)

    @staticmethod
    def _move(source: Path, target: Path) -> Path:
        if source == target:
            return source
        if not os.path.lexists(source):
            raise StoreError(f"„{source.name}“ existiert nicht mehr.")
        if os.path.lexists(target):
            # Auf Dateisystemen ohne Groß-/Kleinschreibung (z. B. /mnt/c unter
            # WSL) ist "a.md" -> "A.md" derselbe Eintrag und damit erlaubt.
            same_entry = (
                source.parent == target.parent
                and source.name.casefold() == target.name.casefold()
                and os.path.samestat(os.lstat(source), os.lstat(target))
            )
            if not same_entry:
                raise StoreError(f"„{target.name}“ existiert dort bereits.")
        try:
            if source.parent == target.parent:
                os.rename(source, target)
            else:
                shutil.move(source, target)
        except (OSError, shutil.Error) as error:
            raise StoreError(f"Verschieben fehlgeschlagen: {error}") from error
        return target

    def count_contents(self, folder: Path) -> tuple[int, int]:
        """(alle Einträge, davon im Tool nicht sichtbare) unterhalb des Ordners."""
        total = hidden = 0
        for base, dirs, files in os.walk(self._entry(folder)):
            in_hidden = not self.listed(Path(base))
            for name in dirs + files:
                total += 1
                if in_hidden or not self.visible(Path(base) / name):
                    hidden += 1
        return total, hidden

    def trash(self, path: Path) -> None:
        """Verschiebt in den Papierkorb. Bei Symlinks wird nur der Link entfernt."""
        entry = self._entry(path)
        if entry.is_symlink():
            self.delete(entry)
            return
        if not entry.exists():
            raise StoreError(f"„{entry.name}“ existiert nicht mehr.")
        try:
            send2trash(str(entry))
        except Exception as error:  # send2trash wirft je nach Plattform Verschiedenes
            raise TrashError(f"Papierkorb nicht nutzbar: {error}") from error

    def delete(self, path: Path) -> None:
        """Löscht endgültig."""
        entry = self._entry(path)
        try:
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        except OSError as error:
            raise StoreError(f"Löschen fehlgeschlagen: {_reason(error)}") from error

    def search(
        self, query: str, stop: Callable[[], bool] = lambda: False
    ) -> Iterator[Hit]:
        """Sucht ohne Groß-/Kleinschreibung in Dateinamen und Inhalten.

        Besteht die Anfrage nur aus `feld:wert`, wird im Frontmatter gefiltert.
        """
        filters = parse_filter(query)
        needle = query.casefold()
        if not needle:
            return
        for base, dirs, files in os.walk(self.root):
            if stop():
                return
            dirs[:] = sorted(
                d for d in dirs if self.visible(Path(base) / d)
                and not (Path(base) / d).is_symlink()
            )
            for name in sorted(files):
                path = Path(base) / name
                if not self.visible(path):
                    continue
                if filters is not None:
                    yield from self._match_fields(path, filters)
                    continue
                if needle in name.casefold():
                    yield Hit(path, None, 0, self.rel(path))
                yield from self._search_file(path, needle)

    def _match_fields(
        self, path: Path, filters: list[tuple[str, str]]
    ) -> Iterator[Hit]:
        if not is_markdown(path):
            return
        try:
            if path.stat().st_size > SEARCH_MAX_BYTES:
                return
            found = fields(self.read(path).text)
        except (OSError, StoreError):
            return
        if found is not None and matches(found, filters):
            yield Hit(path, None, 0, f"{self.rel(path)}  {describe(found, filters)}")

    def _search_file(self, path: Path, needle: str) -> Iterator[Hit]:
        try:
            if path.stat().st_size > SEARCH_MAX_BYTES:
                return
            text = self.read(path).text
        except (OSError, StoreError):
            return
        found = 0
        for row, line in enumerate(text.split("\n")):
            folded = line.casefold()
            if needle not in folded:
                continue
            # casefold kann die Länge ändern (z. B. ß); dann Spalte 0.
            column = folded.find(needle) if len(folded) == len(line) else 0
            yield Hit(path, row, column, line)
            found += 1
            if found >= SEARCH_HITS_PER_FILE:
                return

    def folders(self, limit: int = 5000) -> tuple[list[Path], bool]:
        """Alle sichtbaren Ordner; der zweite Wert meldet eine gekürzte Liste."""
        found = [self.root]
        for base, dirs, _ in os.walk(self.root):
            dirs[:] = sorted(d for d in dirs if self._shows_name(d))
            for name in dirs:
                path = Path(base) / name
                if path.is_symlink():
                    continue
                if len(found) >= limit:
                    return found, True
                found.append(path)
        return sorted(found), False
