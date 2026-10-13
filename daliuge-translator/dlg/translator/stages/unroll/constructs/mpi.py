from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from dlg.common import dropdict
from dlg.translator.vocabulary import Categories

from .base import GraphContext, InstantiationContext
from ..coordinate import InstanceId

if TYPE_CHECKING:
    from ..model import LGNode


class MPIHandler:
    """Handler for MPI nodes, which unroll to one DROP per MPI process"""

    construct_type = Categories.MPI
    is_group_construct = False
    edge_keys = ()

    def validate_link(self, source: Any, target: Any) -> None:
        """Accept every link; MPI adds no link rules."""
        del source, target

    def degree_of_parallelism(
        self,
        node: Any,
        ctx: Optional[GraphContext] = None,
    ) -> int:
        """Return number of processes from num_of_procs"""
        del ctx

        return int(node.jd["num_of_procs"])

    def instantiate(
        self,
        node: LGNode,
        coord: InstanceId,
        ctx: InstantiationContext,
    ) -> list[dropdict]:
        """Create one DROP per process, each with its proc_index"""
        return [
            node.make_single_drop(
                coord.child(index),
                loop_ctx=ctx.loop_context,
                proc_index=index,
            )
            for index in range(node.dop)
        ]
