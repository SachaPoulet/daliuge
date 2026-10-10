from typing import TYPE_CHECKING, Any, Optional, Sequence

from dlg.common import dropdict
from dlg.translator.errors import GraphException, GInvalidLink, GInvalidNode
from dlg.translator.vocabulary import Categories

from .base import GraphContext, WiringContext

if TYPE_CHECKING:
    from ..model import Edge, LogicalLink


class LoopHandler:
    construct_type = Categories.LOOP
    is_group_construct = True
    edge_keys = ()

    def resolve_edges(
        self,
        link: "LogicalLink",
        sources: Sequence[dropdict],
        targets: Sequence[dropdict],
        ctx: WiringContext,
    ) -> list["Edge"]:
        """Resolve the four loop-specific leaf-to-leaf edge cases."""

        from .registry import is_construct
        from ..model import Edge

        source = link.source
        target = link.target
        source_group = source.group
        target_group = target.group

        # Re-link a Loop end node to the next iteration's start node.
        if (
            source_group is not None
            and is_construct(source_group, Categories.LOOP)
            and source.gid == target.gid
            and source.is_group_end
            and target.is_group_start
        ):
            if len(sources) != len(targets):
                raise GraphException(
                    "# of sdrops '{0}' != # of tdrops '{1}'for Loop '{2}'".format(
                        source.name,
                        target.name,
                        source_group.name,
                    )
                )

            loop_size = source_group.dop
            edges = []

            for index, chunk in enumerate(ctx.split(sources, loop_size)):
                for iteration, source_drop in enumerate(chunk):
                    if iteration < loop_size - 1:
                        edges.append(
                            Edge(
                                link,
                                source_drop,
                                targets[index * loop_size + iteration + 1],
                            )
                        )

            return edges

        # Stepwise locking between two independent Loops.
        if (
            source_group is not None
            and is_construct(source_group, Categories.LOOP)
            and target_group is not None
            and is_construct(target_group, Categories.LOOP)
            and not source.h_related(target)
        ):
            return [
                Edge(link, source_drop, target_drop)
                for source_drop in sources
                for target_drop in targets
                if source_drop["loop_ctx"] == target_drop["loop_ctx"]
            ]

        # A loop-aware edge leaving a Loop uses only its last iteration.
        if (
            source_group is not None
            and is_construct(source_group, Categories.LOOP)
            and link.loop_aware
            and source.h_level > target.h_level
        ):
            loop_size = source_group.dop
            chunk_size = ctx.chunk_size(source, target)
            edges = []

            for index, chunk in enumerate(ctx.split(sources, chunk_size)):
                for iteration, source_drop in enumerate(chunk):
                    if iteration % loop_size == loop_size - 1:
                        edges.append(
                            Edge(
                                link,
                                source_drop,
                                targets[index],
                            )
                        )

            return edges

        # A loop-aware edge entering a Loop uses only its first iteration.
        if (
            target_group is not None
            and is_construct(target_group, Categories.LOOP)
            and link.loop_aware
            and source.h_level < target.h_level
        ):
            loop_size = target_group.dop
            chunk_size = ctx.chunk_size(source, target)
            edges = []

            for index, chunk in enumerate(ctx.split(targets, chunk_size)):
                for iteration, target_drop in enumerate(chunk):
                    if iteration % loop_size == 0:
                        edges.append(
                            Edge(
                                link,
                                sources[index],
                                target_drop,
                            )
                        )

            return edges

        return []

    def validate_link(self, source: Any, target: Any) -> None:
        from .registry import is_construct

        if is_construct(source, Categories.LOOP) or is_construct(
            target, Categories.LOOP
        ):
            raise GInvalidLink(
                "Loop construct {0} or {1} cannot be linked".format(
                    source.name, target.name
                )
            )

    def degree_of_parallelism(
        self,
        node: Any,
        ctx: Optional[GraphContext] = None,
    ) -> int:
        del ctx

        for key in [
            "num_of_iter",
            "Number of Iterations",
            "Number of loops",
        ]:
            if key in node.jd and node.jd[key]:
                return int(node.jd[key])

        raise GInvalidNode(
            f"Loop '{node.name}' ({node.id}) has no iteration count. "
            "One of 'num_of_iter', 'Number of Iterations', "
            "'Number of loops' is required."
        )
