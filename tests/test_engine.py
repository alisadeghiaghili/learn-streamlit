"""Tests for the simulated git engine."""

from __future__ import annotations

import pytest

from lgb.model import GitError, GitEngine


def test_sandbox_default() -> None:
    eng = GitEngine.sandbox()
    assert set(eng.commits) == {"C0", "C1"}
    assert eng.branches["main"].target == "C1"
    assert eng.head_commit_id() == "C1"
    assert eng.head_detached is False


def test_commit_on_branch_moves_tip() -> None:
    eng = GitEngine.sandbox()
    from lgb.commands import execute_one

    execute_one(eng, "git commit")
    assert eng.branches["main"].target == "C2"
    assert eng.commits["C2"].parents == ["C1"]
    assert eng.head_commit_id() == "C2"


def test_checkout_branch_and_detach() -> None:
    eng = GitEngine.sandbox()
    from lgb.commands import execute_one

    execute_one(eng, "git checkout -b bugFix")
    execute_one(eng, "git commit")
    execute_one(eng, "git checkout main")
    assert eng.head_target == "main"
    execute_one(eng, "git checkout C0")
    assert eng.head_detached is True
    assert eng.head_commit_id() == "C0"


def test_resolve_relative_refs() -> None:
    eng = GitEngine.sandbox()
    assert eng.resolve_commit("main") == "C1"
    assert eng.resolve_commit("main^") == "C0"
    assert eng.resolve_commit("main~1") == "C0"
    assert eng.resolve_commit("HEAD") == "C1"
    with pytest.raises(GitError):
        eng.resolve_commit("nope")


def test_merge_fast_forward() -> None:
    eng = GitEngine.sandbox()
    from lgb.commands import execute_one

    execute_one(eng, "git checkout -b bugFix")
    execute_one(eng, "git commit")
    execute_one(eng, "git checkout main")
    execute_one(eng, "git merge bugFix")
    assert eng.branches["main"].target == eng.branches["bugFix"].target


def test_merge_creates_two_parents() -> None:
    eng = GitEngine.sandbox()
    from lgb.commands import execute_one

    execute_one(eng, "git checkout -b bugFix")
    execute_one(eng, "git commit")
    execute_one(eng, "git checkout main")
    execute_one(eng, "git commit")
    execute_one(eng, "git merge bugFix")
    tip = eng.branches["main"].target
    assert len(eng.commits[tip].parents) == 2


def test_rebase_linearizes() -> None:
    eng = GitEngine.sandbox()
    from lgb.commands import execute_one

    execute_one(eng, "git checkout -b bugFix")
    execute_one(eng, "git commit")
    execute_one(eng, "git checkout main")
    execute_one(eng, "git commit")
    execute_one(eng, "git checkout bugFix")
    execute_one(eng, "git rebase main")
    tip = eng.branches["bugFix"].target
    assert len(eng.commits[tip].parents) == 1
    assert eng.is_ancestor(eng.branches["main"].target, tip)


def test_reset_hard_moves_branch() -> None:
    eng = GitEngine.sandbox()
    from lgb.commands import execute_one

    execute_one(eng, "git commit")
    execute_one(eng, "git reset --hard HEAD^")
    assert eng.branches["main"].target == "C1"


def test_revert_adds_commit() -> None:
    eng = GitEngine.sandbox()
    from lgb.commands import execute_one

    execute_one(eng, "git revert HEAD")
    assert eng.branches["main"].target.startswith("C")
    tip = eng.branches["main"].target
    assert tip != "C1"
    assert "Revert" in eng.commits[tip].message


def test_cherry_pick_copies() -> None:
    eng = GitEngine.sandbox()
    from lgb.commands import execute_one

    execute_one(eng, "git checkout -b side")
    execute_one(eng, "git commit")
    side_tip = eng.branches["side"].target
    execute_one(eng, "git checkout main")
    execute_one(eng, f"git cherry-pick {side_tip}")
    main_tip = eng.branches["main"].target
    assert main_tip != side_tip
    assert eng.commits[main_tip].parents == ["C1"]


def test_remote_clone_push_pull() -> None:
    eng = GitEngine.sandbox()
    from lgb.commands import execute_one

    execute_one(eng, "git clone")
    assert "o/main" in eng.remote_branches
    execute_one(eng, "git commit")
    execute_one(eng, "git push")
    assert eng.remote_branches["o/main"].target == eng.branches["main"].target


def test_branch_force_and_delete() -> None:
    eng = GitEngine.sandbox()
    from lgb.commands import execute_one

    execute_one(eng, "git branch other")
    execute_one(eng, "git branch -f other C0")
    assert eng.branches["other"].target == "C0"
    execute_one(eng, "git checkout main")
    execute_one(eng, "git branch -d other")
    assert "other" not in eng.branches
