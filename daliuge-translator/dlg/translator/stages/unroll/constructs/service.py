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
        # The flags route make_single_drop to _create_app_drop, whose dropclass
        # setter leaves is_app=True as the legacy branch did.
        node.jd["categoryType"] = CategoryType.APPLICATION
        node.is_data = False
        node.is_app = True

        return [node.make_single_drop(coord)]
