"""Radial feeder topology helpers (pure)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Sequence, Tuple


@dataclass(frozen=True)
class FeederLine:
    id: str
    from_node: str  # parent (toward root)
    to_node: str  # child (away from root)
    capacity_kw: float


@dataclass(frozen=True)
class Feeder:
    """Radial tree feeder; ``root`` is the transformer / grid bus."""

    root: str
    lines: Tuple[FeederLine, ...]

    def nodes(self) -> List[str]:
        seen = {self.root}
        for line in self.lines:
            seen.add(line.from_node)
            seen.add(line.to_node)
        return sorted(seen)

    def children(self) -> Dict[str, List[FeederLine]]:
        out: Dict[str, List[FeederLine]] = {n: [] for n in self.nodes()}
        for line in self.lines:
            out.setdefault(line.from_node, []).append(line)
            out.setdefault(line.to_node, [])
        return out

    def parent_line(self) -> Dict[str, FeederLine]:
        """Map child node → the unique line connecting it toward the root."""
        return {line.to_node: line for line in self.lines}

    def line_by_id(self) -> Dict[str, FeederLine]:
        return {line.id: line for line in self.lines}


def path(feeder: Feeder, node_a: str, node_b: str) -> List[Tuple[str, int]]:
    """Return directed line hops from ``node_a`` to ``node_b``.

    Each hop is ``(line_id, direction)`` where direction is ``+1`` when traversing
    the line in its stored ``from→to`` orientation and ``-1`` otherwise.
    """
    if node_a == node_b:
        return []

    parent = feeder.parent_line()
    all_nodes = set(feeder.nodes())
    if node_a not in all_nodes or node_b not in all_nodes:
        raise ValueError(f"unknown node in path({node_a!r}, {node_b!r})")

    def to_root(node: str) -> List[str]:
        chain = [node]
        while node != feeder.root:
            if node not in parent:
                raise ValueError(f"node {node!r} is disconnected from root")
            node = parent[node].from_node
            chain.append(node)
        return chain

    chain_a = to_root(node_a)
    chain_b = to_root(node_b)
    set_b = set(chain_b)
    lca = next(n for n in chain_a if n in set_b)

    # Climb a → lca (toward root: child→parent = opposite of from→to)
    hops: List[Tuple[str, int]] = []
    node = node_a
    while node != lca:
        line = parent[node]
        hops.append((line.id, -1))
        node = line.from_node

    # Descend lca → b (away from root: parent→child = from→to)
    # Rebuild descent by reversing b→lca
    descent: List[FeederLine] = []
    node = node_b
    while node != lca:
        line = parent[node]
        descent.append(line)
        node = line.from_node
    for line in reversed(descent):
        hops.append((line.id, +1))

    return hops


def incidence_root_to_node(feeder: Feeder, node: str) -> Dict[str, int]:
    """Map line_id → direction for the path root → node."""
    return {line_id: direction for line_id, direction in path(feeder, feeder.root, node)}


def build_pi_matrix(
    feeder: Feeder,
    buyers: Sequence[str],
    sellers: Sequence[str],
    buyer_nodes: Mapping[str, str],
    seller_nodes: Mapping[str, str],
) -> Dict[str, Dict[Tuple[str, str], int]]:
    """Build ``pi[line_id][(buyer_id, seller_id)]`` ∈ {-1, 0, +1}.

    Value is the net directed usage of the line when 1 kWh flows seller → buyer
    (sum of directed hops on that line along the path).
    """
    pi: Dict[str, Dict[Tuple[str, str], int]] = {line.id: {} for line in feeder.lines}
    for b in buyers:
        for s in sellers:
            hops = path(feeder, seller_nodes[s], buyer_nodes[b])
            contrib: Dict[str, int] = {}
            for line_id, direction in hops:
                contrib[line_id] = contrib.get(line_id, 0) + direction
            for line_id, value in contrib.items():
                if value != 0:
                    pi[line_id][(b, s)] = value
    return pi


def default_13_node_feeder(capacity_kw: float = 100.0) -> Feeder:
    """IEEE-ish radial 13-node fixture (root + 12 downstream buses).

    Topology::

            n0 (root / transformer)
           /  |  \\
         n1  n2   n3
        /|\\   |   /\\
      n4 n5 n6 n7 n8 n9
              |
             n10
             /\\
          n11 n12
    """
    edges = [
        ("n0", "n1"),
        ("n0", "n2"),
        ("n0", "n3"),
        ("n1", "n4"),
        ("n1", "n5"),
        ("n1", "n6"),
        ("n2", "n7"),
        ("n3", "n8"),
        ("n3", "n9"),
        ("n7", "n10"),
        ("n10", "n11"),
        ("n10", "n12"),
    ]
    lines = tuple(
        FeederLine(
            id=f"l_{a}_{b}",
            from_node=a,
            to_node=b,
            capacity_kw=capacity_kw,
        )
        for a, b in edges
    )
    return Feeder(root="n0", lines=lines)


def with_line_capacities(feeder: Feeder, capacities: Mapping[str, float]) -> Feeder:
    """Return a copy of ``feeder`` with selected line capacities overridden."""
    lines = tuple(
        FeederLine(
            id=line.id,
            from_node=line.from_node,
            to_node=line.to_node,
            capacity_kw=capacities.get(line.id, line.capacity_kw),
        )
        for line in feeder.lines
    )
    return Feeder(root=feeder.root, lines=lines)


def scale_all_capacities(feeder: Feeder, capacity_kw: float) -> Feeder:
    return Feeder(
        root=feeder.root,
        lines=tuple(
            FeederLine(line.id, line.from_node, line.to_node, capacity_kw) for line in feeder.lines
        ),
    )
