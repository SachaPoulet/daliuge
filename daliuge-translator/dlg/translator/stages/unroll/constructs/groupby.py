from typing import Any, Optional

from dlg.translator.errors import GInvalidLink
from dlg.translator.vocabulary import Categories

from .base import GraphContext


class GroupByHandler:
    construct_type = Categories.GROUP_BY
    edge_keys = ()

    def validate_link(self, source: Any, target: Any) -> None:
        if target.is_groupby:
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

        if source.is_groupby and not target.is_gather:
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
