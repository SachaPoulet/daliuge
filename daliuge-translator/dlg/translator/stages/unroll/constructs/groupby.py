from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, Optional, Sequence

from dlg.common import dropdict
from dlg.translator.errors import GInvalidLink, GInvalidNode, GraphException
from dlg.translator.vocabulary import Categories

from .base import GraphContext, WiringContext

if TYPE_CHECKING:
    from ..model import Edge, LogicalLink


class GroupByHandler:
    """regroups DROPs from nested Scatters by key"""
    construct_type = Categories.GROUP_BY
    is_group_construct = True
    edge_keys = ()

    def validate_link(self, source: Any, target: Any) -> None:
        """check links into and out of a GroupBy.
        input must be a non-group node inside at least 
        one Scatter, and its output must be a Gather.
        """
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
        """Return DoP worked out by group_by_scatter_layers"""
        del ctx

        return self.group_by_scatter_layers(node)[0]

    def group_keys(self, node: Any) -> Optional[list[int]]:
        """
        Return:
            None or a list of keys (each key is an integer)
        """
        val = str(node.jd.get("group_key", "None"))
        if val in ["None", "-1", ""]:
            return None
        else:
            try:
                return [int(x) for x in val.split(",")]
            except ValueError as ve:
                raise GraphException(
                    "group_key must be an integer or comma-separated integers: {0}".format(
                        ve
                    )
                ) from ve

    def groupby_width(self, node: Any) -> int:
        """
        GroupBy count
        """
        tlgn = node.inputs[0]
        re_dop = 1
        cg = tlgn.group  # exclude its own group
        while cg.has_group():
            re_dop *= cg.group.dop
            cg = cg.group
        return re_dop

    def group_by_scatter_layers(
        self,
        node: Any,
    ) -> tuple[int, list[int], list[Any]]:
        """
        Scatter layers info associated with this group by logical node.

        returns a tuple of three items: DoP, list(layer indexes) from 
        inner scatter to outer scatter, and list(layers)
        """
        from .registry import is_construct

        tlgn = node.inputs[0]
        grpks = self.group_keys(node)
        ret_dop = 1
        layer_index = []  # from inner to outer
        layers = []  # from inner to outer
        c = 0
        if is_construct(tlgn.group, Categories.GROUP_BY):
            # group by followed by another group by
            if grpks is None or len(grpks) < 1:
                raise GInvalidNode(
                    "Must specify group_key for Group By '{0}'".format(node.name)
                )
            # find the "root" groupby and get all of its scatters
            inputgrp = node
            while (inputgrp is not None) and is_construct(
                inputgrp.inputs[0].group, Categories.GROUP_BY
            ):
                inputgrp = inputgrp.inputs[0].group
            # inputgrp now is the "root" groupby that follows Scatter immiately
            # move it to Scatter
            inputgrp = inputgrp.inputs[0].group
            # go thru all the scatters
            while (inputgrp is not None) and is_construct(inputgrp, Categories.SCATTER):
                if inputgrp.id in grpks:
                    ret_dop *= inputgrp.dop
                    layer_index.append(c)
                    layers.append(inputgrp)
                inputgrp = inputgrp.group
                c += 1
        else:
            if grpks is None or len(grpks) < 1:
                ret_dop = tlgn.group.dop
                layer_index.append(0)
                layers.append(tlgn.group)
            else:
                if len(grpks) == 1:
                    if grpks[0] == tlgn.group.id:
                        ret_dop = tlgn.group.dop
                        layer_index.append(0)
                        layers.append(tlgn.group)
                    else:
                        raise GInvalidNode(
                            "Wrong single group_key for {0}".format(node.name)
                        )
                else:
                    inputgrp = tlgn.group
                    # find the "groupby column list" from all layers of scatter loops
                    while (inputgrp is not None) and is_construct(
                        inputgrp, Categories.SCATTER
                    ):
                        if inputgrp.id in grpks:
                            ret_dop *= inputgrp.dop
                            layer_index.append(c)
                            layers.append(inputgrp)
                        inputgrp = inputgrp.group
                        c += 1

        return ret_dop, layer_index, layers

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
        layer_index = self.group_by_scatter_layers(target_node)[1]

        for source_drop in sources:
            coord = source_drop.coord
            source_context = coord.path

            if self.group_keys(target_node) is None:
                group_key = str(source_context[-1])
                if (
                    source_node.h_level - 2 == target_node.h_level
                    and target_node.h_level > 0
                ):
                    group_context = "-".join(
                        str(value) for value in source_context[0:-2]
                    )
                    group_key = f"{group_context}-{group_key}"
            else:
                if is_construct(source_node.group, Categories.GROUP_BY):
                    source_context = coord.group_key
                    if not source_context:
                        raise GraphException(
                            "The group by hiearchy in the multi-key group by "
                            "'{0}' is not specified for node '{1}'".format(
                                source_node.group.name, source_node.name
                            )
                        )
                else:
                    source_context = tuple(reversed(coord.path))

                group_key = "-".join(
                    str(source_context[index]) for index in layer_index
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
