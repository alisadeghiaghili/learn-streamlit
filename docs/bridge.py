"""Browser-side session bridge for the static GitHub Pages build.

Loaded inside Pyodide. Exposes a small imperative API used by app.js.
"""

from __future__ import annotations

from lgb.commands import CommandError, execute_line, help_lines, split_commands
from lgb.goal import is_goal_reached
from lgb.levels import LEVELS, LEVELS_BY_ID, SEQUENCE_BLURBS, SEQUENCE_TITLES, next_level_id
from lgb.model import GitEngine, GitError
from lgb.tree_io import dump_tree, load_tree
from lgb.viz import render_graph_svg


class Session:
    """UI session state for the static app."""

    def __init__(self) -> None:
        self.engine: GitEngine = GitEngine.sandbox()
        self.undo_stack: list[GitEngine] = []
        self.mode: str = "sandbox"
        self.level_id: str = LEVELS[0].id
        self.command_count: int = 0
        self.solved: bool = False
        self.show_solution: bool = False
        self.terminal: list[str] = [
            "Learn Git Branching",
            "Type `help` for commands, `levels` for challenges.",
            "",
        ]
        self.best_scores: dict[str, int] = {}

    def log(self, *lines: str) -> None:
        self.terminal.extend(lines)

    def push_undo(self) -> None:
        self.undo_stack.append(self.engine.snapshot())
        if len(self.undo_stack) > 40:
            self.undo_stack.pop(0)

    def undo(self) -> str:
        if not self.undo_stack:
            self.log("nothing to undo")
            return self.terminal_text()
        self.engine.restore(self.undo_stack.pop())
        self.command_count = max(0, self.command_count - 1)
        self.solved = False
        self.log("undid last command")
        return self.terminal_text()

    def reset(self) -> str:
        if self.mode == "levels":
            level = LEVELS_BY_ID[self.level_id]
            self.engine = level.start_engine()
            self.log(f"reset level '{level.name}'")
        else:
            self.engine = GitEngine.sandbox()
            self.log("reset sandbox")
        self.undo_stack.clear()
        self.command_count = 0
        self.solved = False
        self.show_solution = False
        return self.terminal_text()

    def load_level(self, level_id: str) -> str:
        level = LEVELS_BY_ID[level_id]
        self.mode = "levels"
        self.level_id = level_id
        self.engine = level.start_engine()
        self.undo_stack.clear()
        self.command_count = 0
        self.solved = False
        self.show_solution = False
        self.log(f"--- level: {level.name} ---")
        self.log(level.hint)
        return self.terminal_text()

    def set_mode(self, mode: str) -> str:
        if mode == "sandbox":
            self.mode = "sandbox"
            self.engine = GitEngine.sandbox()
            self.undo_stack.clear()
            self.command_count = 0
            self.solved = False
            self.log("--- sandbox ---")
        elif mode == "catalog":
            self.mode = "catalog"
            self.log("--- catalog ---")
        elif mode == "levels":
            return self.load_level(self.level_id)
        return self.terminal_text()

    def terminal_text(self) -> str:
        return "\n".join(self.terminal[-120:])

    def graph_svg(self) -> str:
        return render_graph_svg(self.engine)

    def goal_svg(self) -> str:
        if self.mode != "levels":
            return ""
        return render_graph_svg(
            LEVELS_BY_ID[self.level_id].goal_engine(),
            width=420,
            col_gap=64,
            row_gap=44,
            node_r=13,
        )

    def check_goal(self) -> None:
        if self.mode != "levels":
            return
        level = LEVELS_BY_ID[self.level_id]
        report = is_goal_reached(self.engine, level.goal_engine())
        if report.reached:
            if not self.solved:
                self.solved = True
                best = self.best_scores.get(level.id)
                if best is None or self.command_count < best:
                    self.best_scores[level.id] = self.command_count
                self.log("")
                self.log("*** LEVEL COMPLETE ***")
                self.log(
                    f"commands used: {self.command_count}  (golf target: {level.golf_target})"
                )
                if self.command_count <= level.golf_target:
                    self.log("perfect score — matched the git golf target!")
                self.log("")
        else:
            self.solved = False

    def run(self, line: str) -> str:
        line = line.strip()
        if not line:
            return self.terminal_text()
        self.log(f"$ {line}")
        before = self.engine.snapshot()
        try:
            result = execute_line(self.engine, line)
        except (CommandError, GitError) as exc:
            self.engine = before
            self.log(f"error: {exc}")
            return self.terminal_text()

        if result.undone:
            return self.undo()
        if result.reset_level:
            return self.reset()
        if result.show_levels:
            self.mode = "catalog"
            self.log("opening levels")
            return self.terminal_text()
        if result.show_solution:
            self.show_solution = True
            if self.mode == "levels":
                self.log(f"solution: {LEVELS_BY_ID[self.level_id].solution_command}")
            else:
                self.log("no active level — open levels first")
            return self.terminal_text()

        self.undo_stack.append(before)
        if len(self.undo_stack) > 40:
            self.undo_stack.pop(0)
        self.command_count += max(1, len(split_commands(line)))
        for msg in result.messages:
            self.log(msg)
        self.check_goal()
        return self.terminal_text()

    def status_json(self) -> str:
        import json

        level = LEVELS_BY_ID[self.level_id] if self.mode == "levels" else None
        payload = {
            "mode": self.mode,
            "level_id": self.level_id,
            "command_count": self.command_count,
            "solved": self.solved,
            "show_solution": self.show_solution,
            "tree": dump_tree(self.engine),
            "goal_tree": dump_tree(level.goal_engine()) if level else "",
            "solution": level.solution_command if level else "",
            "hint": level.hint if level else "",
            "name": level.name if level else "Sandbox",
            "lesson": level.lesson if level else "Free-play sandbox. Try `help`.",
            "golf_target": level.golf_target if level else 0,
            "best": self.best_scores.get(self.level_id) if level else None,
            "next_level": next_level_id(self.level_id) if level else None,
            "solved_count": len(self.best_scores),
            "level_count": len(LEVELS),
        }
        return json.dumps(payload)

    def catalog_json(self) -> str:
        import json

        items = []
        for lv in LEVELS:
            items.append(
                {
                    "id": lv.id,
                    "sequence": lv.sequence,
                    "sequence_title": SEQUENCE_TITLES.get(lv.sequence, lv.sequence),
                    "sequence_blurb": SEQUENCE_BLURBS.get(lv.sequence, ""),
                    "name": lv.name,
                    "hint": lv.hint,
                    "golf_target": lv.golf_target,
                    "best": self.best_scores.get(lv.id),
                    "solved": lv.id in self.best_scores,
                }
            )
        return json.dumps(items)

    def help_text(self) -> str:
        return "\n".join(help_lines())

    def reveal_solution(self) -> str:
        """Show the official solution line in the terminal."""
        self.show_solution = True
        if self.mode == "levels":
            self.log(f"solution: {LEVELS_BY_ID[self.level_id].solution_command}")
        else:
            self.log("no active level — open levels first")
        return self.terminal_text()


session = Session()
