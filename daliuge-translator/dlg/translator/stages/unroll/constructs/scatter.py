from typing import TYPE_CHECKING, Any, Optional, Sequence

from dlg.common import dropdict
from dlg.translator.errors import GInvalidLink, GInvalidNode
from dlg.translator.vocabulary import Categories

from .base import GraphContext, WiringContext, resolve_aligned_edges

if TYPE_CHECKING:
    from ..model import Edge, LogicalLink


class ScatterHandler:
    construct_type = Categories.SCATTER
    is_group_construct = True
    edge_keys = ()

    def validate_link(self, source: Any, target: Any) -> None:
        from .registry import is_construct

        if is_construct(source, Categories.SCATTER) or is_construct(
            target, Categories.SCATTER
        ):
            prompt = "Remember to specify Input App Type for the Scatter construct!"
            raise GInvalidLink(
                "Scatter construct {0} or {1} cannot be linked. {2}".format(
                    source.name, target.name, prompt
                )
            )

    def degree_of_parallelism(
        self,
        node: Any,
        ctx: Optional[GraphContext] = None,
    ) -> int:
        del ctx

        for key in [
            "num_of_copies",
            "num_of_splits",
            "Number of copies",
        ]:
            if key in node.jd and node.jd[key]:
                return int(node.jd[key])

        raise GInvalidNode(
            f"Scatter '{node.name}' ({node.id}) has no degree of parallelism. "
            "One of 'num_of_copies', 'num_of_splits', "
            "'Number of copies' is required."
        )

    def resolve_edges(
        self,
        link: "LogicalLink",
        sources: Sequence[dropdict],
        targets: Sequence[dropdict],
        ctx: WiringContext,
    ) -> list["Edge"]:
        """Resolve the matrix's one-to-one within-group fallback.

        Scatter creates no placeholder DROP. GroupBy or Gather may supply the
        source DROPs at this boundary. The shared resolver enforces one source
        per target, and ``link_drops`` performs the physical wiring.
        """
        del ctx

        return resolve_aligned_edges(link, sources, targets)
