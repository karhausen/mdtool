"""Tests für Checkboxen per Taste, Status/Priorität und Filter nach Feldern."""

import asyncio
from datetime import date

import pytest
from textual.widgets import Button, Input, OptionList

from mdtool.app import MdToolApp
from mdtool.dialogs import ChoiceDialog, SearchDialog
from mdtool.metadata import fields, matches, parse_filter, set_field
from mdtool.store import Store
from mdtool.typing_aids import toggle_checkbox

FRONT = "---\ntitle: A\ntags: [projekt, Kunde]\nstatus: active\npriority: normal\nowner:\naliases:\n  - eins\n  - 'zwei'\nupdated:\n---\n# A\n"


# -- reine Funktionen ------------------------------------------------------------


@pytest.mark.parametrize(
    "line, expected",
    [
        ("- [ ] a", "- [x] a"),
        ("- [x] a", "- [ ] a"),
        ("  * [X] a", "  * [ ] a"),
        ("1. [ ] a", "1. [x] a"),
        ("- a", "- [ ] a"),
        ("3) a", "3) [ ] a"),
        ("Text", "- [ ] Text"),
        ("  Text", "  - [ ] Text"),
        ("", "- [ ] "),
        ("- [ ]", "- [x]"),
    ],
)
def test_toggle_checkbox(line, expected):
    assert toggle_checkbox(line) == expected


def test_fields():
    found = fields(FRONT)
    assert found["title"] == ["A"]
    assert found["tags"] == ["projekt", "Kunde"]
    assert found["owner"] == []
    assert found["aliases"] == ["eins", "zwei"]
    assert fields("# ohne\n") is None


@pytest.mark.parametrize(
    "query, expected",
    [
        ("status:active", [("status", "active")]),
        ("Tag:Projekt priority:", [("tags", "projekt"), ("priority", "")]),
        ("status: active", None),  # Leerzeichen: normale Textsuche
        ("http://x", [("http", "//x")]),
        ("einkauf", None),
        ("", None),
    ],
)
def test_parse_filter(query, expected):
    assert parse_filter(query) == expected


@pytest.mark.parametrize(
    "query, expected",
    [
        ("status:act", True),
        ("tag:kunde", True),
        ("tag:projekt status:done", False),
        ("owner:", True),
        ("title:", False),
        ("fehlt:x", False),
        ("alias:zwei", True),
    ],
)
def test_matches(query, expected):
    assert matches(fields(FRONT), parse_filter(query)) is expected


def test_set_field():
    assert "\nstatus: done\n" in set_field(FRONT, "status", "done")
    added = set_field("---\ntitle: A\n---\nText", "priority", "high")
    assert added == "---\ntitle: A\npriority: high\n---\nText"
    assert set_field("---\n---\n", "status", "done") == "---\nstatus: done\n---\n"
    assert set_field("---\ntitle: A\n---", "status", "x") == "---\ntitle: A\nstatus: x\n---"
    assert set_field("Text", "status", "x") is None


def test_store_filters_fields(tmp_path):
    (tmp_path / "a.md").write_text(FRONT)
    (tmp_path / "b.md").write_text("---\nstatus: done\n---\nstatus:active im Text\n")
    (tmp_path / "c.md").write_text("status:active ohne Frontmatter\n")
    hits = list(Store(tmp_path).search("status:active"))
    assert [h.path.name for h in hits] == ["a.md"]
    assert hits[0].line is None and "status: active" in hits[0].text
    # normale Textsuche bleibt möglich
    assert len(list(Store(tmp_path).search("im Text"))) == 1


# -- Oberfläche --------------------------------------------------------------------


def run_app(root, start, steps):
    async def run():
        app = MdToolApp(Store(root), start=start)
        async with app.run_test(size=(110, 32)) as pilot:
            await pilot.pause(0.2)
            await steps(app, pilot)

    asyncio.run(run())


async def press(pilot, *keys):
    await pilot.press(*keys)
    await pilot.pause(0.2)
    await pilot.pause()


def test_set_status_writes_file(tmp_path):
    path = tmp_path / "a.md"
    path.write_text(FRONT)

    async def steps(app, pilot):
        await press(pilot, "s")
        assert isinstance(app.screen, ChoiceDialog)
        assert app.screen.focused.id == "active"  # aktueller Wert vorausgewählt
        await press(pilot, "right", "right", "enter")  # active → waiting → done
        assert len(app.screen_stack) == 1

    run_app(tmp_path, path, steps)
    text = path.read_text()
    assert "\nstatus: done\n" in text
    assert f"\nupdated: {date.today().isoformat()}\n" in text


def test_set_priority_adds_field_and_cancel_keeps_file(tmp_path):
    path = tmp_path / "a.md"
    path.write_text("---\ntitle: A\n---\nText\n")

    async def steps(app, pilot):
        await press(pilot, "p", "escape")
        assert path.read_text() == "---\ntitle: A\n---\nText\n"
        await press(pilot, "p")
        assert isinstance(app.screen.focused, Button)
        await press(pilot, "right", "right", "enter")

    run_app(tmp_path, path, steps)
    assert path.read_text() == "---\ntitle: A\npriority: high\n---\nText\n"


def test_status_needs_frontmatter(tmp_path):
    path = tmp_path / "a.md"
    path.write_text("Text\n")

    async def steps(app, pilot):
        await press(pilot, "s")
        assert len(app.screen_stack) == 1

    run_app(tmp_path, path, steps)
    assert path.read_text() == "Text\n"


def test_ctrl_t_toggles_lines(tmp_path):
    path = tmp_path / "a.md"
    path.write_text("- [ ] eins\n\nzwei\n")

    async def steps(app, pilot):
        await press(pilot, "e", "ctrl+t")
        assert app.editor.text.startswith("- [x] eins\n")
        app.editor.select_all()
        await press(pilot, "ctrl+t")
        assert app.editor.text == "- [ ] eins\n\n- [ ] zwei\n"
        await press(pilot, "ctrl+s")

    run_app(tmp_path, path, steps)
    assert path.read_text() == "- [ ] eins\n\n- [ ] zwei\n"


def test_search_dialog_filters(tmp_path):
    (tmp_path / "a.md").write_text(FRONT)
    (tmp_path / "b.md").write_text("---\nstatus: done\n---\n")

    async def steps(app, pilot):
        await press(pilot, "slash")
        assert isinstance(app.screen, SearchDialog)
        app.screen.query_one(Input).value = "status:done"
        await pilot.pause(0.5)
        options = app.screen.query_one(OptionList)
        assert options.option_count == 1
        await press(pilot, "enter")
        assert app.shown == tmp_path / "b.md"
        assert app.editing is None

    run_app(tmp_path, None, steps)
