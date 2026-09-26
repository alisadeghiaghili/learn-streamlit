"""In-memory simulated git object model for Learn Git Branching.

The engine is a pure structural model of commits, refs, and HEAD. It never
touches the filesystem or a real git binary. Object ids are opaque strings
assigned by the engine (``C1``, ``C2``, ... or caller-provided ids when loading
a level tree).
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Iterable


class GitError(Exception):
    """Raised when a simulated git operation cannot be performed."""


@dataclass
class Commit:
    """A single commit node.

    Attributes:
        id: Unique commit id within one engine snapshot.
        parents: Parent commit ids, in first-parent then other-parent order.
        message: Commit message shown in the graph tooltip / log.
        root_commit: Whether this commit has no parents by construction.
    """

    id: str
    parents: list[str]
    message: str = ""
    root_commit: bool = False

    def to_dict(self) -> dict[str, object]:
        """Serialize this commit for tree I/O.

        Returns:
            Mapping with id, parents, optional rootCommit, and message.
        """
        data: dict[str, object] = {"id": self.id, "parents": list(self.parents)}
        if self.root_commit or not self.parents:
            data["rootCommit"] = True
        if self.message:
            data["message"] = self.message
        return data

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Commit:
        """Deserialize a commit from tree I/O.

        Args:
            data: Mapping produced by :meth:`to_dict` or LGB tree JSON.

        Returns:
            A Commit instance.

        Raises:
            ValueError: If ``id`` is missing or parents are malformed.
        """
        if "id" not in data:
            raise ValueError("commit missing id")
        parents_raw = data.get("parents", [])
        if not isinstance(parents_raw, list):
            raise ValueError("commit parents must be a list")
        parents = [str(p) for p in parents_raw]
        return cls(
            id=str(data["id"]),
            parents=parents,
            message=str(data.get("message", "")),
            root_commit=bool(data.get("rootCommit", False)) or not parents,
        )


@dataclass
class Ref:
    """A named pointer to a commit (branch, remote branch, or tag).

    Attributes:
        id: Ref name (``main``, ``o/main``, ``v1``).
        target: Commit id the ref points at.
        kind: One of ``branch``, ``remote``, or ``tag``.
    """

    id: str
    target: str
    kind: str = "branch"

    def to_dict(self) -> dict[str, object]:
        """Serialize the ref.

        Returns:
            Mapping with id/target (LGB tree shape).
        """
        return {"id": self.id, "target": self.target}

    @classmethod
    def from_dict(cls, data: dict[str, object], kind: str = "branch") -> Ref:
        """Deserialize a ref.

        Args:
            data: Mapping with id and target.
            kind: Ref kind override.

        Returns:
            A Ref instance.
        """
        return cls(id=str(data["id"]), target=str(data["target"]), kind=kind)


@dataclass
class GitEngine:
    """Simulated repository: commits, refs, HEAD, and remote bookkeeping.

    Attributes:
        commits: All commits by id, including unreachable ones left by rewrites.
        branches: Local branches by name.
        remote_branches: Remote-tracking branches (``o/main`` style names).
        tags: Tags by name.
        head_target: Either a branch name (attached) or commit id (detached).
        head_detached: Whether HEAD is detached.
        remote_url: Display name of the simulated remote, if any.
        remote_exists: Whether a fake remote has been created.
        next_id: Monotonic counter for new commit ids.
    """

    commits: dict[str, Commit] = field(default_factory=dict)
    branches: dict[str, Ref] = field(default_factory=dict)
    remote_branches: dict[str, Ref] = field(default_factory=dict)
    tags: dict[str, Ref] = field(default_factory=dict)
    head_target: str = "main"
    head_detached: bool = False
    remote_url: str | None = None
    remote_exists: bool = False
    next_id: int = 1

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    @classmethod
    def empty(cls) -> GitEngine:
        """Create an empty engine with no commits.

        Returns:
            A fresh GitEngine.
        """
        return cls()

    @classmethod
    def sandbox(cls) -> GitEngine:
        """Create the default sandbox: root + one commit on ``main``.

        Returns:
            Engine with C1 -> C0 and HEAD on main.
        """
        eng = cls()
        eng.commits["C0"] = Commit(id="C0", parents=[], message="Initial commit", root_commit=True)
        eng.commits["C1"] = Commit(id="C1", parents=["C0"], message="Commit")
        eng.branches["main"] = Ref(id="main", target="C1", kind="branch")
        eng.head_target = "main"
        eng.head_detached = False
        eng.next_id = 2
        return eng

    def snapshot(self) -> GitEngine:
        """Deep-copy the engine for undo / level reset.

        Returns:
            A detached copy of this engine.
        """
        return deepcopy(self)

    def restore(self, other: GitEngine) -> None:
        """Overwrite this engine with a previous snapshot.

        Args:
            other: Snapshot previously taken from :meth:`snapshot`.
        """
        self.commits = deepcopy(other.commits)
        self.branches = deepcopy(other.branches)
        self.remote_branches = deepcopy(other.remote_branches)
        self.tags = deepcopy(other.tags)
        self.head_target = other.head_target
        self.head_detached = other.head_detached
        self.remote_url = other.remote_url
        self.remote_exists = other.remote_exists
        self.next_id = other.next_id

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def head_commit_id(self) -> str:
        """Resolve HEAD to a commit id.

        Returns:
            Commit id that HEAD points at.

        Raises:
            GitError: If HEAD cannot be resolved.
        """
        if self.head_detached:
            if self.head_target not in self.commits:
                raise GitError(f"HEAD is detached at unknown commit '{self.head_target}'")
            return self.head_target
        ref = self.branches.get(self.head_target)
        if ref is None:
            raise GitError(f"HEAD points at unknown branch '{self.head_target}'")
        return ref.target

    def resolve_commit(self, name: str) -> str:
        """Resolve a user-supplied revision name to a commit id.

        Supports commit ids, branch names, remote branch names, tags, and
        a few relative forms: ``main~1``, ``main~2``, ``HEAD~1``.

        Args:
            name: Revision string.

        Returns:
            Commit id.

        Raises:
            GitError: If the revision cannot be resolved.
        """
        if not name or name in {".", "^"}:
            raise GitError(f"unknown revision '{name}'")

        base_name = name
        hop = 0
        if "~" in name:
            base_name, _, hop_s = name.partition("~")
            try:
                hop = int(hop_s)
            except ValueError as exc:
                raise GitError(f"unknown revision '{name}'") from exc
        elif name.endswith("^"):
            base_name = name[:-1] or "HEAD"
            hop = 1

        if base_name in {"HEAD", "head"}:
            commit_id = self.head_commit_id()
        elif base_name in self.commits:
            commit_id = base_name
        elif base_name in self.branches:
            commit_id = self.branches[base_name].target
        elif base_name in self.remote_branches:
            commit_id = self.remote_branches[base_name].target
        elif base_name in self.tags:
            commit_id = self.tags[base_name].target
        else:
            raise GitError(f"unknown revision '{name}'")

        for _ in range(hop):
            commit = self.commits[commit_id]
            if not commit.parents:
                raise GitError(f"revision '{name}' walks past a root commit")
            commit_id = commit.parents[0]
        return commit_id

    def is_ancestor(self, ancestor_id: str, descendant_id: str) -> bool:
        """Return whether ``ancestor_id`` is reachable from ``descendant_id``.

        Args:
            ancestor_id: Candidate ancestor commit id.
            descendant_id: Candidate descendant commit id.

        Returns:
            True if ancestor is on the ancestry path of descendant (or equal).
        """
        if ancestor_id == descendant_id:
            return True
        seen: set[str] = set()
        stack = [descendant_id]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            if current == ancestor_id:
                return True
            commit = self.commits.get(current)
            if commit is None:
                continue
            stack.extend(commit.parents)
        return False

    def merge_base(self, left_id: str, right_id: str) -> str | None:
        """Find a simple merge base (first common ancestor in BFS).

        Args:
            left_id: First commit id.
            right_id: Second commit id.

        Returns:
            Commit id of a merge base, or None when histories are unrelated.
        """
        if self.is_ancestor(left_id, right_id):
            return left_id
        if self.is_ancestor(right_id, left_id):
            return right_id

        def ancestors(start: str) -> list[str]:
            order: list[str] = []
            seen: set[str] = set()
            stack = [start]
            while stack:
                current = stack.pop()
                if current in seen:
                    continue
                seen.add(current)
                order.append(current)
                commit = self.commits.get(current)
                if commit:
                    stack.extend(commit.parents)
            return order

        left_anc = set(ancestors(left_id))
        for candidate in ancestors(right_id):
            if candidate in left_anc:
                return candidate
        return None

    def commits_inclusive_history(self, start_id: str) -> list[str]:
        """List commit ids reachable from ``start_id``, parents after children.

        Args:
            start_id: Tip commit id.

        Returns:
            Commit ids in reverse-topological (child before parent) order.
        """
        order: list[str] = []
        seen: set[str] = set()
        stack = [start_id]
        while stack:
            current = stack.pop()
            if current in seen or current not in self.commits:
                continue
            seen.add(current)
            order.append(current)
            stack.extend(self.commits[current].parents)
        return order

    def all_ref_names(self) -> list[str]:
        """Return every ref name: branches, remote branches, and tags.

        Returns:
            Sorted ref names.
        """
        names = set(self.branches) | set(self.remote_branches) | set(self.tags)
        return sorted(names)

    def ref_target(self, name: str) -> str:
        """Resolve a ref name to its commit id.

        Args:
            name: Branch, remote branch, or tag name.

        Returns:
            Commit id.

        Raises:
            GitError: If the ref does not exist.
        """
        if name in self.branches:
            return self.branches[name].target
        if name in self.remote_branches:
            return self.remote_branches[name].target
        if name in self.tags:
            return self.tags[name].target
        raise GitError(f"unknown ref '{name}'")

    def allocate_commit_id(self) -> str:
        """Allocate the next free commit id (``C1``, ``C2``, ...).

        Returns:
            Unused commit id.
        """
        while f"C{self.next_id}" in self.commits:
            self.next_id += 1
        cid = f"C{self.next_id}"
        self.next_id += 1
        return cid

    def add_commit(self, parents: Iterable[str], message: str = "") -> str:
        """Create a commit and return its id.

        Args:
            parents: Parent commit ids (already validated).
            message: Optional commit message.

        Returns:
            New commit id.
        """
        parent_list = list(parents)
        cid = self.allocate_commit_id()
        self.commits[cid] = Commit(
            id=cid,
            parents=parent_list,
            message=message or "Commit",
            root_commit=not parent_list,
        )
        return cid

    def set_head_branch(self, branch: str) -> None:
        """Point HEAD at a local branch.

        Args:
            branch: Existing local branch name.

        Raises:
            GitError: If the branch does not exist.
        """
        if branch not in self.branches:
            raise GitError(f"branch '{branch}' does not exist")
        self.head_target = branch
        self.head_detached = False

    def set_head_commit(self, commit_id: str) -> None:
        """Detach HEAD at a commit.

        Args:
            commit_id: Existing commit id.

        Raises:
            GitError: If the commit does not exist.
        """
        if commit_id not in self.commits:
            raise GitError(f"commit '{commit_id}' does not exist")
        self.head_target = commit_id
        self.head_detached = True

    def move_branch(self, branch: str, commit_id: str) -> None:
        """Point a local branch at a commit (create if missing).

        Args:
            branch: Branch name.
            commit_id: Commit id.

        Raises:
            GitError: If the commit does not exist.
        """
        if commit_id not in self.commits:
            raise GitError(f"commit '{commit_id}' does not exist")
        self.branches[branch] = Ref(id=branch, target=commit_id, kind="branch")

    def move_remote_branch(self, name: str, commit_id: str) -> None:
        """Point a remote-tracking branch at a commit.

        Args:
            name: Remote branch name (``o/main``).
            commit_id: Commit id.
        """
        if commit_id not in self.commits:
            raise GitError(f"commit '{commit_id}' does not exist")
        self.remote_branches[name] = Ref(id=name, target=commit_id, kind="remote")
