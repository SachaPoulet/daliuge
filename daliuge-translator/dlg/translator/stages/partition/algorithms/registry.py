"""
Registry for partition algorithm plugins.
"""

from dataclasses import fields
from typing import Any, Mapping, Optional, Union

from .base import PartitionAlgorithm
from .metis import MetisAlgorithm
from .min_num_parts import MinNumPartsAlgorithm
from .mysarkar import MySarkarAlgorithm
from .none import NoneAlgorithm
from .pso import PsoAlgorithm


ALGO_NONE = 0
ALGO_METIS = 1
ALGO_MY_SARKAR = 2
ALGO_MIN_NUM_PARTS = 3
ALGO_PSO = 4


_ALGORITHM_CODES = {
    "none": ALGO_NONE,
    "metis": ALGO_METIS,
    "mysarkar": ALGO_MY_SARKAR,
    "min_num_parts": ALGO_MIN_NUM_PARTS,
    "pso": ALGO_PSO,
}

_ALGORITHM_NAMES = {
    code: name for name, code in _ALGORITHM_CODES.items()
}

_algorithms: dict[str, PartitionAlgorithm] = {}


def register_algorithm(algorithm: PartitionAlgorithm) -> None:
    """Register a partition algorithm under its wire-contract name."""

    expected_code = _ALGORITHM_CODES.get(algorithm.name)

    if expected_code is None:
        raise ValueError(
            "Unknown partition algorithm name: %s" % algorithm.name
        )

    if algorithm.code != expected_code:
        raise ValueError(
            "Partition algorithm %s must use code %d"
            % (algorithm.name, expected_code)
        )

    _algorithms[algorithm.name] = algorithm


def get_algorithm(identifier: Union[str, int]) -> PartitionAlgorithm:
    """Return the registered algorithm for a name or numeric code."""

    if isinstance(identifier, int):
        identifier = _ALGORITHM_NAMES[identifier]

    return _algorithms[identifier]


def algorithm_name(identifier: Union[str, int]) -> str:
    """Resolve an algorithm identifier to its wire-contract name."""

    if isinstance(identifier, int):
        return _ALGORITHM_NAMES[identifier]

    if identifier not in _ALGORITHM_CODES:
        raise KeyError(identifier)

    return identifier


def algorithm_code(identifier: Union[str, int]) -> int:
    """Resolve an algorithm identifier to its numeric code."""

    if isinstance(identifier, int):
        if identifier not in _ALGORITHM_NAMES:
            raise KeyError(identifier)
        return identifier

    return _ALGORITHM_CODES[identifier]


def build_options(
    identifier: Union[str, int],
    params: Optional[Mapping[str, Any]] = None,
) -> Any:
    """Validate parameters and build options for the selected algorithm."""

    algorithm = get_algorithm(identifier)
    values = {} if params is None else dict(params)

    allowed = {
        option_field.name
        for option_field in fields(algorithm.options_type)
    }

    unknown = sorted(set(values) - allowed)

    if unknown:
        raise ValueError(
            "Unknown parameters for partition algorithm %s: %s"
            % (algorithm.name, ", ".join(unknown))
        )

    # Preserve the legacy behaviour where an explicit None uses the default.
    values = {
        name: value
        for name, value in values.items()
        if value is not None
    }

    return algorithm.options_type(**values)


def known_algorithms() -> list[str]:
    """Return the supported wire-contract algorithm names."""

    return list(_ALGORITHM_CODES)


register_algorithm(NoneAlgorithm())
register_algorithm(MetisAlgorithm())
register_algorithm(MySarkarAlgorithm())
register_algorithm(MinNumPartsAlgorithm())
register_algorithm(PsoAlgorithm())
