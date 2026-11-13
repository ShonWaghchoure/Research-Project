"""Tests for radial feeder helpers."""

from __future__ import annotations

from app.engine.grid import (
    build_pi_matrix,
    default_13_node_feeder,
    path,
)


def test_default_feeder_has_13_nodes() -> None:
    feeder = default_13_node_feeder()
    assert len(feeder.nodes()) == 13
    assert feeder.root == "n0"
    assert len(feeder.lines) == 12


def test_path_to_self_empty() -> None:
    feeder = default_13_node_feeder()
    assert path(feeder, "n5", "n5") == []


def test_path_parent_child() -> None:
    feeder = default_13_node_feeder()
    hops = path(feeder, "n0", "n1")
    assert hops == [("l_n0_n1", 1)]
    hops_back = path(feeder, "n1", "n0")
    assert hops_back == [("l_n0_n1", -1)]


def test_path_across_branches() -> None:
    feeder = default_13_node_feeder()
    # n4 → n1 → n0 → n3 → n8
    hops = path(feeder, "n4", "n8")
    line_ids = [h[0] for h in hops]
    assert line_ids == ["l_n1_n4", "l_n0_n1", "l_n0_n3", "l_n3_n8"]
    assert hops[0][1] == -1  # up toward root
    assert hops[-1][1] == 1  # down away from root


def test_pi_matrix_trade_uses_path_lines() -> None:
    feeder = default_13_node_feeder()
    pi = build_pi_matrix(
        feeder,
        buyers=["b0"],
        sellers=["s0"],
        buyer_nodes={"b0": "n8"},
        seller_nodes={"s0": "n4"},
    )
    assert pi["l_n1_n4"].get(("b0", "s0")) == -1 or pi["l_n1_n4"].get(("b0", "s0")) == 1
    # Trade must touch the shared trunk lines
    assert ("b0", "s0") in pi["l_n0_n1"] or ("b0", "s0") in pi["l_n0_n3"]
