"""Lädt die Vorlagen: zuerst aus dem Konfigurationsordner, sonst die mitgelieferten."""

from __future__ import annotations

import os
import re
from datetime import date
from importlib.resources import files
from pathlib import Path

FOLDER_FILE = ".policy.yaml"
TEMPLATE_NAMES = ("datei.md", "ordner.yaml")

YAML_WORDS = {"true", "false", "yes", "no", "on", "off", "null", "y", "n"}


class TemplateError(Exception):
    pass


def user_template_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "mdtool" / "templates"


def default_template(name: str) -> str:
    return files("mdtool").joinpath("templates", name).read_text("utf-8")


def template(name: str) -> str:
    path = user_template_dir() / name
    if not path.is_file():
        return default_template(name)
    try:
        return path.read_text("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise TemplateError(f"Vorlage {path} nicht lesbar: {error}") from error


def copy_defaults() -> tuple[Path, list[str]]:
    """Kopiert fehlende Standardvorlagen; vorhandene bleiben unverändert."""
    folder = user_template_dir()
    folder.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in TEMPLATE_NAMES:
        try:
            with open(folder / name, "x", encoding="utf-8", newline="\n") as handle:
                handle.write(default_template(name))
            copied.append(name)
        except FileExistsError:
            pass
    return folder, copied


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
