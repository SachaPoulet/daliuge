from typing import Any, Optional

from dlg.translator.vocabulary import Categories

from .base import GraphContext


class MPIHandler:
    construct_type = Categories.MPI
    is_group_construct = False
    edge_keys = ()

    def degree_of_parallelism(
        self,
        node: Any,
        ctx: Optional[GraphContext] = None,
    ) -> int:
        del ctx

        return int(node.jd["num_of_procs"])
