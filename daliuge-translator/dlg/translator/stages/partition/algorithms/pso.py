"""
PSO partition algorithm plugin.
"""

from typing import Any

from dlg.translator.stages.partition.pgtp import PSOPGTP

from .base import PsoOptions


class PsoAlgorithm:
    """Partition a physical graph template using PSO."""

    name = "pso"
    code = 4
    options_type = PsoOptions

    def partition(
        self,
        pgt: Any,
        *,
        num_partitions: int,
        partition_label: str,
        options: PsoOptions,
    ) -> PSOPGTP:
        del num_partitions

        max_dop = {
            "num_cpus": options.max_cpu,
            "mem_usage": options.max_mem,
        }

        return PSOPGTP(
            pgt,
            partition_label,
            max_dop,
            deadline=options.deadline,
            topk=options.topk,
            swarm_size=options.swarm_size,
            merge_parts=True,
        )
