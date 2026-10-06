"""
MySarkar partition algorithm plugin.
"""

from typing import Any

from dlg.translator.stages.partition.pgtp import MySarkarPGTP

from .base import MySarkarOptions


class MySarkarAlgorithm:
    """Partition a physical graph template using MySarkar."""

    name = "mysarkar"
    code = 2
    options_type = MySarkarOptions

    def partition(
        self,
        pgt: Any,
        *,
        num_partitions: int,
        partition_label: str,
        options: MySarkarOptions,
    ) -> MySarkarPGTP:
        max_dop = {
            "num_cpus": options.max_cpu,
            "mem_usage": options.max_mem,
        }

        return MySarkarPGTP(
            pgt,
            num_partitions,
            partition_label,
            max_dop,
            merge_parts=True,
        )
