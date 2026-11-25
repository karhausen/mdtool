from datetime import date

import pytest

from mdtool.store import Store
from mdtool.templates import FOLDER_TEMPLATE, frontmatter, yaml_string


@pytest.mark.parametrize(
    "value, expected",
    [
        ("Meine Notiz", "Meine Notiz"),
        ("Übersicht", "Übersicht"),
        ("a: b", '"a: b"'),
        ("2026-11-25", '"2026-11-25"'),
        ("true", '"true"'),
        ("[x]", '"[x]"'),
        ('sag "ja"', '"sag \\"ja\\""'),
        ("{x}", '"{x}"'),
    ],
)
def test_yaml_string(value, expected):
    assert yaml_string(value) == expected


def test_new_file_has_frontmatter(tmp_path):
    path = Store(tmp_path).create_file(tmp_path, "Pandora Contracts")
    assert path.read_text("utf-8") == frontmatter("Pandora Contracts", date.today())
    lines = path.read_text("utf-8").splitlines()
    assert lines[:2] == ["---", "title: Pandora Contracts"]
    assert "status: active" in lines and "---" in lines[2:]


def test_hidden_non_markdown_file_stays_empty(tmp_path):
    assert Store(tmp_path).create_file(tmp_path, ".x.yaml").read_bytes() == b""


def test_new_folder_has_settings(tmp_path):
    folder = Store(tmp_path).create_folder(tmp_path, "neu")
    assert (folder / ".pandora.yaml").read_text("utf-8") == FOLDER_TEMPLATE
    assert [p.name for p in folder.iterdir()] == [".pandora.yaml"]
