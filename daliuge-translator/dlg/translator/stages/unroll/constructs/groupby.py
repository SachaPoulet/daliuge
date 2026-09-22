from typing import Any, Optional

from dlg.translator.vocabulary import Categories

from .base import GraphContext


class GroupByHandler:
    construct_type = Categories.GROUP_BY
    edge_keys = ()

    def degree_of_parallelism(
        self,
        node: Any,
        ctx: Optional[GraphContext] = None,
    ) -> int:
        del ctx

        return node.group_by_scatter_layers[0]
