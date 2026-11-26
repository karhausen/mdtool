"""Tests für updated-Datum, eigene Vorlagen und Suche."""

import asyncio
from datetime import date

import pytest
from textual.widgets import Input, OptionList

from mdtool.app import MdToolApp
from mdtool.cli import main
from mdtool.store import Store, StoreError
from mdtool.templating import default_template, frontmatter
from mdtool.typing_aids import touch_updated

TODAY = date(2026, 11, 26)


# -- updated -------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("---\ntitle: a\nupdated:\n---\nx", (2, "updated:", "updated: 2026-11-26")),
        ("---\nupdated: 2020-01-01\n---\n", (1, "updated: 2020-01-01", "updated: 2026-11-26")),
        ("---\nupdated: 2026-11-26\n---\n", None),
        ("---\ntitle: a\n---\nupdated: alt", None),  # nicht im Frontmatter
        ("Text\n---\nupdated:\n---\n", None),
        ("---\n  updated: x\n---\n", None),  # eingerückt: anderer Schlüssel
        ("---\nupdated:\nkein Ende", None),
    ],
)
def test_touch_updated(text, expected):
    assert touch_updated(text, TODAY) == expected


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


def test_save_sets_updated_and_keeps_cursor(tmp_path):
    path = tmp_path / "a.md"
    path.write_text("---\nupdated: 2000-01-01\n---\nText")

    async def steps(app, pilot):
        await press(pilot, "e")
        app.editor.move_cursor((3, 4))
        await press(pilot, "!")
        await press(pilot, "ctrl+s")
        today = date.today().isoformat()
        assert path.read_text() == f"---\nupdated: {today}\n---\nText!"
        assert app.editor.text == path.read_text()
        assert app.editor.cursor_location == (3, 5)
        assert not app.dirty
        await press(pilot, "ctrl+z", "ctrl+z")  # Rückgängig bleibt möglich
        assert "updated: 2000-01-01" in app.editor.text

    run_app(tmp_path, path.resolve(), steps)


def test_unchanged_file_is_not_touched(tmp_path):
    path = tmp_path / "a.md"
    path.write_text("---\nupdated: 2000-01-01\n---\n")

    async def steps(app, pilot):
        await press(pilot, "e")
        await press(pilot, "ctrl+s")
        assert path.read_text() == "---\nupdated: 2000-01-01\n---\n"

    run_app(tmp_path, path.resolve(), steps)


# -- eigene Vorlagen -----------------------------------------------------------


def test_user_templates_win(tmp_path, isolated_config):
    folder = isolated_config / "mdtool" / "templates"
    folder.mkdir(parents=True)
    (folder / "datei.md").write_text("# {{title}} ({{date}})\n")
    (folder / "ordner.yaml").write_text("owner: ich\n")
    store = Store(tmp_path)
    note = store.create_file(tmp_path, "Plan")
    assert note.read_text() == f"# Plan ({date.today().isoformat()})\n"
    sub = store.create_folder(tmp_path, "x")
    assert (sub / ".policy.yaml").read_text() == "owner: ich\n"


def test_partial_user_templates_fall_back(tmp_path, isolated_config):
    folder = isolated_config / "mdtool" / "templates"
    folder.mkdir(parents=True)
    (folder / "ordner.yaml").write_text("owner: ich\n")
    assert frontmatter("a").startswith("---\ntitle: a\n")


def test_broken_user_template_creates_nothing(tmp_path, isolated_config):
    folder = isolated_config / "mdtool" / "templates"
    folder.mkdir(parents=True)
    (folder / "datei.md").write_bytes(b"\xff\xfe")
    with pytest.raises(StoreError):
        Store(tmp_path).create_file(tmp_path, "a")
    assert not (tmp_path / "a.md").exists()


def test_cli_copies_defaults_without_overwriting(isolated_config, capsys):
    folder = isolated_config / "mdtool" / "templates"
    folder.mkdir(parents=True)
    (folder / "datei.md").write_text("meins")
    assert main(["--vorlagen"]) == 0
    assert (folder / "datei.md").read_text() == "meins"
    assert (folder / "ordner.yaml").read_text() == default_template("ordner.yaml")
    out = capsys.readouterr().out
    assert str(folder) in out and "ordner.yaml" in out
    assert main(["--vorlagen"]) == 0
    assert "nichts" in capsys.readouterr().out


# -- Suche ---------------------------------------------------------------------


@pytest.fixture
def notes(tmp_path):
    root = tmp_path / "n"
    (root / "projekt").mkdir(parents=True)
    (root / "projekt" / "Plan.md").write_text("Erste Zeile\n  Das ist der STRASSENplan\n")
    (root / "einkauf.md").write_text("Milch\nplan b")
    (root / ".versteckt").mkdir()
    (root / ".versteckt" / "x.md").write_text("plan geheim")
    (root / ".git").mkdir()
    (root / ".git" / "y.md").write_text("plan git")
    (root / "bild.png").write_text("plan")
    (root / "kaputt.md").write_bytes(b"plan \xff")
    return root.resolve()


def summary(hits, store):
    return [(store.rel(h.path), h.line, h.column) for h in hits]


def test_search_names_and_content(notes):
    store = Store(notes)
    hits = summary(store.search("PLAN"), store)
    assert hits == [
        ("einkauf.md", 1, 0),
        (".versteckt/x.md", 0, 0),
        ("projekt/Plan.md", None, 0),
        ("projekt/Plan.md", 1, 22),
    ]
    store.show_hidden = False
    assert ".versteckt/x.md" not in [h[0] for h in summary(store.search("plan"), store)]
    assert list(store.search("")) == []
    assert list(store.search("plan", stop=lambda: True)) == []


def test_search_limits_hits_per_file(tmp_path):
    (tmp_path / "a.md").write_text("x\n" * 100)
    assert len(list(Store(tmp_path).search("x"))) == 20


def test_search_skips_symlink_outside(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "draussen"
    outside.mkdir()
    (outside / "a.md").write_text("geheim")
    (root / "link").symlink_to(outside)
    assert list(Store(root).search("geheim")) == []


def test_search_dialog_opens_editor_at_hit(notes):
    async def steps(app, pilot):
        await press(pilot, "slash")
        app.screen.query_one(Input).value = "straßenplan"[:5]  # "straß"
        await pilot.pause(0.6)
        app.screen.query_one(Input).value = "strassen"
        await pilot.pause(0.6)
        options = app.screen.query_one(OptionList)
        assert options.option_count == 1
        assert "projekt/Plan.md:2" in str(options.get_option_at_index(0).prompt)
        await press(pilot, "enter")
        assert app.editing == notes / "projekt" / "Plan.md"
        assert app.editor.selected_text == "STRASSEN"
        await press(pilot, "escape")
        await press(pilot, "slash")
        assert app.screen.query_one(Input).value == "strassen"  # merkt sich die Suche
        await press(pilot, "escape")
        assert app.editing is None and len(app.screen_stack) == 1

    run_app(notes, None, steps)


def test_search_name_hit_shows_preview(notes):
    async def steps(app, pilot):
        await press(pilot, "slash")
        app.screen.query_one(Input).value = "einkauf"
        await pilot.pause(0.6)
        await press(pilot, "enter")
        assert app.editing is None
        assert app.selected == notes / "einkauf.md"

    run_app(notes, None, steps)


def test_search_closed_while_running(notes):
    async def steps(app, pilot):
        await press(pilot, "slash")
        app.screen.query_one(Input).value = "plan"
        await pilot.press("escape")
        await pilot.pause(0.6)
        assert app.is_running and len(app.screen_stack) == 1

    run_app(notes, None, steps)
