"""Structural goal-tree comparison for level completion.

Goal matching ignores concrete commit ids. Two trees match when every named
ref points at a commit with the same ancestor shape (parent counts, order of
first-parent chain length, and merge fan-in). HEAD must also match the goal
when the goal specifies HEAD.
"""

from __future__ import annotations

from dataclasses import dataclass

from lgb.model import GitEngine


class GoalError(Exception):
    """Raised when a goal tree is malformed for comparison."""


@dataclass
class GoalReport:
    """Result of a goal comparison.

    Attributes:
        reached: Whether the player tree satisfies the goal.
        differences: Human-readable mismatch explanations.
    """

    reached: bool
    differences: list[str]


def _structural_key(engine: GitEngine, commit_id: str, cache: dict[str, tuple], depth: int = 0, limit: int = 6) -> tuple:
    """Compute a structural key for ``commit_id`` using engine parents.

    Args:
        engine: Engine containing the commit.
        commit_id: Commit id.
        cache: Memo dict.
        depth: Recursion depth.
        limit: Max depth.

    Returns:
        Hashable key.
    """
    if depth >= limit:
        commit = engine.commits[commit_id]
        return ("stump", len(commit.parents))
    if commit_id in cache:
        return cache[commit_id]
    commit = engine.commits[commit_id]
    parent_keys = tuple(
        _structural_key(engine, p, cache, depth + 1, limit) for p in commit.parents
    )
    key: tuple = ("c", commit.root_commit or not commit.parents, parent_keys)
    cache[commit_id] = key
    return key


def is_goal_reached(eng: GitEngine, goal: GitEngine) -> GoalReport:
    """Compare a player engine against a goal engine.

    Args:
        eng: Player engine.
        goal: Goal engine.

    Returns:
        GoalReport with reachability and mismatch notes.

    Raises:
        GoalError: If the goal has no commits (empty goal is invalid).
    """
    if not goal.commits:
        raise GoalError("goal tree has no commits")

    differences: list[str] = []
    goal_cache: dict[str, tuple] = {}
    player_cache: dict[str, tuple] = {}

    # Every goal branch / remote / tag must exist and structurally match.
    for name, ref in sorted(goal.branches.items()):
        if name not in eng.branches:
            differences.append(f"missing local branch '{name}'")
            continue
        gk = _structural_key(goal, ref.target, goal_cache)
        pk = _structural_key(eng, eng.branches[name].target, player_cache)
        if gk != pk:
            differences.append(f"branch '{name}' does not match goal shape")

    for name, ref in sorted(goal.remote_branches.items()):
        if name not in eng.remote_branches:
            differences.append(f"missing remote branch '{name}'")
            continue
        gk = _structural_key(goal, ref.target, goal_cache)
        pk = _structural_key(eng, eng.remote_branches[name].target, player_cache)
        if gk != pk:
            differences.append(f"remote branch '{name}' does not match goal shape")

    for name, ref in sorted(goal.tags.items()):
        if name not in eng.tags:
            differences.append(f"missing tag '{name}'")
            continue
        gk = _structural_key(goal, ref.target, goal_cache)
        pk = _structural_key(eng, eng.tags[name].target, player_cache)
        if gk != pk:
            differences.append(f"tag '{name}' does not match goal shape")

    # HEAD: if goal HEAD is attached, player must be on the same branch name.
    # If goal HEAD is detached, player HEAD commit must match the goal tip shape.
    if goal.head_detached:
        if not eng.head_detached:
            differences.append("goal expects detached HEAD")
        else:
            gk = _structural_key(goal, goal.head_target, goal_cache)
            pk = _structural_key(eng, eng.head_target, player_cache)
            if gk != pk:
                differences.append("detached HEAD commit does not match goal shape")
    else:
        if eng.head_detached:
            differences.append(f"goal expects HEAD -> {goal.head_target}")
        elif eng.head_target != goal.head_target:
            differences.append(f"HEAD should be on '{goal.head_target}', currently on '{eng.head_target}'")

    return GoalReport(reached=not differences, differences=differences)
