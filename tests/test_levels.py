"""Tests for goal-tree comparison and level solutions."""

from __future__ import annotations

from lgb.commands import execute_line
from lgb.goal import is_goal_reached
from lgb.levels import LEVELS


def _run_solution(start_tree: str, solution: str):
    from lgb.tree_io import load_tree

    eng = load_tree(start_tree)
    execute_line(eng, solution)
    return eng


def test_all_official_solutions_reach_goal() -> None:
    failures = []
    for level in LEVELS:
        eng = _run_solution(level.start_tree, level.solution_command)
        report = is_goal_reached(eng, level.goal_engine())
        if not report.reached:
            failures.append(f"{level.id}: {report.differences}")
    assert not failures, "\n".join(failures)


def test_unsolved_level_is_not_goal() -> None:
    level = next(lv for lv in LEVELS if lv.id == "intro-commits-1")
    eng = level.start_engine()
    report = is_goal_reached(eng, level.goal_engine())
    assert not report.reached


def test_solved_level_reports_success() -> None:
    level = next(lv for lv in LEVELS if lv.id == "intro-commits-1")
    eng = level.start_engine()
    execute_line(eng, "git commit; git commit")
    report = is_goal_reached(eng, level.goal_engine())
    assert report.reached
