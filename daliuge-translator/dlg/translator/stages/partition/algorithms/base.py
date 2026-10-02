"""
Common interface for partition algorithm plugins.
"""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class MetisOptions:
    """Options consumed by the METIS partition algorithm."""

    min_goal: int = 0
    ptype: int = 0
    max_load_imb: int = 90


class PartitionAlgorithm(Protocol):
    """Interface implemented by partition algorithm plugins."""

    name: str
    code: int
    options_type: type[Any]

    def partition(
        self,
        pgt: Any,
        *,
        num_partitions: int,
        partition_label: str,
        options: Any,
    ) -> Any:
        """Create an algorithm-specific partitioned graph."""
        ...
