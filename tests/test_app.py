"""Bedient die echte Oberfläche per Tastatur (ohne sichtbares Terminal)."""

import asyncio
import shutil
from pathlib import Path

import pytest
from textual.widgets import Input, Label, Markdown

from mdtool import store as store_module
from mdtool.app import MdToolApp
from mdtool.store import Store


@pytest.fixture
def root(tmp_path, monkeypatch):
    root = tmp_path / "notizen"
    (root / "privat").mkdir(parents=True)
    (root / "a.md").write_text("# Titel\n\nSiehe [b](privat/b%20c.md)\n")
    (root / "privat" / "b c.md").write_text("Unten")
    (root / "bild.png").write_bytes(b"")
    trash = tmp_path / "papierkorb"
    trash.mkdir()
    # Nie den echten Papierkorb benutzen.
    monkeypatch.setattr(
        store_module, "send2trash", lambda p: shutil.move(p, trash / Path(p).name)
    )
    return root.resolve()


def drive(root, steps, start=None):
    async def run():
        app = MdToolApp(Store(root), start=start)
        async with app.run_test(size=(110, 32)) as pilot:
            await settle(pilot)
            await steps(app, pilot)

    asyncio.run(run())


async def settle(pilot):
    await pilot.pause(0.2)
    await pilot.pause()


async def press(pilot, *keys):
    await pilot.press(*keys)
    await settle(pilot)


async def enter_name(app, pilot, name):
    app.screen.query_one(Input).value = name
    await press(pilot, "enter")


def test_tree_and_preview(root):
    async def steps(app, pilot):
        labels = [str(n.label) for n in app.tree_view.root.children]
        assert labels == ["privat", "a.md"]
        assert app.selected == root / "a.md"
        assert "# Titel" in app.query_one(Markdown).source

    drive(root, steps, start=root / "a.md")


def test_create_edit_save(root):
    async def steps(app, pilot):
        await press(pilot, "n")
        await enter_name(app, pilot, "neu")
        assert app.selected == root / "neu.md"
        await press(pilot, "e")
        await press(pilot, "d", "q", "n")  # Kürzel werden hier zu Text
        assert "ungespeichert" in str(app.query_one("#path", Label).content)
        await press(pilot, "ctrl+s")
        assert (root / "neu.md").read_text() == "dqn"
        await press(pilot, "escape")
        assert app.editing is None and app.focused is app.tree_view
        assert app.query_one(Markdown).source == "dqn"

    drive(root, steps)


def test_create_in_collapsed_folder(root):
    async def steps(app, pilot):
        await press(pilot, "down")
        assert app.selected == root / "privat"
        await press(pilot, "o")
        await enter_name(app, pilot, "tief")
        assert app.selected == root / "privat" / "tief"
        await press(pilot, "n")
        await enter_name(app, pilot, "[rot]x")
        assert app.selected == root / "privat" / "tief" / "[rot]x.md"

    drive(root, steps)


@pytest.mark.parametrize(
    "keys, expected, open_",
    [
        (["escape"], "orig", True),
        (["enter"], "Xorig", False),
        (["right", "enter"], "orig", False),
    ],
)
def test_unsaved_changes_prompt(root, keys, expected, open_):
    (root / "a.md").write_text("orig")

    async def steps(app, pilot):
        await press(pilot, "e")
        await press(pilot, "X")
        await press(pilot, "escape")
        assert len(app.screen_stack) == 2
        await press(pilot, *keys)
        assert (root / "a.md").read_text() == expected
        assert (app.editing is not None) is open_

    drive(root, steps, start=root / "a.md")


def test_quit_asks_when_dirty(root):
    async def steps(app, pilot):
        await press(pilot, "e")
        await press(pilot, "X")
        await press(pilot, "ctrl+q")
        assert app.is_running and len(app.screen_stack) == 2
        await press(pilot, "ctrl+q")
        assert len(app.screen_stack) == 2
        await press(pilot, "escape")
        assert app.editor.text.startswith("X")

    drive(root, steps, start=root / "a.md")


@pytest.mark.parametrize("keys, expected", [(["enter"], "fremd"), (["right", "enter"], "Xorig")])
def test_conflict(root, keys, expected):
    (root / "a.md").write_text("orig")

    async def steps(app, pilot):
        await press(pilot, "e")
        await press(pilot, "X")
        (root / "a.md").write_text("fremd")
        await press(pilot, "ctrl+s")
        assert len(app.screen_stack) == 2
        await press(pilot, *keys)
        assert (root / "a.md").read_text() == expected
        assert app.editor.text == "Xorig"

    drive(root, steps, start=root / "a.md")


def test_rename_and_move(root):
    async def steps(app, pilot):
        await press(pilot, "r")
        await enter_name(app, pilot, "z")
        assert app.selected == root / "z.md"
        await press(pilot, "m")
        await press(pilot, *"priv")
        await press(pilot, "enter")
        assert app.selected == root / "privat" / "z.md"
        assert not (root / "z.md").exists()

    drive(root, steps, start=root / "a.md")


def test_delete_defaults_to_cancel(root):
    async def steps(app, pilot):
        await press(pilot, "d")
        await press(pilot, "enter")
        assert (root / "a.md").exists()
        await press(pilot, "d")
        await press(pilot, "right", "enter")
        assert not (root / "a.md").exists()
        assert (root.parent / "papierkorb" / "a.md").exists()

    drive(root, steps, start=root / "a.md")


def test_permanent_delete_needs_second_confirmation(root, monkeypatch):
    def broken(_):
        raise PermissionError("kein Papierkorb")

    monkeypatch.setattr(store_module, "send2trash", broken)

    async def steps(app, pilot):
        await press(pilot, "d")
        await press(pilot, "right", "enter")
        await press(pilot, "enter")
        assert (root / "a.md").exists()
        await press(pilot, "d")
        await press(pilot, "right", "enter")
        await press(pilot, "right", "enter")
        assert not (root / "a.md").exists()

    drive(root, steps, start=root / "a.md")


def test_root_cannot_be_deleted(root):
    async def steps(app, pilot):
        assert app.selected == root
        await press(pilot, "d")
        assert len(app.screen_stack) == 1

    drive(root, steps)


def test_error_message_with_brackets(root):
    (root / "[b]x.md").write_text("")

    async def steps(app, pilot):
        await press(pilot, "n")
        await enter_name(app, pilot, "[b]x")
        assert app.is_running and len(app.screen_stack) == 1

    drive(root, steps)


def test_relative_link(root):
    async def steps(app, pilot):
        markdown = app.query_one(Markdown)
        markdown.post_message(Markdown.LinkClicked(markdown, "privat/b%20c.md"))
        await settle(pilot)
        assert app.selected == root / "privat" / "b c.md"
        assert markdown.source == "Unten"

    drive(root, steps, start=root / "a.md")


def test_external_change_is_picked_up(root):
    async def steps(app, pilot):
        (root / "extern.md").write_text("x")
        await press(pilot, "f5")
        assert "extern.md" in [str(n.label) for n in app.tree_view.root.children]

    drive(root, steps)
