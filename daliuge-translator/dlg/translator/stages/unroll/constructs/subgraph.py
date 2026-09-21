from typing import Any

from dlg.translator.vocabulary import Categories


class SubgraphHandler:
    construct_type = Categories.SUBGRAPH

    def degree_of_parallelism(self, node: Any, ctx: Any) -> int:
        return 1