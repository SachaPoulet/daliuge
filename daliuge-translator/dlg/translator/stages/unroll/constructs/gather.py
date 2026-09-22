import math
from typing import Any, Optional

from dlg.translator.errors import GInvalidLink
from dlg.translator.vocabulary import Categories

from .base import GraphContext


class GatherHandler:
    construct_type = Categories.GATHER
    edge_keys = ()

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
