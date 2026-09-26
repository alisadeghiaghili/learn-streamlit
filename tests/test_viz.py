"""Tests for SVG rendering."""

from __future__ import annotations

from lgb.model import GitEngine
from lgb.viz import render_graph_svg


def test_render_sandbox_svg() -> None:
    svg = render_graph_svg(GitEngine.sandbox())
    assert svg.startswith("<svg")
    assert "C0" in svg
    assert "main" in svg
    assert "HEAD" in svg


def test_render_empty_svg() -> None:
    svg = render_graph_svg(GitEngine.empty())
    assert "no commits" in svg
