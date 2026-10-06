"""
No-partition algorithm plugin.
"""

from typing import Any

from dlg.translator.stages.partition.pgt import PGT

from .base import NoneOptions


class NoneAlgorithm:
    """Wrap the graph as a PGT without partitioning it."""

    name = "none"
    code = 0
    options_type = NoneOptions

    def partition(
        self,
        pgt: Any,
        *,
        num_partitions: int,
        partition_label: str,
        options: NoneOptions,
    ) -> PGT:
        del num_partitions, partition_label, options
        return PGT(pgt)
