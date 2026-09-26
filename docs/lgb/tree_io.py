"""Serialize and parse LearnGitBranching-compatible tree JSON.

Tree shape (as used by current LGB level modules)::

    {
      "commits": {"C0": {"parents": [], "id": "C0", "rootCommit": true}, ...},
      "branches": {"main": {"target": "C1", "id": "main"}},
      "remoteBranches": {"o/main": {"target": "C1", "id": "o/main"}},
      "tags": {"v1": {"target": "C1", "id": "v1"}},
      "HEAD": {"target": "main", "id": "HEAD"}
    }

``HEAD.target`` is a branch name when attached and a commit id when detached.
"""

from __future__ import annotations

import json
from typing import Any

from lgb.model import Commit, GitEngine, Ref


class TreeFormatError(ValueError):
    """Raised when a tree JSON document is malformed."""


def load_tree(source: str | dict[str, Any]) -> GitEngine:
    """Load an engine from LGB tree JSON.

    Args:
        source: JSON string or already-parsed mapping.

    Returns:
        Populated GitEngine.

    Raises:
        TreeFormatError: If required keys are missing or types are wrong.
    """
    if isinstance(source, str):
        try:
            data = json.loads(source)
        except json.JSONDecodeError as exc:
            raise TreeFormatError(f"invalid tree JSON: {exc}") from exc
    else:
        data = source

    if not isinstance(data, dict):
        raise TreeFormatError("tree must be a JSON object")

    eng = GitEngine.empty()
    commits_raw = data.get("commits", {})
    if not isinstance(commits_raw, dict):
        raise TreeFormatError("commits must be an object")
    for cid, cdata in commits_raw.items():
        if not isinstance(cdata, dict):
            raise TreeFormatError(f"commit '{cid}' must be an object")
        payload = dict(cdata)
        payload.setdefault("id", cid)
        try:
            eng.commits[str(cid)] = Commit.from_dict(payload)
        except ValueError as exc:
            raise TreeFormatError(str(exc)) from exc

    for key, dest, kind in (
        ("branches", eng.branches, "branch"),
        ("remoteBranches", eng.remote_branches, "remote"),
        ("tags", eng.tags, "tag"),
    ):
        refs_raw = data.get(key, {})
        if not isinstance(refs_raw, dict):
            raise TreeFormatError(f"{key} must be an object")
        for name, rdata in refs_raw.items():
            if not isinstance(rdata, dict):
                raise TreeFormatError(f"{key} entry '{name}' must be an object")
            payload = dict(rdata)
            payload.setdefault("id", name)
            dest[str(name)] = Ref.from_dict(payload, kind=kind)

    head_raw = data.get("HEAD", {})
    if not isinstance(head_raw, dict) or "target" not in head_raw:
        raise TreeFormatError("HEAD must be an object with a target")
    head_target = str(head_raw["target"])
    if head_target in eng.branches:
        eng.head_target = head_target
        eng.head_detached = False
    else:
        if head_target not in eng.commits:
            raise TreeFormatError(f"HEAD target '{head_target}' is not a branch or commit")
        eng.head_target = head_target
        eng.head_detached = True

    if eng.remote_branches or data.get("remote") or data.get("remoteUrl"):
        eng.remote_exists = True
        eng.remote_url = str(data.get("remoteUrl") or data.get("remote") or "origin")

    max_id = 0
    for cid in eng.commits:
        if cid.startswith("C") and cid[1:].isdigit():
            max_id = max(max_id, int(cid[1:]))
    eng.next_id = max_id + 1

    for commit in eng.commits.values():
        for parent in commit.parents:
            if parent not in eng.commits:
                raise TreeFormatError(f"commit '{commit.id}' references unknown parent '{parent}'")

    return eng


def dump_tree(eng: GitEngine) -> str:
    """Serialize an engine to LGB tree JSON.

    Args:
        eng: Engine to dump.

    Returns:
        Compact JSON string.
    """
    return json.dumps(tree_dict(eng), separators=(",", ":"))


def tree_dict(eng: GitEngine) -> dict[str, Any]:
    """Build an LGB-shaped mapping for an engine.

    Args:
        eng: Engine to dump.

    Returns:
        Mapping with commits / branches / remoteBranches / tags / HEAD.
    """
    head_target = eng.head_target
    return {
        "commits": {cid: c.to_dict() for cid, c in eng.commits.items()},
        "branches": {n: r.to_dict() for n, r in eng.branches.items()},
        "remoteBranches": {n: r.to_dict() for n, r in eng.remote_branches.items()},
        "tags": {n: r.to_dict() for n, r in eng.tags.items()},
        "HEAD": {"id": "HEAD", "target": head_target},
    }
