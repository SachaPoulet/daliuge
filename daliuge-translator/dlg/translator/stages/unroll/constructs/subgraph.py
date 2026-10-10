from typing import TYPE_CHECKING, Any, Optional, Sequence

from dlg.common import dropdict
from dlg.translator.vocabulary import Categories

from .base import GraphContext, WiringContext

if TYPE_CHECKING:
    from ..model import Edge, LogicalLink


class SubgraphHandler:
    construct_type = Categories.SUBGRAPH
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

    def resolve_edges(
        self,
        link: "LogicalLink",
        sources: Sequence[dropdict],
        targets: Sequence[dropdict],
        ctx: WiringContext,
    ) -> list["Edge"]:
        """Preserve the legacy no-op behaviour for Subgraph edges."""

        del link, sources, targets, ctx
        return []
