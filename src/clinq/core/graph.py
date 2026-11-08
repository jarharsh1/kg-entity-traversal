"""A small, dependency-free directed property graph.

Nodes have a type (Vessel, Voyage, Port, Cargo, ...), an id, and attributes.
Edges are typed, directed relations (e.g. Voyage -OPERATED_BY-> Vessel).
Enough to model a fleet/voyage/port knowledge graph and do k-hop neighborhood
expansion for GraphRAG, with no external graph database.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Node:
    id: str
    type: str
    attrs: dict = field(default_factory=dict)


@dataclass
class Edge:
    src: str
    dst: str
    rel: str
    attrs: dict = field(default_factory=dict)


class PropertyGraph:
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self._out: dict[str, list[int]] = {}
        self._in: dict[str, list[int]] = {}

    # ---- construction ---------------------------------------------------- #
    def add_node(self, node_id: str, node_type: str, **attrs) -> None:
        if node_id in self.nodes:
            self.nodes[node_id].attrs.update(attrs)
        else:
            self.nodes[node_id] = Node(node_id, node_type, dict(attrs))

    def add_edge(self, src: str, dst: str, rel: str, **attrs) -> None:
        if src not in self.nodes or dst not in self.nodes:
            raise KeyError(f"both endpoints must exist: {src!r}, {dst!r}")
        idx = len(self.edges)
        self.edges.append(Edge(src, dst, rel, dict(attrs)))
        self._out.setdefault(src, []).append(idx)
        self._in.setdefault(dst, []).append(idx)

    # ---- queries --------------------------------------------------------- #
    def neighbors(self, node_id: str) -> list[tuple[Edge, str, str]]:
        """Return (edge, direction, other_id) for all incident edges."""
        out = [(self.edges[i], "out", self.edges[i].dst) for i in self._out.get(node_id, [])]
        inc = [(self.edges[i], "in", self.edges[i].src) for i in self._in.get(node_id, [])]
        return out + inc

    def expand(self, seeds: list[str], hops: int) -> tuple[set[str], list[Edge]]:
        """Return the node ids and edges within `hops` of any seed node."""
        seen = {s for s in seeds if s in self.nodes}
        frontier = set(seen)
        collected: list[Edge] = []
        edge_ids: set[int] = set()
        for _ in range(max(hops, 0)):
            nxt: set[str] = set()
            for nid in frontier:
                for i in self._out.get(nid, []) + self._in.get(nid, []):
                    if i not in edge_ids:
                        edge_ids.add(i)
                        collected.append(self.edges[i])
                    e = self.edges[i]
                    other = e.dst if e.src == nid else e.src
                    if other not in seen:
                        nxt.add(other)
            seen |= nxt
            frontier = nxt
            if not frontier:
                break
        return seen, collected

    def nodes_of_type(self, node_type: str) -> list[Node]:
        return [n for n in self.nodes.values() if n.type == node_type]

    def __len__(self) -> int:
        return len(self.nodes)
