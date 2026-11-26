from datetime import date

import pytest

from mdtool.store import Store
from mdtool.templating import folder_settings, frontmatter, yaml_string


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


def test_templates_content():
    text = frontmatter("Notiz", date(2026, 1, 2))
    assert "title: Notiz\n" in text and "created: 2026-01-02\n" in text
    assert "{{" not in text
    lines = folder_settings().splitlines()
    assert "owner:" in lines and "  company_allowed: false" in lines


def test_hidden_non_markdown_file_stays_empty(tmp_path):
    assert Store(tmp_path).create_file(tmp_path, ".x.yaml").read_bytes() == b""


def test_new_folder_has_settings(tmp_path):
    folder = Store(tmp_path).create_folder(tmp_path, "neu")
    assert (folder / ".pandora.yaml").read_text("utf-8") == folder_settings()
    assert [p.name for p in folder.iterdir()] == [".pandora.yaml"]
