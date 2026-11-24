"""Einstiegspunkt für die Kommandozeile."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .store import Store, is_markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mdtool", description="Markdown-Dateien und Ordner im Terminal verwalten."
    )
    parser.add_argument(
        "pfad",
        nargs="?",
        default=".",
        help="Ordner oder Markdown-Datei (Standard: aktueller Ordner)",
    )
    parser.add_argument("--version", action="version", version=f"mdtool {__version__}")
    args = parser.parse_args(argv)

    path = Path(args.pfad).expanduser()
    if not path.exists():
        parser.error(f"Pfad nicht gefunden: {path}")
    start: Path | None = None
    if not path.is_dir():
        if not is_markdown(path):
            parser.error(f"Keine Markdown-Datei: {path}")
        start = path.resolve()
        path = start.parent

    from .app import MdToolApp  # erst hier, damit --help schnell bleibt

    MdToolApp(Store(path), start=start).run()
    return 0
