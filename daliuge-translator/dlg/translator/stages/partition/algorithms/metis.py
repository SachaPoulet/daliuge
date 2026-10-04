"""
METIS partition algorithm plugin.
"""

from typing import Any

from dlg.translator.stages.partition.pgtp import MetisPGTP

from .base import MetisOptions


class MetisAlgorithm:
    """Partition a physical graph template using METIS."""

    name = "metis"
    code = 1
    options_type = MetisOptions

    def partition(
        self,
        pgt: Any,
        *,
        num_partitions: int,
        partition_label: str,
        options: MetisOptions,
    ) -> MetisPGTP:
        ufactor = 100 - options.max_load_imb + 1
        if ufactor <= 0:
            ufactor = 1

        return MetisPGTP(
            pgt,
            num_partitions,
            options.min_goal,
            partition_label,
            options.ptype,
            ufactor,
            merge_parts=True,
        )
