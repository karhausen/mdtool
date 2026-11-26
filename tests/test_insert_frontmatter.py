import asyncio
from datetime import date

import pytest

from mdtool.app import MdToolApp
from mdtool.store import Store
from mdtool.templating import frontmatter
from mdtool.typing_aids import first_heading, has_frontmatter


@pytest.mark.parametrize(
    "text, expected",
    [
        ("# Titel\nText", "Titel"),
        ("Text\n\n#  Mit Abstand ##\n", "Mit Abstand"),
        ("## Unterpunkt\n", None),
        ("```\n# Kommentar\n```\n# Echt", "Echt"),
        ("#Kein Titel", None),
    ],
)
def test_first_heading(text, expected):
    assert first_heading(text) == expected


def test_has_frontmatter():
    assert has_frontmatter("---\na: 1\n---\nText")
    assert not has_frontmatter("Text\n---\na: 1\n---\n")
    assert not has_frontmatter("---\nnur eine Linie")


def run(root, start, steps):
    async def main():
        app = MdToolApp(Store(root), start=start)
        async with app.run_test(size=(110, 32)) as pilot:
            await pilot.pause(0.2)
            await steps(app, pilot)

    asyncio.run(main())


async def press(pilot, *keys):
    await pilot.press(*keys)
    await pilot.pause(0.2)
    await pilot.pause()


def test_insert_and_save(tmp_path):
    path = tmp_path / "notiz.md"
    path.write_text("# Mein Thema\n\nInhalt\n")

    async def steps(app, pilot):
        await press(pilot, "f")
        assert app.editing == path.resolve() and app.dirty
        expected = frontmatter("Mein Thema") + "# Mein Thema\n\nInhalt\n"
        assert app.editor.text == expected
        assert path.read_text() == "# Mein Thema\n\nInhalt\n"  # noch nicht gespeichert
        await press(pilot, "ctrl+s")
        saved = path.read_text()
        assert saved.startswith("---\ntitle: Mein Thema\n")
        assert f"updated: {date.today().isoformat()}\n" in saved
        assert saved.endswith("---\n\n# Mein Thema\n\nInhalt\n")

    run(tmp_path, path.resolve(), steps)


def test_insert_can_be_discarded(tmp_path):
    path = tmp_path / "notiz.md"
    path.write_text("Inhalt")

    async def steps(app, pilot):
        await press(pilot, "f")
        assert "title: notiz\n" in app.editor.text
        await press(pilot, "escape")
        await press(pilot, "right", "enter")  # Verwerfen
        assert app.editing is None
        assert path.read_text() == "Inhalt"

    run(tmp_path, path.resolve(), steps)


def test_existing_frontmatter_is_kept(tmp_path):
    path = tmp_path / "notiz.md"
    path.write_text("---\ntitle: x\n---\nInhalt")

    async def steps(app, pilot):
        await press(pilot, "f")
        assert app.editing is None

    run(tmp_path, path.resolve(), steps)


@pytest.mark.parametrize("name", [".policy.yaml", "ordner"])
def test_only_markdown_files(tmp_path, name):
    path = tmp_path / name
    if name == "ordner":
        path.mkdir()
    else:
        path.write_text("owner:\n")

    async def steps(app, pilot):
        await press(pilot, "f")
        assert app.editing is None
        if name != "ordner":
            assert path.read_text() == "owner:\n"

    run(tmp_path, path.resolve(), steps)


def test_blocked_while_editing(tmp_path):
    path = tmp_path / "notiz.md"
    path.write_text("")

    async def steps(app, pilot):
        await press(pilot, "e")
        await press(pilot, "f")
        assert app.editor.text == "f"  # nur getippt, nichts eingefügt

    run(tmp_path, path.resolve(), steps)
