import asyncio

import pytest

from mdtool.app import MdToolApp
from mdtool.store import Store
from mdtool.typing_aids import frontmatter_as_code, in_code_block, next_list_prefix


@pytest.mark.parametrize(
    "line, expected",
    [
        ("- a", "- "),
        ("  * a", "  * "),
        ("+  a", "+  "),
        ("9. a", "10. "),
        ("3) a", "4) "),
        ("- [ ] a", "- [ ] "),
        ("- [x] a", "- [ ] "),
        ("- [link](x)", "- "),
        ("- ", ""),
        ("- [ ] ", ""),
        ("- [ ]", ""),
        ("Text", None),
        ("-a", None),
        ("---", None),
    ],
)
def test_next_list_prefix(line, expected):
    assert next_list_prefix(line, len(line)) == expected


def test_enter_before_content_is_normal():
    assert next_list_prefix("- a", 0) is None


def test_code_block():
    assert in_code_block(["```python"])
    assert in_code_block(["````", "```"])
    assert not in_code_block(["```", "```"])
    assert not in_code_block(["```a```"])


def test_frontmatter_preview():
    assert frontmatter_as_code("---\na: 1\n---\n# T") == "```yaml\na: 1\n```\n\n# T"
    assert frontmatter_as_code("---\nkein Ende") == "---\nkein Ende"


@pytest.mark.parametrize(
    "start, keys, expected",
    [
        ("", "-| |a|enter|b", "- a\n- b"),
        ("", "-| |a|enter|enter|b", "- a\nb"),
        ("", "-| |[| |]| |a|enter|b", "- [ ] a\n- [ ] b"),
        ("", "-| |[|x|]| |a|enter|b", "- [x] a\n- [ ] b"),
        ("", "-| |[|]| |a", "- [ ] a"),
        ("", "[|t|x|t|]|(|u|)", "[txt](u)"),
        ("", "[|backspace|a", "a"),
        ("", "[|enter", "[\n ]"),
        ("- [ ] x", "end|enter|y", "- [ ] x\n- [ ] y"),
        ("- ab", "end|left|enter", "- a\n- b"),
        ("```\n- a", "down|end|enter|b", "```\n- a\nb"),
        ("- a", "end|enter|ctrl+z", "- a"),
        ("abc", "shift+right|[", "[bc"),
    ],
)
def test_editor_keys(tmp_path, start, keys, expected):
    path = tmp_path / "a.md"
    path.write_text(start)

    async def run():
        app = MdToolApp(Store(tmp_path), start=path.resolve())
        async with app.run_test() as pilot:
            await pilot.pause(0.2)
            await pilot.press("e")
            await pilot.pause()
            for key in keys.split("|"):
                await pilot.press(key)
            await pilot.pause()
            assert app.editor.text == expected

    asyncio.run(run())
