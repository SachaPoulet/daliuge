"""
Common interface for partition algorithm plugins.
"""

from typing import Any, Protocol


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
