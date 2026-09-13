"""Algorithm-specific parameter models for physical-graph partitioning."""

from dataclasses import dataclass
from typing import Any, Mapping


def _value_or_default(params: Mapping[str, Any], name: str, default: Any) -> Any:
    """Return a mapping value unless it is absent or explicitly ``None``."""

    value = params.get(name)
    return default if value is None else value


@dataclass(frozen=True)
class MetisParameters:
    """Parameters consumed by the METIS partitioning branch."""

    min_goal: int = 0
    ptype: int = 0
    max_load_imb: int = 90

    @classmethod
    def from_mapping(cls, params: Mapping[str, Any]) -> "MetisParameters":
        """Build parameters while preserving existing absent/None fallback."""

        defaults = cls()
        return cls(
            min_goal=_value_or_default(params, "min_goal", defaults.min_goal),
            ptype=_value_or_default(params, "ptype", defaults.ptype),
            max_load_imb=_value_or_default(
                params, "max_load_imb", defaults.max_load_imb
            ),
        )


@dataclass(frozen=True)
class MySarkarParameters:
    """Parameters consumed by the MySarkar partitioning branch."""

    max_cpu: int = 8
    max_mem: int = 1000

    @classmethod
    def from_mapping(cls, params: Mapping[str, Any]) -> "MySarkarParameters":
        """Build parameters while preserving existing absent/None fallback."""

        defaults = cls()
        return cls(
            max_cpu=_value_or_default(params, "max_cpu", defaults.max_cpu),
            max_mem=_value_or_default(params, "max_mem", defaults.max_mem),
        )


@dataclass(frozen=True)
class MinNumPartsParameters:
    """Parameters consumed by the MinNumParts partitioning branch."""

    deadline: int | None = None
    max_cpu: int = 8
    time_greedy: int = 50

    @classmethod
    def from_mapping(cls, params: Mapping[str, Any]) -> "MinNumPartsParameters":
        """Build parameters while preserving existing absent/None fallback."""

        defaults = cls()
        return cls(
            deadline=_value_or_default(params, "deadline", defaults.deadline),
            max_cpu=_value_or_default(params, "max_cpu", defaults.max_cpu),
            time_greedy=_value_or_default(params, "time_greedy", defaults.time_greedy),
        )


@dataclass(frozen=True)
class PsoParameters:
    """Parameters consumed by the PSO partitioning branch."""

    max_cpu: int = 8
    max_mem: int = 1000
    deadline: int | None = None
    topk: int = 30
    swarm_size: int = 40

    @classmethod
    def from_mapping(cls, params: Mapping[str, Any]) -> "PsoParameters":
        """Build parameters while preserving existing absent/None fallback."""

        defaults = cls()
        return cls(
            max_cpu=_value_or_default(params, "max_cpu", defaults.max_cpu),
            max_mem=_value_or_default(params, "max_mem", defaults.max_mem),
            deadline=_value_or_default(params, "deadline", defaults.deadline),
            topk=_value_or_default(params, "topk", defaults.topk),
            swarm_size=_value_or_default(params, "swarm_size", defaults.swarm_size),
        )
