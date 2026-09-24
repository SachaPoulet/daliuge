from typing import Any, Optional

from dlg.translator.vocabulary import Categories

from .base import GraphContext


class ServiceHandler:
    construct_type = Categories.SERVICE
    edge_keys = ()

    def validate_link(self, source: Any, target: Any) -> None:
        del source, target

    def degree_of_parallelism(
        self,
        node: Any,
        ctx: Optional[GraphContext] = None,
    ) -> int:
        del node, ctx

        return 1
