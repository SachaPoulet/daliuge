from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, Optional, Sequence

from dlg.common import dropdict
from dlg.translator.errors import GInvalidLink, GraphException
from dlg.translator.vocabulary import Categories

from .base import GraphContext, WiringContext

if TYPE_CHECKING:
    from ..model import Edge, LogicalLink


class GroupByHandler:
    construct_type = Categories.GROUP_BY
    is_group_construct = True
    edge_keys = ()

    def validate_link(self, source: Any, target: Any) -> None:
        from .registry import is_construct

        if is_construct(target, Categories.GROUP_BY):
            if source.is_group:
                raise GInvalidLink(
                    "GroupBy {0} input must not be a group {1}".format(
                        target.id, source.id
                    )
                )
            if len(target.inputs) > 0:
                raise GInvalidLink(
                    "GroupBy {0} already has input {2} other than {1}".format(
                        target.id, source.id, target.inputs[0].id
                    )
                )
            if source.gid == 0:
                raise GInvalidLink(
                    "GroupBy {0} requires at least one Scatter around input {1}".format(
                        target.id, source.id
                    )
                )

        if is_construct(source, Categories.GROUP_BY) and not is_construct(
            target, Categories.GATHER
        ):
            raise GInvalidLink(
                "Output {1} from GroupBy {0} must be Gather, otherwise embbed {1} inside GroupBy {0}".format(
                    source.id, target.id
                )
            )

    def degree_of_parallelism(
        self,
        node: Any,
        ctx: Optional[GraphContext] = None,
    ) -> int:
        del ctx

        return node.group_by_scatter_layers[0]

    def resolve_edges(
        self,
        link: LogicalLink,
        sources: Sequence[dropdict],
        targets: Sequence[dropdict],
        ctx: WiringContext,
    ) -> list[Edge]:
        """Return edge pairs grouped by the GroupBy key in each source IID."""

        from .registry import is_construct
        from ..model import Edge

        del ctx

        source_node = link.source
        target_node = link.target
        groups: dict[str, list[dropdict]] = defaultdict(list)
        layer_index = target_node.group_by_scatter_layers[1]

        for source_drop in sources:
            source_context = source_drop["iid"].split("-")
            if target_node.group_keys is None:
                group_key = source_context[-1]
                if (
                    source_node.h_level - 2 == target_node.h_level
                    and target_node.h_level > 0
                ):
                    group_context = "-".join(source_context[0:-2])
                    group_key = f"{group_context}-{group_key}"
            else:
                if is_construct(source_node.group, Categories.GROUP_BY):
                    try:
                        source_context = (
                            source_drop["iid"].split("$")[1].split("-")
                        )
                    except IndexError as error:
                        raise GraphException(
                            "The group by hiearchy in the multi-key group by "
                            "'{0}' is not specified for node '{1}'".format(
                                source_node.group.name, source_node.name
                            )
                        ) from error
                else:
                    source_context.reverse()

                group_key = "-".join(
                    source_context[index] for index in layer_index
                )

            groups[group_key].append(source_drop)

        if len(groups) != len(targets):
            raise GraphException(
                "# of Group keys {0} != # of Group Drops {1} for LGN {2}".format(
                    len(groups), len(targets), target_node.id
                )
            )

        edges = []
        for index, group_key in enumerate(
            sorted(
                groups,
                key=lambda value: tuple(
                    int(component) for component in value.split("-")
                ),
            )
        ):
            for source_drop in groups[group_key]:
                edges.append(
                    Edge(
                        link=link,
                        source=source_drop,
                        target=targets[index],
                    )
                )

        return edges
