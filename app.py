"""Learn Git Branching — Streamlit app.

An interactive git visualizer, sandbox, and level-based tutorial inspired by
https://github.com/pcottle/learnGitBranching
"""

from __future__ import annotations

import json
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from lgb.commands import CommandError, CommandResult, execute_line, help_lines
from lgb.goal import GoalError, is_goal_reached
from lgb.levels import (
    LEVELS,
    LEVELS_BY_ID,
    SEQUENCE_BLURBS,
    SEQUENCE_TITLES,
    next_level_id,
)
from lgb.model import GitEngine, GitError
from lgb.viz import PALETTE, render_graph_svg

st.set_page_config(
    page_title="Learn Git Branching",
    page_icon=":material/account_tree:",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = f"""
<style>
    .stApp {{
        background: {PALETTE['bg']};
    }}
    header[data-testid="stHeader"] {{
        background: rgba(14, 17, 23, 0.9);
    }}
    .block-container {{
        padding-top: 1.2rem;
        padding-bottom: 2rem;
        max-width: 1200px;
    }}
    .lgb-title {{
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        letter-spacing: 0.04em;
        color: {PALETTE['ink']};
    }}
    .lgb-terminal {{
        background: {PALETTE['surface']};
        border: 1px solid {PALETTE['edge']};
        border-radius: 12px;
        padding: 0.85rem 1rem;
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        font-size: 13px;
        color: {PALETTE['ink']};
        white-space: pre-wrap;
        min-height: 140px;
        max-height: 260px;
        overflow-y: auto;
    }}
    .lgb-meta {{
        color: {PALETTE['muted']};
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        font-size: 12px;
    }}
    .lgb-win {{
        background: rgba(63, 185, 80, 0.12);
        border: 1px solid {PALETTE['commit']};
        color: {PALETTE['commit']};
        border-radius: 10px;
        padding: 0.75rem 1rem;
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    .lgb-lesson {{
        background: {PALETTE['surface']};
        border-left: 3px solid {PALETTE['branch']};
        border-radius: 0 10px 10px 0;
        padding: 0.85rem 1rem;
        color: {PALETTE['ink']};
        font-size: 14px;
        line-height: 1.5;
    }}
    div[data-testid="stSidebar"] {{
        background: {PALETTE['surface']};
    }}
</style>
"""


def _init_state() -> None:
    """Initialize Streamlit session state defaults."""
    if "mode" not in st.session_state:
        st.session_state.mode = "sandbox"  # sandbox | levels | catalog
    if "engine" not in st.session_state:
        st.session_state.engine = GitEngine.sandbox()
    if "undo_stack" not in st.session_state:
        st.session_state.undo_stack: list[GitEngine] = []
    if "terminal" not in st.session_state:
        st.session_state.terminal: list[str] = [
            "Learn Git Branching (Streamlit clone)",
            "Type `help` for commands, `levels` for challenges.",
            "",
        ]
    if "command_count" not in st.session_state:
        st.session_state.command_count = 0
    if "current_level_id" not in st.session_state:
        st.session_state.current_level_id = LEVELS[0].id
    if "solved" not in st.session_state:
        st.session_state.solved = False
    if "best_scores" not in st.session_state:
        st.session_state.best_scores: dict[str, int] = {}
    if "show_solution" not in st.session_state:
        st.session_state.show_solution = False
    if "goal_visible" not in st.session_state:
        st.session_state.goal_visible = True


def _log(*lines: str) -> None:
    """Append lines to the terminal buffer.

    Args:
        *lines: Lines to append.
    """
    st.session_state.terminal.extend(lines)


def _push_undo() -> None:
    """Snapshot the engine before a mutating command."""
    st.session_state.undo_stack.append(st.session_state.engine.snapshot())
    if len(st.session_state.undo_stack) > 40:
        st.session_state.undo_stack.pop(0)


def _do_undo() -> None:
    """Restore the most recent snapshot."""
    if not st.session_state.undo_stack:
        _log("nothing to undo")
        return
    snap = st.session_state.undo_stack.pop()
    st.session_state.engine.restore(snap)
    st.session_state.command_count = max(0, st.session_state.command_count - 1)
    st.session_state.solved = False
    _log("undid last command")


def _reset_current() -> None:
    """Reset sandbox or the active level to its start state."""
    if st.session_state.mode == "levels":
        level = LEVELS_BY_ID[st.session_state.current_level_id]
        st.session_state.engine = level.start_engine()
        _log(f"reset level '{level.name}'")
    else:
        st.session_state.engine = GitEngine.sandbox()
        _log("reset sandbox")
    st.session_state.undo_stack.clear()
    st.session_state.command_count = 0
    st.session_state.solved = False
    st.session_state.show_solution = False


def _load_level(level_id: str) -> None:
    """Switch into level mode and load a level.

    Args:
        level_id: Level slug.
    """
    level = LEVELS_BY_ID[level_id]
    st.session_state.mode = "levels"
    st.session_state.current_level_id = level_id
    st.session_state.engine = level.start_engine()
    st.session_state.undo_stack.clear()
    st.session_state.command_count = 0
    st.session_state.solved = False
    st.session_state.show_solution = False
    _log(f"--- level: {level.name} ---")
    _log(level.hint)


def _check_goal() -> None:
    """Compare the engine against the active level goal and celebrate wins."""
    if st.session_state.mode != "levels":
        return
    level = LEVELS_BY_ID[st.session_state.current_level_id]
    try:
        report = is_goal_reached(st.session_state.engine, level.goal_engine())
    except GoalError as exc:
        _log(f"goal error: {exc}")
        return
    if report.reached:
        if not st.session_state.solved:
            st.session_state.solved = True
            count = st.session_state.command_count
            best = st.session_state.best_scores.get(level.id)
            if best is None or count < best:
                st.session_state.best_scores[level.id] = count
            _log("")
            _log("*** LEVEL COMPLETE ***")
            _log(f"commands used: {count}  (golf target: {level.golf_target})")
            if count <= level.golf_target:
                _log("perfect score — matched the git golf target!")
            _log("")
    else:
        st.session_state.solved = False


def _run_command(line: str) -> None:
    """Execute one user line and update state.

    Args:
        line: Raw input from the command box.
    """
    line = line.strip()
    if not line:
        return
    _log(f"$ {line}")
    eng: GitEngine = st.session_state.engine
    history: list[str] = []
    before = eng.snapshot()
    try:
        result: CommandResult = execute_line(eng, line, history=history)
    except (CommandError, GitError) as exc:
        st.session_state.engine = before
        _log(f"error: {exc}")
        return

    if result.undone:
        _do_undo()
        return
    if result.reset_level:
        _reset_current()
        return
    if result.show_levels:
        st.session_state.mode = "catalog"
        _log("opening level catalog")
        return
    if result.show_solution:
        st.session_state.show_solution = True
        level = LEVELS_BY_ID.get(st.session_state.current_level_id)
        if level and st.session_state.mode == "levels":
            _log(f"solution: {level.solution_command}")
        else:
            _log("no active level — open `levels` first")
        return

    st.session_state.undo_stack.append(before)
    if len(st.session_state.undo_stack) > 40:
        st.session_state.undo_stack.pop(0)
    st.session_state.command_count += max(1, len(history) or 1)
    for msg in result.messages:
        _log(msg)
    _check_goal()


def _goal_svg() -> str:
    """Render the goal tree SVG for the sidebar.

    Returns:
        SVG string or empty placeholder.
    """
    if st.session_state.mode != "levels":
        return ""
    level = LEVELS_BY_ID[st.session_state.current_level_id]
    try:
        return render_graph_svg(level.goal_engine(), width=360, col_gap=64, row_gap=44, node_r=13)
    except Exception:
        return ""


def _catalog_view() -> None:
    """Render the level catalog page."""
    st.markdown("## Levels")
    st.caption("Pick a sequence, then a challenge. Your best command count is saved per session (git golf).")
    by_seq: dict[str, list[Any]] = {}
    for lv in LEVELS:
        by_seq.setdefault(lv.sequence, []).append(lv)

    for seq, items in by_seq.items():
        st.markdown(f"### {SEQUENCE_TITLES.get(seq, seq)}")
        st.caption(SEQUENCE_BLURBS.get(seq, ""))
        for lv in items:
            best = st.session_state.best_scores.get(lv.id)
            badge = "solved" if best is not None else "new"
            cols = st.columns([4, 2, 1, 1])
            cols[0].markdown(f"**{lv.name}**  \n{lv.hint}")
            cols[1].markdown(
                f"<span class='lgb-meta'>golf target: {lv.golf_target} · {badge}"
                + (f" · best: {best}" if best is not None else "")
                + "</span>",
                unsafe_allow_html=True,
            )
            if cols[2].button("Play", key=f"play-{lv.id}"):
                _load_level(lv.id)
                st.rerun()
            if cols[3].button("Peek", key=f"peek-{lv.id}"):
                _log(f"[{lv.name}] solution: {lv.solution_command}")


def _sidebar() -> None:
    """Render the sidebar: mode switch, goal, level copy, progress."""
    st.markdown("### Learn Git Branching")
    st.caption("Streamlit clone of pcottle/learnGitBranching")

    mode = st.radio(
        "Mode",
        ["Sandbox", "Levels", "Catalog"],
        index={"sandbox": 0, "levels": 1, "catalog": 2}[st.session_state.mode],
        horizontal=True,
    )
    new_mode = {"Sandbox": "sandbox", "Levels": "levels", "Catalog": "catalog"}[mode]
    if new_mode != st.session_state.mode:
        st.session_state.mode = new_mode
        if new_mode == "sandbox":
            st.session_state.engine = GitEngine.sandbox()
            st.session_state.undo_stack.clear()
            st.session_state.command_count = 0
            st.session_state.solved = False
            _log("--- sandbox ---")
        elif new_mode == "catalog":
            _log("--- catalog ---")
        elif new_mode == "levels":
            _load_level(st.session_state.current_level_id)
        st.rerun()

    st.markdown("---")

    if st.session_state.mode == "levels":
        level = LEVELS_BY_ID[st.session_state.current_level_id]
        st.markdown(f"**{level.name}**")
        st.markdown(f"<div class='lgb-lesson'>{level.lesson}</div>", unsafe_allow_html=True)
        st.markdown("**Hint**")
        st.write(level.hint)
        st.markdown("**Git golf**")
        st.write(
            f"Target: `{level.golf_target}` commands · You: `{st.session_state.command_count}`"
        )
        cols = st.columns(2)
        if cols[0].button("Reset level"):
            _reset_current()
            st.rerun()
        if cols[1].button("Show solution"):
            st.session_state.show_solution = True
            _log(f"solution: {level.solution_command}")

        if st.session_state.show_solution:
            st.code(level.solution_command, language="bash")

        st.markdown("**Goal tree**")
        goal_markup = _goal_svg()
        if goal_markup:
            components.html(goal_markup, height=220, scrolling=False)
        if st.session_state.solved:
            st.markdown(
                "<div class='lgb-win'>Level complete. Nice work.</div>",
                unsafe_allow_html=True,
            )
            nxt = next_level_id(level.id)
            if nxt and st.button("Next level"):
                _load_level(nxt)
                st.rerun()
            if st.button("Back to catalog"):
                st.session_state.mode = "catalog"
                st.rerun()

    solved_count = len(st.session_state.best_scores)
    st.markdown("---")
    st.markdown("**Progress**")
    st.write(f"{solved_count} / {len(LEVELS)} levels solved")
    st.markdown("**Commands this run**")
    st.write(str(st.session_state.command_count))


def _main_header() -> None:
    """Render the title row."""
    st.markdown(
        "<h1 class='lgb-title'>learn git branching</h1>"
        "<p class='lgb-meta'>visualize · sandbox · levels</p>",
        unsafe_allow_html=True,
    )


def _graph_area() -> None:
    """Render the live commit graph."""
    st.markdown("**Commit tree**")
    svg = render_graph_svg(st.session_state.engine)
    components.html(svg, height=360, scrolling=False)


def _terminal_area() -> None:
    """Render terminal output and the command input."""
    st.markdown("**Terminal**")
    text = "\n".join(st.session_state.terminal[-80:])
    st.markdown(f"<div class='lgb-terminal'>{text}</div>", unsafe_allow_html=True)

    with st.form("command-form", clear_on_submit=True):
        cols = st.columns([6, 1, 1, 1])
        raw = cols[0].text_input(
            "command",
            placeholder="git commit; git checkout -b bugFix",
            label_visibility="collapsed",
            key="command_input",
        )
        submitted = cols[1].form_submit_button("Run")
        if cols[2].form_submit_button("Undo"):
            _push_undo()
            _do_undo()
            st.rerun()
        if cols[3].form_submit_button("Reset"):
            _reset_current()
            st.rerun()
        if submitted and raw:
            _run_command(raw)
            st.rerun()

    with st.expander("Command cheatsheet"):
        st.code("\n".join(help_lines()), language="text")


def main() -> None:
    """Streamlit entrypoint."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    _init_state()
    _sidebar()
    _main_header()

    if st.session_state.mode == "catalog":
        _catalog_view()
    else:
        if st.session_state.mode == "levels":
            level = LEVELS_BY_ID[st.session_state.current_level_id]
            st.info(f"Level: **{level.name}** — {level.hint}")
        _graph_area()
        _terminal_area()

    with st.expander("Raw tree JSON (debug)"):
        from lgb.tree_io import dump_tree

        st.code(dump_tree(st.session_state.engine), language="json")


if __name__ == "__main__":
    main()
