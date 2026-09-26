"""Extract English level metadata from downloaded LearnGitBranching level JS modules.

Reads ``ref/*.js`` (raw GitHub downloads of LGB level files) and prints a compact
summary: name, hint, startTree, goalTreeString, solutionCommand.

Args:
    None

Returns:
    None

Raises:
    FileNotFoundError: If ``ref/`` is missing or empty.

Examples:
    python scripts/extract_levels.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _unescape_js_string(raw: str) -> str:
    """Decode a JSON-escaped JS string body.

    Args:
        raw: Escaped string body without surrounding quotes.

    Returns:
        Decoded Python string.
    """
    return json.loads(f'"{raw}"')


def _first_en(text: str, key: str) -> str:
    """Return the first ``en_US`` value nested under ``key``.

    Args:
        text: Full JS module text.
        key: Object key such as ``name`` or ``hint``.

    Returns:
        English string or empty string.
    """
    pattern = rf'"{key}"\s*:\s*\{{[^}}]*?"en_US"\s*:\s*"((?:\\.|[^"\\])*)"'
    match = re.search(pattern, text, flags=re.DOTALL)
    return _unescape_js_string(match.group(1)) if match else ""


def _all_string_fields(text: str, key: str) -> list[str]:
    """Collect every JSON-escaped string assigned to ``key``.

    Args:
        text: Full JS module text.
        key: Field name.

    Returns:
        Decoded values in source order.
    """
    pattern = rf'"{key}"\s*:\s*"((?:\\.|[^"\\])*)"'
    return [_unescape_js_string(m) for m in re.findall(pattern, text)]


def extract_file(path: Path) -> list[dict[str, Any]]:
    """Extract level-like records from one JS file.

    Args:
        path: Path to a level module.

    Returns:
        List of dicts with name/hint/start/goal/solution fields.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    goals = _all_string_fields(text, "goalTreeString")
    starts = _all_string_fields(text, "startTree")
    sols = _all_string_fields(text, "solutionCommand")
    names = [
        _unescape_js_string(m)
        for m in re.findall(r'"name"\s*:\s*\{[^}]*?"en_US"\s*:\s*"((?:\\.|[^"\\])*)"', text, flags=re.DOTALL)
    ]
    hints = [
        _unescape_js_string(m)
        for m in re.findall(r'"hint"\s*:\s*\{[^}]*?"en_US"\s*:\s*"((?:\\.|[^"\\])*)"', text, flags=re.DOTALL)
    ]
    records: list[dict[str, Any]] = []
    for i, goal in enumerate(goals):
        records.append(
            {
                "file": path.name,
                "index": i,
                "name": names[i] if i < len(names) else "",
                "hint": hints[i] if i < len(hints) else "",
                "startTree": starts[i] if i < len(starts) else "",
                "goalTreeString": goal,
                "solutionCommand": sols[i] if i < len(sols) else "",
            }
        )
    return records


def main() -> None:
    """Print extracted level records for every file under ``ref/``."""
    root = Path(__file__).resolve().parents[1] / "ref"
    if not root.is_dir():
        raise FileNotFoundError(f"missing reference directory: {root}")
    for path in sorted(root.glob("*.js")):
        for rec in extract_file(path):
            print("=" * 72)
            print(json.dumps(rec, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
