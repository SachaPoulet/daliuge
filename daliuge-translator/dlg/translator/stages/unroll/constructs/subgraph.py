from typing import Any

from dlg.translator.vocabulary import Categories


class SubgraphHandler:
    construct_type = Categories.SUBGRAPH
    edge_keys = ()

    def degree_of_parallelism(self, node: Any, ctx: Any) -> int:
        del node, ctx

        return 1