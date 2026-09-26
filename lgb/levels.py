"""Level catalog for learn-streamlit.

Each level stores an LGB-compatible start tree, goal tree, solution command
string, English copy, and a golf target (optimal command count).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lgb.model import GitEngine
from lgb.tree_io import load_tree


@dataclass
class Level:
    """One playable level.

    Attributes:
        id: Stable slug used in URLs / session state.
        sequence: Series key (``intro``, ``rampup``, ``rebase``, ``remote``).
        name: Short title.
        hint: One-line hint shown in the sidebar.
        lesson: Multi-line teaching blurb.
        start_tree: JSON tree for the starting repository.
        goal_tree: JSON tree describing the solved repository.
        solution_command: Canonical shortest solution (git golf).
        golf_target: Expected command count for a perfect score.
    """

    id: str
    sequence: str
    name: str
    hint: str
    lesson: str
    start_tree: str
    goal_tree: str
    solution_command: str
    golf_target: int = 1

    def start_engine(self) -> GitEngine:
        """Materialize the starting engine.

        Returns:
            Fresh engine from ``start_tree``.
        """
        return load_tree(self.start_tree)

    def goal_engine(self) -> GitEngine:
        """Materialize the goal engine.

        Returns:
            Fresh engine from ``goal_tree``.
        """
        return load_tree(self.goal_tree)


SEQUENCE_TITLES: dict[str, str] = {
    "intro": "Introduction to Commits and Branching",
    "rampup": "Ramp Up on Detaching and Relative Refs",
    "rebase": "Rebase and Cherry-Pick Mastery",
    "remote": "Push, Pull, and Remote Branches",
}

SEQUENCE_BLURBS: dict[str, str] = {
    "intro": "Learn commits, branches, merges, and rebases with a live commit graph.",
    "rampup": "Detach HEAD, walk history with ~ and ^, reset and revert.",
    "rebase": "Rewrite history cleanly with rebase, --onto, and cherry-pick.",
    "remote": "Simulate origin and practice fetch / pull / push / teamwork.",
}


def _tree(
    commits: dict[str, list[str]],
    branches: dict[str, str],
    head: str,
    remote_branches: dict[str, str] | None = None,
    tags: dict[str, str] | None = None,
) -> str:
    """Build a compact LGB tree JSON string.

    Args:
        commits: Map of commit id → parent ids.
        branches: Map of branch name → tip commit id.
        head: Branch name or commit id for HEAD.
        remote_branches: Optional remote-tracking map.
        tags: Optional tag map.

    Returns:
        JSON string.
    """
    import json

    commit_obj: dict[str, Any] = {}
    for cid, parents in commits.items():
        entry: dict[str, Any] = {"id": cid, "parents": parents}
        if not parents:
            entry["rootCommit"] = True
        commit_obj[cid] = entry
    payload = {
        "commits": commit_obj,
        "branches": {n: {"id": n, "target": t} for n, t in branches.items()},
        "remoteBranches": {
            n: {"id": n, "target": t} for n, t in (remote_branches or {}).items()
        },
        "tags": {n: {"id": n, "target": t} for n, t in (tags or {}).items()},
        "HEAD": {"id": "HEAD", "target": head},
    }
    return json.dumps(payload, separators=(",", ":"))


def _levels() -> list[Level]:
    """Return the built-in level list.

    Returns:
        Levels in play order across sequences.
    """
    return [
        # ---------------------------------------------------------------- intro
        Level(
            id="intro-commits-1",
            sequence="intro",
            name="Introduction to Commits",
            hint="Just type `git commit` twice. Watch the graph grow to the right.",
            lesson=(
                "A commit is a snapshot of the project plus a pointer to its parent.\n\n"
                "In this app the graph draws older commits on the left and newer on the right. "
                "Each circle is a commit; green circles have one parent (or none if they are root commits).\n\n"
                "Create two commits to match the goal tree."
            ),
            start_tree=_tree({"C0": [], "C1": ["C0"]}, {"main": "C1"}, "main"),
            goal_tree=_tree({"C0": [], "C1": ["C0"], "C2": ["C1"], "C3": ["C2"]}, {"main": "C3"}, "main"),
            solution_command="git commit; git commit",
            golf_target=2,
        ),
        Level(
            id="intro-branching-1",
            sequence="intro",
            name="Branching in Git",
            hint="`git branch bugFix` then `git checkout bugFix` — or one shot: `git checkout -b bugFix`.",
            lesson=(
                "A branch is just a movable label on a commit. Creating one is cheap.\n\n"
                "`git checkout -b bugFix` creates the branch at HEAD and switches to it. "
                "The blue pill shows where the branch points; the yellow HEAD pill shows where you are."
            ),
            start_tree=_tree({"C0": [], "C1": ["C0"]}, {"main": "C1"}, "main"),
            goal_tree=_tree(
                {"C0": [], "C1": ["C0"]},
                {"main": "C1", "bugFix": "C1"},
                "bugFix",
            ),
            solution_command="git checkout -b bugFix",
            golf_target=1,
        ),
        Level(
            id="intro-branching-2",
            sequence="intro",
            name="Branching and Committing",
            hint="Create `bugFix`, switch to it, then commit.",
            lesson=(
                "Branches only move when you commit (or force-move them). "
                "Commit on `bugFix` and leave `main` where it is."
            ),
            start_tree=_tree({"C0": [], "C1": ["C0"]}, {"main": "C1"}, "main"),
            goal_tree=_tree(
                {"C0": [], "C1": ["C0"], "C2": ["C1"]},
                {"main": "C1", "bugFix": "C2"},
                "bugFix",
            ),
            solution_command="git checkout -b bugFix; git commit",
            golf_target=2,
        ),
        Level(
            id="intro-merging-1",
            sequence="intro",
            name="Merging with Git",
            hint="`git checkout main` then `git merge bugFix`.",
            lesson=(
                "Merging joins two histories. If one tip is a direct ancestor of the other, git "
                "fast-forwards. Otherwise it creates a merge commit with two parents (purple).\n\n"
                "Fast-forward first by checking out `main` and merging `bugFix`."
            ),
            start_tree=_tree(
                {"C0": [], "C1": ["C0"], "C2": ["C1"]},
                {"main": "C1", "bugFix": "C2"},
                "main",
            ),
            goal_tree=_tree(
                {"C0": [], "C1": ["C0"], "C2": ["C1"]},
                {"main": "C2", "bugFix": "C2"},
                "main",
            ),
            solution_command="git merge bugFix",
            golf_target=1,
        ),
        Level(
            id="intro-merging-2",
            sequence="intro",
            name="Merge Commit",
            hint="Create `bugFix`, commit on both branches after diverging, then `git merge`.",
            lesson=(
                "When both sides have new commits, merge creates a purple merge commit "
                "with two parents. That is the classic diamond shape."
            ),
            start_tree=_tree(
                {"C0": [], "C1": ["C0"]},
                {"main": "C1"},
                "main",
            ),
            goal_tree=_tree(
                {
                    "C0": [],
                    "C1": ["C0"],
                    "C2": ["C1"],
                    "C3": ["C1"],
                    "C4": ["C3", "C2"],
                },
                {"main": "C4", "bugFix": "C2"},
                "main",
            ),
            solution_command=(
                "git checkout -b bugFix; git commit; git checkout main; git commit; git merge bugFix"
            ),
            golf_target=5,
        ),
        Level(
            id="intro-rebasing-1",
            sequence="intro",
            name="Rebase Introduction",
            hint="`git rebase main` while on `bugFix`, then move `main` up (`git merge bugFix`).",
            lesson=(
                "Rebase copies commits onto a new base and moves the branch. "
                "History looks linear — great for review, but it rewrites commit ids.\n\n"
                "Replay `bugFix` onto `main`, then move `main` to the same tip."
            ),
            start_tree=_tree(
                {"C0": [], "C1": ["C0"], "C2": ["C1"]},
                {"main": "C1", "bugFix": "C2"},
                "bugFix",
            ),
            goal_tree=_tree(
                {"C0": [], "C1": ["C0"], "C3": ["C1"]},
                {"main": "C3", "bugFix": "C3"},
                "main",
            ),
            solution_command="git rebase main; git checkout main; git merge bugFix",
            golf_target=2,
        ),
        # --------------------------------------------------------------- rampup
        Level(
            id="rampup-detached-1",
            sequence="rampup",
            name="Detached HEAD",
            hint="`git checkout C1` detaches HEAD at that commit.",
            lesson=(
                "HEAD is a pointer to your current location. On a branch it moves with commits. "
                "Detached, it points at a commit id — new commits do not update any branch."
            ),
            start_tree=_tree({"C0": [], "C1": ["C0"], "C2": ["C1"]}, {"main": "C2"}, "main"),
            goal_tree=_tree({"C0": [], "C1": ["C0"], "C2": ["C1"]}, {"main": "C2"}, "C1"),
            solution_command="git checkout C1",
            golf_target=1,
        ),
        Level(
            id="rampup-relative-1",
            sequence="rampup",
            name="Relative Refs (^)",
            hint="`git checkout main^` moves to the parent of main.",
            lesson=(
                "Instead of typing ids, walk the graph. `^` is parent; `~n` is n first-parent steps.\n\n"
                "Land on the parent of `main`."
            ),
            start_tree=_tree({"C0": [], "C1": ["C0"], "C2": ["C1"]}, {"main": "C2"}, "main"),
            goal_tree=_tree({"C0": [], "C1": ["C0"], "C2": ["C1"]}, {"main": "C2"}, "C1"),
            solution_command="git checkout main^",
            golf_target=1,
        ),
        Level(
            id="rampup-relative-2",
            sequence="rampup",
            name="Relative Refs #2",
            hint="Create `main` at the root with `git branch -f main C0` (or `main~2`).",
            lesson=(
                "`git branch -f main <rev>` force-moves a branch without checking it out. "
                "That is the fastest way to rearrange labels."
            ),
            start_tree=_tree({"C0": [], "C1": ["C0"], "C2": ["C1"]}, {"main": "C2"}, "main"),
            goal_tree=_tree({"C0": [], "C1": ["C0"], "C2": ["C1"]}, {"main": "C0"}, "main"),
            solution_command="git branch -f main C0",
            golf_target=1,
        ),
        Level(
            id="rampup-reversing-1",
            sequence="rampup",
            name="Reversing Changes with reset",
            hint="`git reset --hard HEAD^` moves the branch back one step.",
            lesson=(
                "`git reset --hard` rewinds the current branch to a commit. "
                "Local history is clean; anyone who already fetched still has the old commits.\n\n"
                "For undoing published work, use `git revert` instead — it adds a new commit."
            ),
            start_tree=_tree({"C0": [], "C1": ["C0"], "C2": ["C1"]}, {"main": "C2"}, "main"),
            goal_tree=_tree({"C0": [], "C1": ["C0"], "C2": ["C1"]}, {"main": "C1"}, "main"),
            solution_command="git reset --hard HEAD^",
            golf_target=1,
        ),
        Level(
            id="rampup-reversing-2",
            sequence="rampup",
            name="Reversing Changes with revert",
            hint="`git revert HEAD` adds a commit that undoes the tip.",
            lesson=(
                "Revert never deletes commits. It appends an inverse commit so remote history stays honest."
            ),
            start_tree=_tree({"C0": [], "C1": ["C0"], "C2": ["C1"]}, {"main": "C2"}, "main"),
            goal_tree=_tree(
                {"C0": [], "C1": ["C0"], "C2": ["C1"], "C3": ["C2"]},
                {"main": "C3"},
                "main",
            ),
            solution_command="git revert HEAD",
            golf_target=1,
        ),
        # ---------------------------------------------------------------- rebase
        Level(
            id="rebase-many-1",
            sequence="rebase",
            name="Rebasing over Diverging Work",
            hint="Stay on `main` and `git rebase bugFix` — or rebase bugFix onto main first.",
            lesson=(
                "Linearizing two lines of work is the bread-and-butter of rebase. "
                "Replay whichever branch should end up on top."
            ),
            start_tree=_tree(
                {"C0": [], "C1": ["C0"], "C2": ["C1"], "C3": ["C1"]},
                {"main": "C2", "bugFix": "C3"},
                "bugFix",
            ),
            goal_tree=_tree(
                {"C0": [], "C1": ["C0"], "C2": ["C1"], "C3": ["C2"]},
                {"main": "C2", "bugFix": "C3"},
                "bugFix",
            ),
            solution_command="git rebase main",
            golf_target=1,
        ),
        Level(
            id="rebase-onto-1",
            sequence="rebase",
            name="Rebase --onto",
            hint="`git rebase --onto main bugFix bugFix` or cherry-pick the one commit you need.",
            lesson=(
                "`git rebase --onto <newbase> <oldbase> [<branch>]` replays only the commits "
                "after `<oldbase>` onto `<newbase>`. Essential for surgical history edits."
            ),
            start_tree=_tree(
                {"C0": [], "C1": ["C0"], "C2": ["C1"], "C3": ["C2"], "C4": ["C1"]},
                {"main": "C4", "bugFix": "C3"},
                "main",
            ),
            goal_tree=_tree(
                {"C0": [], "C1": ["C0"], "C2": ["C1"], "C3": ["C2"], "C4": ["C1"], "C5": ["C4"]},
                {"main": "C5", "bugFix": "C3"},
                "main",
            ),
            solution_command="git cherry-pick C3",
            golf_target=1,
        ),
        Level(
            id="rebase-cherry-1",
            sequence="rebase",
            name="Cherry-Pick Commits",
            hint="`git cherry-pick C2 C4` (order matters).",
            lesson=(
                "Cherry-pick copies specific commits onto HEAD. Great for hotfixes "
                "and for grabbing one change out of a feature branch."
            ),
            start_tree=_tree(
                {
                    "C0": [],
                    "C1": ["C0"],
                    "C2": ["C1"],
                    "C3": ["C2"],
                    "C4": ["C3"],
                    "C5": ["C1"],
                },
                {"main": "C5", "bugFix": "C4"},
                "main",
            ),
            goal_tree=_tree(
                {
                    "C0": [],
                    "C1": ["C0"],
                    "C2": ["C1"],
                    "C3": ["C2"],
                    "C4": ["C3"],
                    "C5": ["C1"],
                    "C6": ["C5"],
                    "C7": ["C6"],
                },
                {"main": "C7", "bugFix": "C4"},
                "main",
            ),
            solution_command="git cherry-pick C2 C4",
            golf_target=2,
        ),
        # ---------------------------------------------------------------- remote
        Level(
            id="remote-clone-1",
            sequence="remote",
            name="Clone a Remote",
            hint="`git clone` creates origin and `o/main` remote-tracking branches.",
            lesson=(
                "A remote is another copy of the repository. `git clone` sets up `origin` "
                "and remote-tracking branches named `o/<branch>` in this simulator."
            ),
            start_tree=_tree({"C0": [], "C1": ["C0"]}, {"main": "C1"}, "main"),
            goal_tree=_tree(
                {"C0": [], "C1": ["C0"]},
                {"main": "C1"},
                "main",
                remote_branches={"o/main": "C1"},
            ),
            solution_command="git clone",
            golf_target=1,
        ),
        Level(
            id="remote-push-1",
            sequence="remote",
            name="Pushing Work",
            hint="`git push` publishes `main` to `o/main`.",
            lesson=(
                "Push updates the remote to match your local branch. "
                "Non-fast-forward pushes are rejected — fetch and integrate first."
            ),
            start_tree=_tree(
                {"C0": [], "C1": ["C0"], "C2": ["C1"]},
                {"main": "C2"},
                "main",
                remote_branches={"o/main": "C1"},
            ),
            goal_tree=_tree(
                {"C0": [], "C1": ["C0"], "C2": ["C1"]},
                {"main": "C2"},
                "main",
                remote_branches={"o/main": "C2"},
            ),
            solution_command="git push",
            golf_target=1,
        ),
        Level(
            id="remote-pull-1",
            sequence="remote",
            name="Pulling Work",
            hint="`git pull` fetches (here: already reflected) and merges `o/main` into `main`.",
            lesson=(
                "Pull = fetch + integrate. Default is a merge; `git pull --rebase` "
                "replays your commits on top of the remote for a linear story."
            ),
            start_tree=_tree(
                {"C0": [], "C1": ["C0"], "C2": ["C1"]},
                {"main": "C1"},
                "main",
                remote_branches={"o/main": "C2"},
            ),
            goal_tree=_tree(
                {"C0": [], "C1": ["C0"], "C2": ["C1"]},
                {"main": "C2"},
                "main",
                remote_branches={"o/main": "C2"},
            ),
            solution_command="git pull",
            golf_target=1,
        ),
        Level(
            id="remote-teamwork-1",
            sequence="remote",
            name="Teamwork Diverges",
            hint="`git fakeTeamwork main 1` then `git push` fails. Integrate with `git pull` and push.",
            lesson=(
                "When a teammate pushes first, your push is rejected. "
                "Fetch their work, rebase or merge, then push again."
            ),
            start_tree=_tree(
                {"C0": [], "C1": ["C0"], "C2": ["C1"]},
                {"main": "C2"},
                "main",
                remote_branches={"o/main": "C1"},
            ),
            goal_tree=_tree(
                {
                    "C0": [],
                    "C1": ["C0"],
                    "C2": ["C1"],
                    "C3": ["C1"],
                    "C4": ["C2", "C3"],
                },
                {"main": "C4"},
                "main",
                remote_branches={"o/main": "C4"},
            ),
            solution_command="git fakeTeamwork main 1; git pull; git push",
            golf_target=3,
        ),
        Level(
            id="remote-rebase-fetch-1",
            sequence="remote",
            name="Pull with Rebase",
            hint="`git pull --rebase` then `git push` after `git fakeTeamwork`.",
            lesson=(
                "Prefer linear remote history? Use `git pull --rebase`. "
                "Your local commits are replayed on top of `o/main`."
            ),
            start_tree=_tree(
                {"C0": [], "C1": ["C0"], "C2": ["C1"]},
                {"main": "C2"},
                "main",
                remote_branches={"o/main": "C1"},
            ),
            goal_tree=_tree(
                {
                    "C0": [],
                    "C1": ["C0"],
                    "C3": ["C1"],
                    "C4": ["C3"],
                },
                {"main": "C4"},
                "main",
                remote_branches={"o/main": "C4"},
            ),
            solution_command="git fakeTeamwork main 1; git pull --rebase; git push",
            golf_target=3,
        ),
    ]


LEVELS: list[Level] = _levels()
LEVELS_BY_ID: dict[str, Level] = {lv.id: lv for lv in LEVELS}


def levels_for_sequence(sequence: str) -> list[Level]:
    """Return levels belonging to one sequence.

    Args:
        sequence: Sequence key.

    Returns:
        Levels in order.
    """
    return [lv for lv in LEVELS if lv.sequence == sequence]


def next_level_id(level_id: str) -> str | None:
    """Return the id of the level after ``level_id``.

    Args:
        level_id: Current level id.

    Returns:
        Next level id or None at the end of the catalog.
    """
    ids = [lv.id for lv in LEVELS]
    if level_id not in ids:
        return None
    idx = ids.index(level_id)
    return ids[idx + 1] if idx + 1 < len(ids) else None
