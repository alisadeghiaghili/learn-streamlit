"""SVG commit-graph rendering for the Streamlit UI.

Layout: time flows left → right (older commits on the left). Branch lanes
stack vertically. Refs render as pills to the right of their tip commit.
HEAD is a yellow pill attached to the current commit or branch tip.
"""

from __future__ import annotations

import html
from dataclasses import dataclass

from lgb.model import GitEngine

PALETTE = {
    "bg": "#0E1117",
    "surface": "#161B22",
    "ink": "#E6EDF3",
    "muted": "#8B949E",
    "edge": "#30363D",
    "commit": "#3FB950",
    "commit_merge": "#A371F7",
    "branch": "#58A6FF",
    "remote": "#F0883E",
    "tag": "#E3B341",
    "head": "#E3B341",
    "error": "#F85149",
}


@dataclass
class _Node:
    """Computed drawing position for one commit."""

    commit_id: str
    x: int
    y: int


def _topo_order(eng: GitEngine) -> list[str]:
    """Return commit ids, oldest first.

    Args:
        eng: Engine to layout.

    Returns:
        Commit ids in a left-to-right drawing order.
    """
    indeg = {cid: 0 for cid in eng.commits}
    for commit in eng.commits.values():
        for _parent in commit.parents:
            # edge parent -> child for topo
            pass
    children: dict[str, list[str]] = {cid: [] for cid in eng.commits}
    for commit in eng.commits.values():
        for parent in commit.parents:
            if parent in children:
                children[parent].append(commit.id)
                indeg[commit.id] = indeg.get(commit.id, 0) + 1

    # Kahn on parent-before-child edges
    ready = sorted([cid for cid, d in indeg.items() if d == 0])
    order: list[str] = []
    seen: set[str] = set()
    while ready:
        current = ready.pop(0)
        if current in seen:
            continue
        seen.add(current)
        order.append(current)
        for child in children[current]:
            indeg[child] -= 1
            if indeg[child] <= 0:
                ready.append(child)
        ready.sort()
    # Append any leftovers (cycles shouldn't exist).
    for cid in sorted(eng.commits):
        if cid not in seen:
            order.append(cid)
    return order


def _assign_lanes(eng: GitEngine, order: list[str]) -> dict[str, int]:
    """Assign a vertical lane index to each commit.

    Args:
        eng: Engine.
        order: Oldest-first commit ids.

    Returns:
        Mapping commit id → lane index (0-based).
    """
    lanes: dict[str, int] = {}
    for cid in order:
        commit = eng.commits[cid]
        if not commit.parents:
            lanes[cid] = 0
            continue
        parent_lanes = [lanes.get(p, 0) for p in commit.parents if p in lanes]
        lanes[cid] = parent_lanes[0] if parent_lanes else 0
        if len(commit.parents) >= 2:
            # merge nodes stay on first parent lane
            pass
    # Spread tips of diverging branches a bit
    return lanes


