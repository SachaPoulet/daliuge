from typing import Any

from dlg.translator.vocabulary import Categories


class ServiceHandler:
    construct_type = Categories.SERVICE
    edge_keys = ()

    def degree_of_parallelism(self, node: Any, ctx: Any) -> int:
        del node, ctx

        return 1
