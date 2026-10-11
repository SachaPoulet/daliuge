import math
from typing import TYPE_CHECKING, Any, Optional, Sequence

from dlg.common import dropdict
from dlg.translator.errors import GInvalidLink, GraphException
from dlg.translator.vocabulary import Categories

from .base import GraphContext, WiringContext

if TYPE_CHECKING:
    from ..model import Edge, LogicalLink


class GatherHandler:
    construct_type = Categories.GATHER
    is_group_construct = True
    edge_keys = ()

    def validate_link(self, source: Any, target: Any) -> None:
        from .registry import is_construct

        if is_construct(source, Categories.GATHER):
            if not (
                target.jd["categoryType"] in ["app", "application", "Application"]
                and target.is_group_start
                and source.inputs[0].h_level == target.h_level
            ):
                raise GInvalidLink(
                    "Gather {0}'s output {1} must be a Group-Start Component inside a Group with the same H level as Gather's input".format(
                        source.id, target.id
                    )
                )

        if is_construct(target, Categories.GATHER):
            if (
                source.jd["categoryType"].lower() != "data"
                and not is_construct(source, Categories.GROUP_BY)
            ):
                raise GInvalidLink(
                    "Gather {0}'s input {1} should be either a GroupBy or Data. {2}".format(
                        target.id, source.id, source.jd
                    )
                )

    def degree_of_parallelism(
        self,
        node: Any,
        ctx: Optional[GraphContext] = None,
    ) -> int:
        del ctx

        try:
            input_node = node.inputs[0]
        except IndexError as error:
            raise GInvalidLink(
                "Gather '{0}' does not have input!".format(node.id)
            ) from error

        from .registry import is_construct

        if is_construct(input_node, Categories.GROUP_BY):
            input_dop = input_node.dop
        else:
            input_dop = node.dop_diff(input_node)

        return int(math.ceil(input_dop / float(node.gather_width)))

    def resolve_edges(
        self,
        link: "LogicalLink",
        sources: Sequence[dropdict],
        targets: Sequence[dropdict],
        ctx: WiringContext,
    ) -> list["Edge"]:
        """Resolve edges whose target is a Gather construct."""

        from ..model import Edge

        source = link.source
        target = link.target

        if source.h_level < target.h_level:
            raise GraphException(
                "Gather {0} has higher h-level than its input {1}".format(
                    target.id,
                    source.id,
                )
            )

        chunk_size = ctx.chunk_size(source, target)
        edges = []

        for index, chunk in enumerate(ctx.split(sources, chunk_size)):
            for source_drop in chunk:
                edges.append(
                    Edge(
                        link,
                        source_drop,
                        targets[index],
                    )
                )

        return edges

    def resolve_sequential_edges(
        self,
        link: "LogicalLink",
        inputs: Sequence[Sequence[Optional[dropdict]]],
        targets: Sequence[dropdict],
        ctx: WiringContext,
    ) -> list["Edge"]:
        """Resolve a Gather -> group-start link that sequentialises a Scatter.

        ``inputs[i]`` holds the inputs of the i-th Gather drop; ``targets``
        are the group-start drops. Gather drop i's inputs feed the next
        window of ``gather_width`` targets, so the Scatter runs that many
        iterations at a time. When a Gather has fewer inputs than its window,
        they are reused so every target in the window still waits on one.
        A window never runs past the last target, and is skipped when it would
        start exactly at an outer iteration's first target. Windows are counted
        over all targets, so when the Scatter's DoP is not a multiple of
        ``gather_width`` a Gather drop holds inputs from two outer iterations
        and its edges can cross into the next one. ``None`` marks an input
        from another Gather, which has no drop to chain.
        """
        del ctx

        from ..model import Edge

        # gather_width is defined on lg_node.LGNode, not on the model LGNode
        # that LogicalLink is annotated with.
        gather: Any = link.source
        edges = []

        for index, gather_inputs in enumerate(inputs):
            chainable = [drop for drop in gather_inputs if drop is not None]
            if not chainable:
                continue
            width = gather.gather_width
            dop = link.target.group.dop
            start = (index + 1) * width
            if start >= len(targets):
                continue
            if start >= dop and start % dop == 0:
                continue
            end = min((index + 2) * width, dop * (index + 1), len(targets))
            while start < end:
                for drop in chainable:
                    if start >= end:
                        break
                    edges.append(Edge(link, drop, targets[start]))
                    start += 1

        return edges