def render_graph_svg(
    eng: GitEngine,
    *,
    width: int = 960,
    node_r: int = 16,
    row_gap: int = 56,
    col_gap: int = 88,
    left_pad: int = 36,
    top_pad: int = 48,
    goal: GitEngine | None = None,
) -> str:
    """Render the commit graph as a self-contained SVG string.

    Args:
        eng: Engine to draw.
        width: SVG width in pixels.
        node_r: Commit circle radius.
        row_gap: Vertical spacing between lanes.
        col_gap: Horizontal spacing between commits.
        left_pad: Left margin.
        top_pad: Top margin.
        goal: Optional goal engine used only to color-match tips (unused for now).

    Returns:
        SVG markup ready for ``st.components.v1.html``.
    """
    _ = goal
    if not eng.commits:
        return _empty_svg(width)

    order = _topo_order(eng)
    lanes = _assign_lanes(eng, order)
    max_lane = max(lanes.values()) if lanes else 0
    # Stable x by topo index
    xs = {cid: left_pad + 40 + i * col_gap for i, cid in enumerate(order)}
    # Center lanes vertically
    height = top_pad * 2 + max_lane * row_gap + 80
    ys = {cid: top_pad + lane * row_gap for cid, lane in lanes.items()}

    # Slight vertical separation when many commits share a lane
    by_lane: dict[int, list[str]] = {}
    for cid, lane in lanes.items():
        by_lane.setdefault(lane, []).append(cid)
    for lane, ids in by_lane.items():
        ids_sorted = sorted(ids, key=lambda c: xs[c])
        if len(ids_sorted) > 1:
            for i, cid in enumerate(ids_sorted):
                offset = (i % 3) * 6 - 6
                ys[cid] = top_pad + lane * row_gap + offset

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="100%" height="{height}" style="background:{PALETTE["bg"]};border-radius:12px">',
        f'<rect width="100%" height="100%" fill="{PALETTE["bg"]}" rx="12"/>',
    ]

    # Edges first
    for cid in order:
        commit = eng.commits[cid]
        x2, y2 = xs[cid], ys[cid]
        for parent in commit.parents:
            if parent not in xs:
                continue
            x1, y1 = xs[parent], ys[parent]
            color = PALETTE["edge"]
            if len(commit.parents) >= 2:
                color = PALETTE["commit_merge"]
            parts.append(
                f'<path d="M {x1 + node_r} {y1} C {x1 + node_r + 24} {y1}, '
                f'{x2 - node_r - 24} {y2}, {x2 - node_r} {y2}" '
                f'fill="none" stroke="{color}" stroke-width="2"/>'
            )

    # Commit circles + ids
    for cid in order:
        commit = eng.commits[cid]
        x, y = xs[cid], ys[cid]
        fill = PALETTE["commit_merge"] if len(commit.parents) >= 2 else PALETTE["commit"]
        parts.append(
            f'<circle cx="{x}" cy="{y}" r="{node_r}" fill="{fill}" stroke="{PALETTE["ink"]}" stroke-width="1.5"/>'
        )
        label = html.escape(cid)
        parts.append(
            f'<text x="{x}" y="{y + 4}" text-anchor="middle" '
            f'font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" '
            f'font-size="11" font-weight="700" fill="{PALETTE["bg"]}">{label}</text>'
        )
        if commit.message:
            tip = html.escape(commit.message[:28])
            parts.append(
                f'<title>{html.escape(cid)}: {html.escape(commit.message)}</title>'
            )
            parts.append(
                f'<text x="{x}" y="{y + node_r + 14}" text-anchor="middle" '
                f'font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" '
                f'font-size="10" fill="{PALETTE["muted"]}">{tip}</text>'
            )

    # Refs: place to the right of tip commit
    def ref_pill(name: str, commit_id: str, kind: str, row: int) -> None:
        if commit_id not in xs:
            return
        color = {
            "branch": PALETTE["branch"],
            "remote": PALETTE["remote"],
            "tag": PALETTE["tag"],
            "head": PALETTE["head"],
        }.get(kind, PALETTE["muted"])
        x = xs[commit_id] + node_r + 10
        y = ys[commit_id] - node_r - 10 + row * 0
        y = ys[commit_id] - 28 - row * 22
        text = html.escape(name)
        w = max(36, 9 * len(name) + 14)
        parts.append(
            f'<rect x="{x}" y="{y - 11}" width="{w}" height="22" rx="6" '
            f'fill="{PALETTE["surface"]}" stroke="{color}" stroke-width="1.5"/>'
        )
        parts.append(
            f'<text x="{x + w / 2}" y="{y + 4}" text-anchor="middle" '
            f'font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" '
            f'font-size="11" fill="{color}">{text}</text>'
        )

    row = 0
    for name, ref in sorted(eng.branches.items()):
        ref_pill(name, ref.target, "branch", row)
        row += 1
    for name, ref in sorted(eng.remote_branches.items()):
        ref_pill(name, ref.target, "remote", row)
        row += 1
    for name, ref in sorted(eng.tags.items()):
        ref_pill(name, ref.target, "tag", row)
        row += 1

    try:
        head_commit = eng.head_commit_id()
    except Exception:
        head_commit = None
    if head_commit and head_commit in xs:
        head_label = eng.head_target if not eng.head_detached else "HEAD"
        ref_pill(f"HEAD:{head_label}" if eng.head_detached else "HEAD", head_commit, "head", row)

    parts.append("</svg>")
    return "".join(parts)


def _empty_svg(width: int) -> str:
    """Render an empty-state SVG.

    Args:
        width: SVG width.

    Returns:
        SVG markup.
    """
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 160" width="100%" height="160">'
        f'<rect width="100%" height="100%" fill="{PALETTE["bg"]}" rx="12"/>'
        f'<text x="{width / 2}" y="80" text-anchor="middle" fill="{PALETTE["muted"]}" '
        f'font-family="ui-monospace,Menlo,Consolas,monospace" font-size="14">no commits yet</text></svg>'
    )
