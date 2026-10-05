"""
Backward-compatible typed parameter interface for partition options.

The canonical option models live under ``partition.algorithms.base``.
This module preserves the interface introduced by the earlier partition
parameter refactor while delegating validation and defaults to the registry.
"""

from typing import Any, Mapping, Optional, Union

from dlg.translator.stages.partition.algorithms.base import (
    MetisOptions,
    MinNumPartsOptions,
    MySarkarOptions,
    PsoOptions,
)
from dlg.translator.stages.partition.algorithms.registry import build_options


class MetisParameters(MetisOptions):
    """Backward-compatible METIS parameter model."""

    @classmethod
    def from_mapping(cls, params: Mapping[str, Any]) -> "MetisParameters":
        options = build_options("metis", params)
        return cls(**vars(options))


class MySarkarParameters(MySarkarOptions):
    """Backward-compatible MySarkar parameter model."""

    @classmethod
    def from_mapping(cls, params: Mapping[str, Any]) -> "MySarkarParameters":
        options = build_options("mysarkar", params)
        return cls(**vars(options))


class MinNumPartsParameters(MinNumPartsOptions):
    """Backward-compatible MinNumParts parameter model."""

    @classmethod
    def from_mapping(
        cls,
        params: Mapping[str, Any],
    ) -> "MinNumPartsParameters":
        options = build_options("min_num_parts", params)
        return cls(**vars(options))


class PsoParameters(PsoOptions):
    """Backward-compatible PSO parameter model."""

    @classmethod
    def from_mapping(cls, params: Mapping[str, Any]) -> "PsoParameters":
        options = build_options("pso", params)
        return cls(**vars(options))


PartitionAlgorithmParameters = Union[
    MetisParameters,
    MySarkarParameters,
    MinNumPartsParameters,
    PsoParameters,
]


_PARAMETER_MODELS = {
    "metis": MetisParameters,
    "mysarkar": MySarkarParameters,
    "min_num_parts": MinNumPartsParameters,
    "pso": PsoParameters,
}


def parameters_for(
    algo: str,
    params: Mapping[str, Any],
) -> Optional[PartitionAlgorithmParameters]:
    """Return validated typed parameters for a partition algorithm."""

    parameter_model = _PARAMETER_MODELS.get(algo)
    if parameter_model is None:
        return None

    return parameter_model.from_mapping(params)
