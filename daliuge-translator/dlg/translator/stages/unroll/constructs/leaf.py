from typing import Any


class LeafHandler:
    construct_type = "leaf"

    def degree_of_parallelism(self, node: Any, ctx: Any) -> int:
        del node, ctx

        return 1