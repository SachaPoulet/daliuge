from typing import Any

from dlg.translator.vocabulary import Categories


class GroupByHandler:
    construct_type = Categories.GROUP_BY
    edge_keys = ()

    def degree_of_parallelism(self, node: Any, ctx: Any) -> int:
        del ctx

        return node.group_by_scatter_layers[0]
