"""
Minimum-number-of-partitions algorithm plugin.
"""

from typing import Any

from dlg.translator.stages.partition.pgtp import MinNumPartsPGTP

from .base import MinNumPartsOptions


class MinNumPartsAlgorithm:
    """Partition a physical graph using the MinNumParts algorithm."""

    name = "min_num_parts"
    code = 3
    options_type = MinNumPartsOptions

    def partition(
        self,
        pgt: Any,
        *,
        num_partitions: int,
        partition_label: str,
        options: MinNumPartsOptions,
    ) -> MinNumPartsPGTP:
        optimistic_factor = 1 - options.time_greedy / 100.0

        return MinNumPartsPGTP(
            pgt,
            options.deadline,
            num_partitions,
            partition_label,
            options.max_cpu,
            merge_parts=True,
            optimistic_factor=optimistic_factor,
        )
