"""Tests für den Git-Abgleich mit einem lokalen Server-Repository."""

import asyncio
import subprocess

import pytest
from textual.widgets import Input, Label

from mdtool.app import MdToolApp
from mdtool.dialogs import GitDialog
from mdtool.gitsync import GitError, Repo
from mdtool.store import Store


def git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def remote(tmp_path, monkeypatch):
    """Ein Server-Repository mit einem ersten Commit; liefert Klon-Funktion."""
    config = tmp_path / "gitconfig"
    config.write_text(
        "[user]\n name = Test\n email = test@example.invalid\n"
        "[init]\n defaultBranch = main\n"
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    server = tmp_path / "server.git"
    git(tmp_path, "init", "-q", "--bare", str(server))
    seed = tmp_path / "seed"
    git(tmp_path, "clone", "-q", str(server), str(seed))
    (seed / "notizen").mkdir()
    (seed / "notizen" / "a.md").write_text("eins\n")
    (seed / "readme.txt").write_text("außerhalb\n")
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "start")
    git(seed, "push", "-q", "-u", "origin", "main")

    def clone(name):
        target = tmp_path / name
        git(tmp_path, "clone", "-q", str(server), str(target))
        return target

    return clone


def test_find_outside_repo(tmp_path):
    assert Repo.find(tmp_path) is None


def test_state_counts_only_base_folder(remote):
    work = remote("work")
    (work / "notizen" / "b.md").write_text("neu\n")
    (work / "readme.txt").write_text("geändert\n")
    repo = Repo.find(work / "notizen")
    assert repo.top == work
    state = repo.state()
    assert (state.branch, state.upstream, state.changes) == ("main", "origin/main", 1)
    assert state.summary == "⎇ main ●1"


def test_sync_commits_base_folder_and_pushes(remote):
    work, other = remote("work"), remote("other")
    notes = work / "notizen"
    (notes / "b.md").write_text("neu\n")
    (notes / "a.md").unlink()
    (work / "readme.txt").write_text("geändert\n")
    git(work, "add", "readme.txt")  # außerhalb vorgemerkt: bleibt draußen
    repo = Repo.find(notes)
    assert repo.sync("Notizen") == ["committet", "geholt", "hochgeladen"]
    assert git(work, "log", "-1", "--format=%s").strip() == "Notizen"
    # bleibt geändert, aber uncommittet (autostash nimmt nur die Vormerkung weg)
    assert git(work, "diff", "HEAD", "--name-only").strip() == "readme.txt"
    assert (work / "readme.txt").read_text() == "geändert\n"
    git(other, "pull", "-q")
    assert (other / "notizen" / "b.md").exists()
    assert not (other / "notizen" / "a.md").exists()
    assert (other / "readme.txt").read_text() == "außerhalb\n"
    assert repo.state().summary == "⎇ main"


def test_sync_pulls_changes_from_elsewhere(remote):
    work, other = remote("work"), remote("other")
    (other / "notizen" / "c.md").write_text("von woanders\n")
    Repo.find(other / "notizen").sync("x")
    (work / "notizen" / "d.md").write_text("hier\n")
    assert Repo.find(work / "notizen").sync("y") == ["committet", "geholt", "hochgeladen"]
    assert (work / "notizen" / "c.md").exists()
    git(other, "pull", "-q")
    assert (other / "notizen" / "d.md").exists()


def test_conflict_is_rolled_back(remote):
    work, other = remote("work"), remote("other")
    (other / "notizen" / "a.md").write_text("dort\n")
    Repo.find(other / "notizen").sync("dort")
    (work / "notizen" / "a.md").write_text("hier\n")
    repo = Repo.find(work / "notizen")
    with pytest.raises(GitError, match="Konflikt beim Holen in notizen/a.md"):
        repo.sync("hier")
    assert repo.state().busy is None
    assert (work / "notizen" / "a.md").read_text() == "hier\n"
    assert git(work, "log", "-1", "--format=%s").strip() == "hier"


def test_without_upstream(remote):
    work = remote("work")
    git(work, "switch", "-q", "-c", "neu")
    with pytest.raises(GitError, match="keinen Upstream.*git push -u origin neu"):
        Repo.find(work).sync("x")


def test_detached_head(remote):
    work = remote("work")
    git(work, "switch", "-q", "--detach")
    repo = Repo.find(work)
    with pytest.raises(GitError, match="detached"):
        repo.check(repo.state(), network=False)


# -- Oberfläche --------------------------------------------------------------------


def run_app(root, steps):
    async def run():
        app = MdToolApp(Store(root))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.3)
            await steps(app, pilot)

    asyncio.run(run())


async def press(pilot, *keys):
    await pilot.press(*keys)
    await pilot.pause(0.3)


def test_git_key_outside_repo(tmp_path):
    async def steps(app, pilot):
        await press(pilot, "g")
        assert len(app.screen_stack) == 1
        assert str(app.query_one("#git", Label).render()) == ""

    run_app(tmp_path, steps)


def test_git_dialog_syncs(remote):
    work, other = remote("work"), remote("other")
    (work / "notizen" / "b.md").write_text("neu\n")

    async def steps(app, pilot):
        assert "●1" in str(app.query_one("#git", Label).render())
        await press(pilot, "g")
        assert isinstance(app.screen, GitDialog)
        app.screen.query_one(Input).value = "aus mdtool"
        await press(pilot, "enter")
        for _ in range(20):
            if "●" not in str(app.query_one("#git", Label).render()):
                break
            await pilot.pause(0.2)
        assert str(app.query_one("#git", Label).render()) == "⎇ main"

    run_app(work / "notizen", steps)
    git(other, "pull", "-q")
    assert git(other, "log", "-1", "--format=%s").strip() == "aus mdtool"
