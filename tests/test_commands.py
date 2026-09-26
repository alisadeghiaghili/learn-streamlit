"""Tests for command parsing."""

from __future__ import annotations

import pytest

from lgb.commands import CommandError, execute_line, split_commands
from lgb.model import GitEngine


def test_split_commands() -> None:
    assert split_commands("git commit; git checkout main") == [
        "git commit",
        "git checkout main",
    ]
    assert split_commands("\n\ngit commit\n") == ["git commit"]


def test_unknown_command() -> None:
    eng = GitEngine.sandbox()
    with pytest.raises(CommandError):
        execute_line(eng, "foo bar")


def test_meta_help() -> None:
    eng = GitEngine.sandbox()
    result = execute_line(eng, "help")
    assert any("git commit" in m for m in result.messages)


def test_status_and_log() -> None:
    eng = GitEngine.sandbox()
    assert execute_line(eng, "status").messages
    assert execute_line(eng, "log").messages
