from typing import Any

from dlg.translator.errors import GInvalidNode
from dlg.translator.vocabulary import Categories


class ScatterHandler:
    construct_type = Categories.SCATTER

    def degree_of_parallelism(self, node: Any, ctx: Any) -> int:
        for key in [
            "num_of_copies",
            "num_of_splits",
            "Number of copies",
        ]:
            if key in node.jd and node.jd[key]:
                return int(node.jd[key])

        raise GInvalidNode(
            f"Scatter '{node.name}' ({node.id}) has no degree of parallelism. "
            "One of 'num_of_copies', 'num_of_splits', 'Number of copies' is required."
        )