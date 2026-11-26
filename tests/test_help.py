import asyncio
import re

import pytest

from mdtool.app import Editor, MdToolApp
from mdtool.help import HELP, HelpDialog
from mdtool.store import Store

KEY_NAMES = {"slash": "/", "full_stop": ".", "question_mark": "?", "escape": "Esc"}


def documented_keys() -> set[str]:
    keys = set()
    for row in re.findall(r"^- (.+?): ", HELP, re.M):
        keys.update(re.findall(r"`([^`]+)`", row))
    return keys


def shown(key: str) -> str:
    name = KEY_NAMES.get(key, key)
    if name.startswith("ctrl+"):
        return "Strg+" + name[5:].upper()
    if re.fullmatch(r"f\d+", name):
        return name.upper()
    return name


@pytest.mark.parametrize("binding", MdToolApp.BINDINGS + Editor.BINDINGS)
def test_every_key_is_documented(binding):
    assert shown(binding.key) in documented_keys()


def run(root, steps):
    async def main():
        app = MdToolApp(Store(root))
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.2)
            await steps(app, pilot)

    asyncio.run(main())


async def press(pilot, *keys):
    await pilot.press(*keys)
    await pilot.pause(0.2)


@pytest.mark.parametrize("open_key, close_key", [("h", "escape"), ("question_mark", "h"), ("f1", "q")])
def test_open_and_close(tmp_path, open_key, close_key):
    async def steps(app, pilot):
        await press(pilot, open_key)
        assert isinstance(app.screen, HelpDialog)
        assert len(app.screen_stack) == 2
        await press(pilot, close_key)
        assert len(app.screen_stack) == 1 and app.is_running
        await press(pilot, open_key, open_key)  # dieselbe Taste schließt wieder
        assert len(app.screen_stack) == 1 and app.is_running

    run(tmp_path, steps)


def test_f1_works_in_editor(tmp_path):
    (tmp_path / "a.md").write_text("")

    async def steps(app, pilot):
        await press(pilot, "down", "e")
        assert app.editing is not None
        await press(pilot, "h")
        assert app.editor.text == "h" and len(app.screen_stack) == 1
        await press(pilot, "f1")
        assert isinstance(app.screen, HelpDialog)
        await press(pilot, "escape")
        assert app.editing is not None and app.editor.text == "h"

    run(tmp_path, steps)
