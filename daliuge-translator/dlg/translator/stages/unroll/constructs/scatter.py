from typing import Any, Optional

from dlg.translator.errors import GInvalidLink
from dlg.translator.errors import GInvalidNode
from dlg.translator.vocabulary import Categories

from .base import GraphContext


class ScatterHandler:
    construct_type = Categories.SCATTER
    edge_keys = ()

    def validate_link(self, source: Any, target: Any) -> None:
        if source.is_scatter or target.is_scatter:
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
