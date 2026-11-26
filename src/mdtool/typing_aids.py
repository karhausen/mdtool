"""Schreibhilfen des Editors als reine Textfunktionen."""

from __future__ import annotations

import re
from datetime import date

LIST_ITEM = re.compile(
    r"^(?P<indent>[ \t]*)(?P<marker>[-*+]|(?P<number>\d{1,9})(?P<delim>[.)]))"
    r"(?P<space>[ \t]+)(?P<box>\[[ xX]\](?:[ \t]+|$))?(?P<content>.*)$"
)
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
FRONTMATTER = re.compile(r"\A---[ \t]*\n(.*?)^(?:---|\.\.\.)[ \t]*(?:\n|\Z)", re.S | re.M)


def in_code_block(lines_before: list[str]) -> bool:
    """Steht die Zeile nach diesen Zeilen in einem offenen Codeblock?"""
    fence = ""
    for line in lines_before:
        match = FENCE.match(line)
        if match is None:
            continue
        marks, rest = match.groups()
        if not fence:
            if marks[0] == "~" or "`" not in rest:
                fence = marks
        elif marks[0] == fence[0] and len(marks) >= len(fence) and not rest.strip():
            fence = ""
    return bool(fence)


def next_list_prefix(line: str, column: int) -> str | None:
    """Was die neue Zeile nach Enter erhält.

    None: keine Liste. Leerer Text: der Punkt ist leer, die Liste endet hier.
    """
    match = LIST_ITEM.match(line)
    if match is None or column < match.start("content"):
        return None
    if not match["content"].strip():
        return ""
    marker = match["marker"]
    if match["number"]:
        marker = f"{int(match['number']) + 1}{match['delim']}"
    box = "[ ] " if match["box"] else ""
    return f"{match['indent']}{marker}{match['space']}{box}"


UPDATED = re.compile(r"^updated:(?P<value>[ \t]*.*)$")


def touch_updated(text: str, today: date) -> tuple[int, str, str] | None:
    """Findet `updated:` im Frontmatter: (Zeile, alter Inhalt, neuer Inhalt)."""
    match = FRONTMATTER.match(text)
    if match is None:
        return None
    lines = text.split("\n")
    for row in range(1, match[0].count("\n")):
        line = lines[row]
        if UPDATED.match(line):
            new = f"updated: {today.isoformat()}"
            return (row, line, new) if line != new else None
    return None


HEADING = re.compile(r"^#[ \t]+(.+?)[ \t#]*$", re.M)


def has_frontmatter(text: str) -> bool:
    return FRONTMATTER.match(text) is not None


def first_heading(text: str) -> str | None:
    """Text der ersten Überschrift der obersten Ebene außerhalb von Codeblöcken."""
    lines = text.split("\n")
    for row, line in enumerate(lines):
        match = HEADING.match(line)
        if match and not in_code_block(lines[:row]):
            return match[1]
    return None


def frontmatter_as_code(text: str) -> str:
    """Zeigt Frontmatter in der Vorschau als YAML-Block statt als Überschrift."""
    match = FRONTMATTER.match(text)
    if match is None:
        return text
    return f"{as_code(match[1], 'yaml')}\n{text[match.end():]}"


def as_code(text: str, language: str = "") -> str:
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{language}\n{text.rstrip()}\n{fence}\n"


def toggle_checkbox(line: str) -> str:
    """Hakt eine Checkbox ab oder wieder auf; macht andere Zeilen zur Checkbox."""
    match = LIST_ITEM.match(line)
    if match is None:
        indent = line[: len(line) - len(line.lstrip())]
        return f"{indent}- [ ] {line.lstrip()}"
    box = match["box"]
    if box is None:
        start = match.start("content")
        return f"{line[:start]}[ ] {line[start:]}"
    mark = " " if box[1] in "xX" else "x"
    start = match.start("box")
    return f"{line[:start + 1]}{mark}{line[start + 2:]}"
