from typing import Any, Optional

from .base import GraphContext


class LeafHandler:
    construct_type = "leaf"
    edge_keys = ()

    def degree_of_parallelism(
        self,
        node: Any,
        ctx: Optional[GraphContext] = None,
    ) -> int:
        del node, ctx

        return 1
