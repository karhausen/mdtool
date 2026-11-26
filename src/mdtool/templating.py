"""Lädt die Vorlagen aus dem Ordner templates."""

from __future__ import annotations

import re
from datetime import date
from importlib.resources import files

FOLDER_FILE = ".pandora.yaml"

YAML_WORDS = {"true", "false", "yes", "no", "on", "off", "null", "y", "n"}


def template(name: str) -> str:
    return files("mdtool").joinpath("templates", name).read_text("utf-8")


def yaml_string(value: str) -> str:
    """Setzt nur dann Anführungszeichen, wenn YAML den Text sonst falsch läse."""
    if re.fullmatch(r"[^\W\d_][\w ,.()-]*", value) and value.lower() not in YAML_WORDS:
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def frontmatter(title: str, today: date | None = None) -> str:
    text = template("datei.md")
    text = text.replace("{{date}}", (today or date.today()).isoformat())
    return text.replace("{{title}}", yaml_string(title))


def folder_settings() -> str:
    return template("ordner.yaml")
