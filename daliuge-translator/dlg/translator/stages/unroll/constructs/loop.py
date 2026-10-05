from typing import Any, Optional

from dlg.translator.errors import GInvalidLink, GInvalidNode
from dlg.translator.vocabulary import Categories

from .base import GraphContext


class LoopHandler:
    construct_type = Categories.LOOP
    is_group_construct = True
    edge_keys = ()

    def validate_link(self, source: Any, target: Any) -> None:
        from .registry import is_construct

        if is_construct(source, Categories.LOOP) or is_construct(
            target, Categories.LOOP
        ):
            raise GInvalidLink(
                "Loop construct {0} or {1} cannot be linked".format(
                    source.name, target.name
                )
            )

    def degree_of_parallelism(
        self,
        node: Any,
        ctx: Optional[GraphContext] = None,
    ) -> int:
        del ctx

        for key in [
            "num_of_iter",
            "Number of Iterations",
            "Number of loops",
        ]:
            if key in node.jd and node.jd[key]:
                return int(node.jd[key])

        raise GInvalidNode(
            f"Loop '{node.name}' ({node.id}) has no iteration count. "
            "One of 'num_of_iter', 'Number of Iterations', "
            "'Number of loops' is required."
        )
