import os

import pytest

from mdtool import store as store_module
from mdtool.store import ConflictError, Store, StoreError, TrashError


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    return Store(root)


def test_create_adds_suffix_and_never_overwrites(store):
    path = store.create_file(store.root, "notiz.v2")
    assert path.name == "notiz.v2.md"
    path.write_text("Inhalt")
    with pytest.raises(StoreError):
        store.create_file(store.root, "notiz.v2.md")
    assert path.read_text() == "Inhalt"


@pytest.mark.parametrize("name", ["", "  ", "..", "../x", "a/b", "a\\b", ".x", "a\nb"])
def test_bad_names(store, name):
    with pytest.raises(StoreError):
        store.create_file(store.root, name)
    with pytest.raises(StoreError):
        store.create_folder(store.root, name)


@pytest.mark.parametrize(
    "data", [b"a\nb\n", b"a\r\nb\r\n", b"\xef\xbb\xbfa\r\nb", "äöü €\n".encode(), b""]
)
def test_roundtrip_keeps_bytes(store, data):
    path = store.root / "a.md"
    path.write_bytes(data)
    doc = store.read(path)
    assert "\r" not in doc.text
    store.write(path, doc.text, doc)
    assert path.read_bytes() == data


def test_write_keeps_mode_and_leaves_no_temp(store):
    path = store.create_file(store.root, "a")
    path.chmod(0o640)
    store.write(path, "neu", store.read(path))
    assert path.stat().st_mode & 0o777 == 0o640
    assert os.listdir(store.root) == ["a.md"]


def test_write_detects_conflict_and_deletion(store):
    path = store.create_file(store.root, "a")
    doc = store.read(path)
    path.write_text("fremd")
    with pytest.raises(ConflictError):
        store.write(path, "meins", doc)
    assert path.read_text() == "fremd"
    path.unlink()
    with pytest.raises(ConflictError):
        store.write(path, "meins", doc)
    store.write(path, "meins", doc, force=True)
    assert path.read_text() == "meins"


def test_write_through_symlink_keeps_link(store):
    real = store.create_file(store.root, "real")
    link = store.root / "link.md"
    link.symlink_to(real)
    store.write(link, "x", store.read(link))
    assert link.is_symlink() and real.read_text() == "x"


def test_write_respects_readonly(store):
    path = store.create_file(store.root, "a")
    doc = store.read(path)
    path.chmod(0o444)
    with pytest.raises(StoreError):
        store.write(path, "x", doc)


def test_non_utf8(store):
    path = store.root / "a.md"
    path.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(StoreError):
        store.read(path)


def test_outside_is_refused(store, tmp_path):
    outside = tmp_path / "geheim.md"
    outside.write_text("geheim")
    link = store.root / "link.md"
    link.symlink_to(outside)
    assert not store.visible(link)
    for action in (store.read, store.trash, store.delete):
        with pytest.raises(StoreError):
            action(outside)
    with pytest.raises(StoreError):
        store.read(link)
    with pytest.raises(StoreError):
        store.create_file(tmp_path, "x")
    assert outside.read_text() == "geheim"


def test_root_is_protected(store):
    for action in (store.trash, store.delete):
        with pytest.raises(StoreError):
            action(store.root)
    with pytest.raises(StoreError):
        store.rename(store.root, "x")


def test_rename_and_move_never_overwrite(store):
    a = store.create_file(store.root, "a")
    b = store.create_file(store.root, "b")
    b.write_text("b")
    with pytest.raises(StoreError):
        store.rename(a, "b")
    sub = store.create_folder(store.root, "sub")
    (sub / "a.md").write_text("alt")
    with pytest.raises(StoreError):
        store.move(a, sub)
    assert b.read_text() == "b" and (sub / "a.md").read_text() == "alt"
    moved = store.move(b, sub)
    assert moved.read_text() == "b" and not b.exists()


def test_rename_case_only(store):
    a = store.create_file(store.root, "a")
    store.rename(a, "A")
    assert os.listdir(store.root) == ["A.md"]


def test_rename_to_hardlink_is_refused(store):
    a = store.create_file(store.root, "a")
    os.link(a, store.root / "b.md")
    with pytest.raises(StoreError):
        store.rename(a, "b")
    assert sorted(os.listdir(store.root)) == ["a.md", "b.md"]


def test_folder_not_into_itself(store):
    a = store.create_folder(store.root, "a")
    b = store.create_folder(a, "b")
    with pytest.raises(StoreError):
        store.move(a, b)
    assert b.is_dir()


def test_delete_symlink_keeps_target(store):
    folder = store.create_folder(store.root, "a")
    store.create_file(folder, "x")
    link = store.root / "link"
    link.symlink_to(folder)
    store.trash(link)
    assert not link.is_symlink() and (folder / "x.md").exists()


def test_trash_failure_keeps_file(store, monkeypatch):
    path = store.create_file(store.root, "a")

    def broken(_):
        raise PermissionError("kein Papierkorb")

    monkeypatch.setattr(store_module, "send2trash", broken)
    with pytest.raises(TrashError):
        store.trash(path)
    assert path.exists()


def test_count_contents(store):
    folder = store.create_folder(store.root, "a")
    store.create_file(folder, "x")
    (folder / "bild.png").write_bytes(b"")
    (folder / ".git").mkdir()
    (folder / ".git" / "y.md").write_text("")
    assert store.count_contents(folder) == (4, 3)


def test_folders(store):
    b = store.create_folder(store.create_folder(store.root, "a"), "b")
    (store.root / ".git").mkdir()
    assert store.folders() == ([store.root, store.root / "a", b], False)
    assert store.folders(limit=2)[1] is True
