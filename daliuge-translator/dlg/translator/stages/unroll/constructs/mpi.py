from typing import Any

from dlg.translator.vocabulary import Categories


class MPIHandler:
    construct_type = Categories.MPI
    edge_keys = ()

    def degree_of_parallelism(self, node: Any, ctx: Any) -> int:
        del ctx

        return int(node.jd["num_of_procs"])