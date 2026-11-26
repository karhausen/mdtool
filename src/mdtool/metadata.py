"""Frontmatter-Felder lesen, setzen und filtern, ohne YAML-Bibliothek.

Verstanden wird die einfache Form aus den Vorlagen: `feld: wert` auf oberster
Ebene, Listen als `[a, b]` oder als eingerückte Zeilen mit `- eintrag`.
"""

from __future__ import annotations

import re

from .typing_aids import FRONTMATTER

STATUS = ("active", "waiting", "done", "archived")
PRIORITY = ("low", "normal", "high")
CHOICES = {"status": STATUS, "priority": PRIORITY}

FIELD = re.compile(r"^(?P<key>[A-Za-z_][\w-]*)[ \t]*:(?:[ \t]+(?P<value>.*?))?[ \t]*$")
ITEM = re.compile(r"^[ \t]*-[ \t]+(?P<value>.*?)[ \t]*$")
FILTER = re.compile(r"^(?P<key>[A-Za-z_][\w-]*):(?P<value>.*)$")
ALIASES = {"tag": "tags", "alias": "aliases"}


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def _values(raw: str) -> list[str]:
    raw = raw.strip()
    if raw.startswith("#"):
        return []
    if raw.startswith("[") and raw.endswith("]"):
        return [_unquote(v.strip()) for v in raw[1:-1].split(",") if v.strip()]
    return [_unquote(raw)] if raw else []


def fields(text: str) -> dict[str, list[str]] | None:
    """Felder des Frontmatters; None, wenn die Datei keines hat."""
    match = FRONTMATTER.match(text)
    if match is None:
        return None
    result: dict[str, list[str]] = {}
    current: str | None = None
    for line in match[1].split("\n"):
        field = FIELD.match(line)
        if field:
            current = field["key"].lower()
            result[current] = _values(field["value"] or "")
            continue
        item = ITEM.match(line)
        if item and current is not None:
            result[current].extend(_values(item["value"]))
        elif line.strip() and not line[0].isspace():
            current = None
    return result


def set_field(text: str, key: str, value: str) -> str | None:
    """Setzt ein einfaches Feld; None, wenn die Datei kein Frontmatter hat."""
    match = FRONTMATTER.match(text)
    if match is None:
        return None
    lines = text.split("\n")
    # Zeile des schließenden Trenners
    end = match[0].count("\n") - (1 if match[0].endswith("\n") else 0)
    new = f"{key}: {value}"
    for row in range(1, end):
        field = FIELD.match(lines[row])
        if field and field["key"].lower() == key:
            lines[row] = new
            return "\n".join(lines)
    lines.insert(end, new)
    return "\n".join(lines)


def parse_filter(query: str) -> list[tuple[str, str]] | None:
    """`status:done tag:projekt` wird zu Bedingungen; sonst None (Textsuche)."""
    words = query.split()
    if not words:
        return None
    result = []
    for word in words:
        match = FILTER.match(word)
        if match is None:
            return None
        key = match["key"].lower()
        result.append((ALIASES.get(key, key), match["value"].casefold()))
    return result


def matches(found: dict[str, list[str]], filters: list[tuple[str, str]]) -> bool:
    """Jede Bedingung muss passen. Ein leerer Wert verlangt ein leeres Feld."""
    for key, wanted in filters:
        if key not in found:
            return False
        values = [v.casefold() for v in found[key]]
        if wanted == "":
            if values:
                return False
        elif not any(wanted in v for v in values):
            return False
    return True


def describe(found: dict[str, list[str]], filters: list[tuple[str, str]]) -> str:
    """Kurztext der passenden Felder für die Trefferliste."""
    parts = []
    for key in dict.fromkeys(key for key, _ in filters):
        parts.append(f"{key}: {', '.join(found.get(key, [])) or '–'}")
    return " · ".join(parts)
