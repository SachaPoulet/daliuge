"""
Common interface for partition algorithm plugins.
"""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class NoneOptions:
    """Options for the no-partition algorithm."""


@dataclass(frozen=True)
class MetisOptions:
    """Options consumed by the METIS partition algorithm."""

    min_goal: int = 0
    ptype: int = 0
    max_load_imb: int = 90


@dataclass(frozen=True)
class MySarkarOptions:
    """Options consumed by the MySarkar partition algorithm."""

    max_cpu: int = 8
    max_mem: int = 1000


@dataclass(frozen=True)
class MinNumPartsOptions:
    """Options consumed by the MinNumParts partition algorithm."""

    deadline: int | None = None
    max_cpu: int = 8
    time_greedy: int = 50


@dataclass(frozen=True)
class PsoOptions:
    """Options consumed by the PSO partition algorithm."""

    max_cpu: int = 8
    max_mem: int = 1000
    deadline: int | None = None
    topk: int = 30
    swarm_size: int = 40


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
        raise NotImplementedError
