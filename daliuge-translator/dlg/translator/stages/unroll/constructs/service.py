from typing import Any, Optional

from dlg.common import CategoryType, dropdict
from dlg.translator.vocabulary import Categories

from ..coordinate import InstanceId
from .base import GraphContext, InstantiationContext


class ServiceHandler:
    construct_type = Categories.SERVICE
    is_group_construct = True
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

    def instantiate(
        self,
        node: Any,
        coord: InstanceId,
        ctx: InstantiationContext,
    ) -> list[dropdict]:
        del ctx

        # Preserve the legacy no-op path for a non-group Service node.
        if not node.is_group:
            return []

        # Preserve the working Service behaviour from LGNode.make_single_drop:
        # Service constructs instantiate as Application DROPs.
        node.jd["categoryType"] = CategoryType.APPLICATION

        was_data = node.is_data
        was_app = node.is_app
        node.is_data = False
        node.is_app = True

        try:
            drop = node.make_single_drop(coord)
        finally:
            node.is_data = was_data
            node.is_app = was_app

        return [drop]
