from typing import Any, Optional

from dlg.translator.vocabulary import Categories

from .base import GraphContext


class MPIHandler:
    construct_type = Categories.MPI
    edge_keys = ()

    def validate_link(self, source: Any, target: Any) -> None:
        del source, target

    def degree_of_parallelism(
        self,
        node: Any,
        ctx: Optional[GraphContext] = None,
    ) -> int:
        del ctx

        return int(node.jd["num_of_procs"])
