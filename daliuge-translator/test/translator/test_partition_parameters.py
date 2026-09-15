"""Tests for partition algorithm parameter models."""

import pytest

from dlg.translator.stages.partition.parameters import (
    MetisParameters,
    MinNumPartsParameters,
    MySarkarParameters,
    PsoParameters,
)


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        (MetisParameters, MetisParameters(0, 0, 90)),
        (MySarkarParameters, MySarkarParameters(8, 1000)),
        (MinNumPartsParameters, MinNumPartsParameters(None, 8, 50)),
        (PsoParameters, PsoParameters(8, 1000, None, 30, 40)),
    ],
)
def test_from_mapping_uses_established_defaults(model, expected):
    """Each model exposes the defaults previously held by ``partition``."""

    assert model.from_mapping({}) == expected


@pytest.mark.parametrize(
    ("model", "params", "expected"),
    [
        (
            MetisParameters,
            {"min_goal": 2, "ptype": 1, "max_load_imb": 75},
            MetisParameters(2, 1, 75),
        ),
        (
            MySarkarParameters,
            {"max_cpu": 16, "max_mem": 4096},
            MySarkarParameters(16, 4096),
        ),
        (
            MinNumPartsParameters,
            {"deadline": 120, "max_cpu": 12, "time_greedy": 25},
            MinNumPartsParameters(120, 12, 25),
        ),
        (
            PsoParameters,
            {
                "max_cpu": 16,
                "max_mem": 4096,
                "deadline": 120,
                "topk": 12,
                "swarm_size": 20,
            },
            PsoParameters(16, 4096, 120, 12, 20),
        ),
    ],
)
def test_from_mapping_applies_explicit_values(model, params, expected):
    """Each model reads only the values its algorithm uses."""

    assert model.from_mapping(params) == expected


@pytest.mark.parametrize(
    ("model", "params"),
    [
        (MetisParameters, {"min_goal": None, "ptype": None, "max_load_imb": None}),
        (MySarkarParameters, {"max_cpu": None, "max_mem": None}),
        (
            MinNumPartsParameters,
            {"deadline": None, "max_cpu": None, "time_greedy": None},
        ),
        (
            PsoParameters,
            {
                "max_cpu": None,
                "max_mem": None,
                "deadline": None,
                "topk": None,
                "swarm_size": None,
            },
        ),
    ],
)
def test_from_mapping_treats_none_like_a_missing_value(model, params):
    """Explicit None keeps the same fallback semantics as the old helper."""

    assert model.from_mapping(params) == model()


@pytest.mark.parametrize(
    ("model", "params", "expected"),
    [
        (MetisParameters, {"min_goal": 0, "ptype": 0, "max_load_imb": 0}, MetisParameters(0, 0, 0)),
        (MySarkarParameters, {"max_cpu": 0, "max_mem": 0}, MySarkarParameters(0, 0)),
        (
            MinNumPartsParameters,
            {"deadline": 0, "max_cpu": 0, "time_greedy": 0},
            MinNumPartsParameters(0, 0, 0),
        ),
        (
            PsoParameters,
            {"max_cpu": 0, "max_mem": 0, "deadline": 0, "topk": 0, "swarm_size": 0},
            PsoParameters(0, 0, 0, 0, 0),
        ),
    ],
)
def test_from_mapping_preserves_zero_values(model, params, expected):
    """Zero is an explicit value, not a request to fall back to a default."""

    assert model.from_mapping(params) == expected


@pytest.mark.parametrize(
    ("model", "params", "expected"),
    [
        (MetisParameters, {"min_goal": 3, "unused": "value"}, MetisParameters(3, 0, 90)),
        (MySarkarParameters, {"max_mem": 2048, "unused": "value"}, MySarkarParameters(8, 2048)),
        (
            MinNumPartsParameters,
            {"time_greedy": 10, "unused": "value"},
            MinNumPartsParameters(None, 8, 10),
        ),
        (PsoParameters, {"topk": 5, "unused": "value"}, PsoParameters(8, 1000, None, 5, 40)),
    ],
)
def test_from_mapping_ignores_unknown_keys_without_mutating_input(
    model, params, expected
):
    """Compatibility requires unrelated keys to be ignored and input untouched."""

    original = dict(params)

    assert model.from_mapping(params) == expected
    assert params == original
