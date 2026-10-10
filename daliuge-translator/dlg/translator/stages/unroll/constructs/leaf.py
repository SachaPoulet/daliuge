from typing import TYPE_CHECKING, Any, Optional, Sequence

from dlg.common import dropdict

from .base import GraphContext, WiringContext

if TYPE_CHECKING:
    from ..model import Edge, LogicalLink


class LeafHandler:
    construct_type = "leaf"
    is_group_construct = False
    edge_keys = ()

    def validate_link(self, source: Any, target: Any) -> None:
        del source, target

    def degree_of_parallelism(
        self,
        node: Any,
        ctx: Optional[GraphContext] = None,
    ) -> int:
        del node, ctx

        return 1

    def resolve_edges(
        self,
        link: "LogicalLink",
        sources: Sequence[dropdict],
        targets: Sequence[dropdict],
        ctx: WiringContext,
    ) -> list["Edge"]:
        """Resolve the plain leaf-to-leaf edge cases."""

        from ..model import Edge

        source = link.source
        target = link.target

        if source.is_start_node:
            return []

        chunk_size = ctx.chunk_size(source, target)
        edges = []

        if source.h_level >= target.h_level:
            for index, chunk in enumerate(ctx.split(sources, chunk_size)):
                for source_drop in chunk:
                    edges.append(Edge(link, source_drop, targets[index]))
        else:
            for index, chunk in enumerate(ctx.split(targets, chunk_size)):
                for target_drop in chunk:
                    edges.append(Edge(link, sources[index], target_drop))

        return edges
