"""Autonomous Startup Engine — mission traceability graph.

Every startup artifact (mission → strategy → objective → goal → product →
project → employee → task → execution → kpi → decision → feedback) is linked
into a directed graph as entities are created. This is the single provenance
mechanism: no parallel "lineage" tables. ``trace`` answers "why does this task
exist" by walking edges back to the mission.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.startup import MissionGraphEdge, MissionGraphRelation


def _dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str)


def _loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:  # pragma: no cover - defensive
        return None


class MissionGraphBuilder:
    """Record and query mission-graph edges."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def link(
        self,
        *,
        company_id: UUID,
        source_type: str,
        source_id: UUID,
        target_type: str,
        target_id: UUID,
        relation: MissionGraphRelation,
        metadata: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> MissionGraphEdge:
        """Create an edge (idempotent on source/target/relation)."""
        existing = self._find_edge(source_type, source_id, target_type, target_id, relation)
        if existing is not None:
            return existing
        edge = MissionGraphEdge(
            company_id=company_id,
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            relation=relation,
            edge_metadata=_dumps(metadata),
        )
        self._db.add(edge)
        self._db.flush()
        if commit:
            self._db.commit()
        return edge

    def _find_edge(
        self,
        source_type: str,
        source_id: UUID,
        target_type: str,
        target_id: UUID,
        relation: MissionGraphRelation,
    ) -> MissionGraphEdge | None:
        stmt = select(MissionGraphEdge).where(
            MissionGraphEdge.source_type == source_type,
            MissionGraphEdge.source_id == source_id,
            MissionGraphEdge.target_type == target_type,
            MissionGraphEdge.target_id == target_id,
            MissionGraphEdge.relation == relation,
        )
        return self._db.scalar(stmt)

    # ── Queries ────────────────────────────────────────────────────────

    def query(
        self,
        company_id: UUID,
        *,
        node_type: str | None = None,
        node_id: UUID | None = None,
        relation: MissionGraphRelation | None = None,
        limit: int = 500,
    ) -> list[MissionGraphEdge]:
        """Return edges for a company, optionally filtered by node/relation."""
        stmt = (
            select(MissionGraphEdge)
            .where(MissionGraphEdge.company_id == company_id)
            .order_by(MissionGraphEdge.created_at)
        )
        if node_type is not None and node_id is not None:
            stmt = stmt.where(
                (
                    (MissionGraphEdge.source_type == node_type)
                    & (MissionGraphEdge.source_id == node_id)
                )
                | (
                    (MissionGraphEdge.target_type == node_type)
                    & (MissionGraphEdge.target_id == node_id)
                )
            )
        if relation is not None:
            stmt = stmt.where(MissionGraphEdge.relation == relation)
        stmt = stmt.limit(limit)
        return list(self._db.execute(stmt).scalars().all())

    def children(self, company_id: UUID, node_type: str, node_id: UUID) -> list[MissionGraphEdge]:
        """Outgoing edges from a node."""
        stmt = select(MissionGraphEdge).where(
            MissionGraphEdge.company_id == company_id,
            MissionGraphEdge.source_type == node_type,
            MissionGraphEdge.source_id == node_id,
        )
        return list(self._db.execute(stmt).scalars().all())

    def parents(self, company_id: UUID, node_type: str, node_id: UUID) -> list[MissionGraphEdge]:
        """Incoming edges to a node."""
        stmt = select(MissionGraphEdge).where(
            MissionGraphEdge.company_id == company_id,
            MissionGraphEdge.target_type == node_type,
            MissionGraphEdge.target_id == node_id,
        )
        return list(self._db.execute(stmt).scalars().all())

    def trace(
        self, company_id: UUID, node_type: str, node_id: UUID, *, max_depth: int = 20
    ) -> dict[str, Any]:
        """Walk the derivation lineage back to the mission — 'why does this exist'.

        Edges are stored child → parent (e.g. ``goal → mission`` for
        ``derived_from``), so walking the node's outgoing edges moves up the
        lineage toward the mission.
        """
        chain: list[dict[str, Any]] = []
        visited: set[tuple[str, str]] = set()
        frontier: list[tuple[str, UUID]] = [(node_type, node_id)]
        reached_mission = node_type == "mission"
        depth = 0
        while frontier and depth < max_depth:
            next_frontier: list[tuple[str, UUID]] = []
            for ntype, nid in frontier:
                key = (ntype, str(nid))
                if key in visited:
                    continue
                visited.add(key)
                for edge in self.children(company_id, ntype, nid):
                    chain.append(
                        {
                            "from": {"type": edge.source_type, "id": str(edge.source_id)},
                            "to": {"type": edge.target_type, "id": str(edge.target_id)},
                            "relation": edge.relation.value,
                            "metadata": _loads(edge.edge_metadata),
                        }
                    )
                    if edge.target_type == "mission":
                        reached_mission = True
                    next_frontier.append((edge.target_type, edge.target_id))
            frontier = next_frontier
            depth += 1
        return {
            "origin": {"type": node_type, "id": str(node_id)},
            "chain": chain,
            "reached_mission": reached_mission,
        }

    def to_dict(self, edge: MissionGraphEdge) -> dict[str, Any]:
        return {
            "id": str(edge.id),
            "company_id": str(edge.company_id),
            "source_type": edge.source_type,
            "source_id": str(edge.source_id),
            "target_type": edge.target_type,
            "target_id": str(edge.target_id),
            "relation": edge.relation.value,
            "metadata": _loads(edge.edge_metadata),
            "created_at": edge.created_at.isoformat() if edge.created_at else None,
        }
