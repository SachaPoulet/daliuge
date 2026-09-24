import math
from typing import Any, Optional

from dlg.translator.errors import GInvalidLink
from dlg.translator.vocabulary import Categories

from .base import GraphContext


class GatherHandler:
    construct_type = Categories.GATHER
    edge_keys = ()

    def validate_link(self, source: Any, target: Any) -> None:
        if source.is_gather:
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

        if target.is_gather:
            if not source.jd["categoryType"].lower() == "data" and not source.is_groupby:
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

        if input_node.is_groupby:
            input_dop = input_node.dop
        else:
            input_dop = node.dop_diff(input_node)

        return int(math.ceil(input_dop / float(node.gather_width)))
