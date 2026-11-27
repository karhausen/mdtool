"""Abgleich des Basisordners mit Git: committen, holen, hochladen.

Git läuft ohne Rückfragen. Braucht es eine Anmeldung, die nicht gespeichert
ist, gibt es eine Fehlermeldung statt eines hängenden Programms.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path

TIMEOUT = 120  # Sekunden, für Netzwerkzugriffe


class GitError(Exception):
    pass


@dataclass
class RepoState:
    branch: str | None  # None: kein Branch ausgecheckt
    upstream: str | None
    ahead: int
    behind: int
    changes: int  # geänderte Einträge im Basisordner
    busy: str | None  # laufender Merge oder Rebase

    @property
    def summary(self) -> str:
        parts = [f"⎇ {self.branch or 'kein Branch'}"]
        if self.changes:
            parts.append(f"●{self.changes}")
        if self.ahead:
            parts.append(f"↑{self.ahead}")
        if self.behind:
            parts.append(f"↓{self.behind}")
        return " ".join(parts)


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    env["LC_ALL"] = "C"  # Ausgaben einheitlich auswerten
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    return env


def default_message(today: date | None = None) -> str:
    return f"mdtool: {(today or date.today()).isoformat()}"


class Repo:
    def __init__(self, root: Path, top: Path) -> None:
        self.root = root
        self.top = top

    @classmethod
    def find(cls, root: Path) -> Repo | None:
        """Das Repository, in dem der Basisordner liegt, sonst None."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=root, env=_env(), capture_output=True, text=True, timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0 or not result.stdout.strip():
            return None
        return cls(root, Path(result.stdout.strip()))

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        try:
            result = subprocess.run(
                ["git", *args], cwd=self.root, env=_env(),
                capture_output=True, text=True, timeout=TIMEOUT,
            )
        except subprocess.TimeoutExpired as error:
            raise GitError(f"git {args[0]} dauert zu lange, abgebrochen.") from error
        except OSError as error:
            raise GitError(f"git konnte nicht gestartet werden: {error}") from error
        if check and result.returncode != 0:
            raise GitError(_explain(args[0], result.stderr or result.stdout))
        return result

    def state(self) -> RepoState:
        out = self._git(
            "status", "--porcelain=v2", "--branch", "-z", "--", "."
        ).stdout
        branch = upstream = None
        ahead = behind = changes = 0
        tokens = iter(out.split("\0"))
        for token in tokens:
            if token.startswith("# branch.head "):
                head = token[len("# branch.head "):]
                branch = None if head == "(detached)" else head
            elif token.startswith("# branch.upstream "):
                upstream = token[len("# branch.upstream "):]
            elif token.startswith("# branch.ab "):
                a, b = token[len("# branch.ab "):].split()
                ahead, behind = int(a.lstrip("+")), int(b.lstrip("-"))
            elif token[:2] in ("1 ", "2 ", "u ", "? "):
                changes += 1
                if token.startswith("2 "):
                    next(tokens, None)  # alter Pfad einer Umbenennung
        return RepoState(branch, upstream, ahead, behind, changes, self._busy())

    def _busy(self) -> str | None:
        for name, label in (
            ("rebase-merge", "Rebase"),
            ("rebase-apply", "Rebase"),
            ("MERGE_HEAD", "Merge"),
        ):
            path = self._git("rev-parse", "--git-path", name).stdout.strip()
            if (self.root / path).exists():
                return label
        return None

    def check(self, state: RepoState, network: bool) -> None:
        if state.busy:
            raise GitError(
                f"Im Repository läuft noch ein {state.busy}. Bitte im Terminal "
                "abschließen."
            )
        if state.branch is None:
            raise GitError("Es ist kein Branch ausgecheckt (detached HEAD).")
        if network and state.upstream is None:
            raise GitError(
                f"Der Branch {state.branch} hat keinen Upstream. Einmalig im "
                f"Terminal: git push -u origin {state.branch}"
            )

    def commit(self, message: str) -> bool:
        """Committet alle Änderungen im Basisordner; False: nichts zu tun."""
        self._git("add", "-A", "--", ".")
        staged = self._git(
            "diff", "--cached", "--quiet", "--", ".", check=False
        ).returncode
        if staged == 0:
            return False
        # Nur der Basisordner, auch wenn außerhalb etwas vorgemerkt ist.
        self._git("commit", "-q", "-m", message or default_message(), "--", ".")
        return True

    def pull(self) -> bool:
        """Holt neue Commits; False: den Branch gibt es auf dem Server noch nicht."""
        result = self._git("pull", "--rebase", "--autostash", "-q", check=False)
        if result.returncode == 0:
            return True
        if "no such ref was fetched" in result.stderr:
            return False
        if self._busy() == "Rebase":
            files = self._git(
                "diff", "--name-only", "--diff-filter=U", check=False
            ).stdout.split()
            self._git("rebase", "--abort", check=False)
            which = f" in {', '.join(files[:5])}" if files else ""
            raise GitError(
                f"Konflikt beim Holen{which}. Nichts wurde verändert, dein Commit "
                "ist erhalten. Bitte im Terminal mit git pull lösen."
            )
        raise GitError(_explain("pull", result.stderr or result.stdout))

    def push(self) -> None:
        self._git("push", "-q")

    def sync(self, message: str) -> list[str]:
        """Committen, holen, hochladen. Liefert, was passiert ist."""
        state = self.state()
        self.check(state, network=True)
        done = []
        if self.commit(message):
            done.append("committet")
        if self.pull():
            done.append("geholt")
        if self.state().ahead or not self._remote_has_branch():
            self.push()
            done.append("hochgeladen")
        return done

    def _remote_has_branch(self) -> bool:
        return self._git("rev-parse", "--verify", "-q", "@{upstream}", check=False).returncode == 0

    def fetch_only(self) -> None:
        self.check(self.state(), network=True)
        self.pull()


def _explain(command: str, output: str) -> str:
    text = output.strip()
    lowered = text.lower()
    if "terminal prompts disabled" in lowered or "could not read username" in lowered:
        return (
            "Git braucht eine Anmeldung. Bitte einmal im Terminal git "
            f"{command} ausführen, damit die Zugangsdaten gespeichert werden."
        )
    if "permission denied (publickey)" in lowered or "host key verification" in lowered:
        return "SSH-Anmeldung fehlgeschlagen. Bitte im Terminal prüfen (ssh-agent)."
    if "could not resolve host" in lowered or "unable to access" in lowered:
        return "Der Server ist nicht erreichbar. Besteht eine Netzverbindung?"
    if "rejected" in lowered:
        return "Hochladen abgelehnt: Auf dem Server gibt es neuere Commits."
    last = text.splitlines()[-1] if text else "unbekannter Fehler"
    return f"git {command} fehlgeschlagen: {last}"
