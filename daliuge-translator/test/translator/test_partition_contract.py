"""Characterise the parameter and output contract of ``partition``.

These tests deliberately patch only the constructors named in the implementation
module. The real ``partition`` function still performs algorithm selection,
parameter handling, and output generation in every test.
"""

import pytest

from dlg.dropmake import pg_generator as implementation


class AlgorithmProbe:
    """Records output-method calls made by ``partition``."""

    def __init__(self):
        self.calls = []
        self.pg_spec = object()

    def to_gojs_json(self, *args, **kwargs):
        self.calls.append(("to_gojs_json", args, kwargs))

    def to_pg_spec(self, *args, **kwargs):
        self.calls.append(("to_pg_spec", args, kwargs))
        return self.pg_spec


class ConstructorProbe:
    """Captures constructor arguments and returns an ``AlgorithmProbe``."""

    def __init__(self, result):
        self.calls = []
        self.result = result

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result


@pytest.fixture
def patch_constructor(monkeypatch):
    """Patch one constructor at the lookup site used by ``partition``."""

    def patch(name):
        result = AlgorithmProbe()
        constructor = ConstructorProbe(result)
        monkeypatch.setattr(implementation, name, constructor)
        return constructor, result

    return patch


def assert_pg_spec_output(result, returned, num_partitions, num_islands):
    """Assert the unchanged post-processing contract for ``show_gojs=False``."""

    assert returned is result.pg_spec
    assert result.calls == [
        ("to_gojs_json", (), {"string_rep": False, "visual": False}),
        (
            "to_pg_spec",
            ([],),
            {
                "ret_str": False,
                "num_islands": num_islands,
                "tpl_nodes_len": num_partitions + num_islands,
            },
        ),
    ]


def test_none_constructs_pgt_and_generates_pg_spec(patch_constructor):
    """The ``none`` algorithm remains a PGT wrapper with normal output handling."""

    constructor, result = patch_constructor("PGT")
    pgt = object()

    returned = implementation.partition(
        pgt,
        "none",
        num_partitions=4,
        num_islands=2,
        partition_label="unused-for-none",
        unknown_parameter="ignored",
    )

    assert constructor.calls == [((pgt,), {})]
    assert_pg_spec_output(result, returned, num_partitions=4, num_islands=2)


def test_show_gojs_returns_algorithm_instance_without_pg_spec(patch_constructor):
    """GOJS mode performs only the GOJS conversion and returns the object."""

    constructor, result = patch_constructor("MetisPGTP")
    pgt = object()

    returned = implementation.partition(pgt, "metis", show_gojs=True)

    assert returned is result
    assert constructor.calls == [((pgt, 1, 0, "partition", 0, 11), {"merge_parts": True})]
    assert result.calls == [("to_gojs_json", (), {"string_rep": False, "visual": True})]


@pytest.mark.parametrize(
    ("algo_params", "expected_min_goal", "expected_ptype", "expected_ufactor"),
    [
        ({}, 0, 0, 11),
        ({"min_goal": None, "ptype": None, "max_load_imb": None}, 0, 0, 11),
        (
            {
                "min_goal": 7,
                "ptype": 3,
                "max_load_imb": 0,
                "unknown_parameter": "ignored",
            },
            7,
            3,
            101,
        ),
    ],
)
def test_metis_preserves_parameter_defaults_and_explicit_values(
    patch_constructor,
    algo_params,
    expected_min_goal,
    expected_ptype,
    expected_ufactor,
):
    """METIS retains missing/None fallback, zero values, and the ufactor formula."""

    constructor, result = patch_constructor("MetisPGTP")
    pgt = object()

    returned = implementation.partition(
        pgt,
        "metis",
        num_partitions=4,
        num_islands=2,
        partition_label="metis-label",
        **algo_params,
    )

    assert constructor.calls == [
        (
            (pgt, 4, expected_min_goal, "metis-label", expected_ptype, expected_ufactor),
            {"merge_parts": True},
        )
    ]
    assert_pg_spec_output(result, returned, num_partitions=4, num_islands=2)


@pytest.mark.parametrize(
    ("algo_params", "expected_max_dop"),
    [
        ({}, {"num_cpus": 8, "mem_usage": 1000}),
        ({"max_cpu": None, "max_mem": None}, {"num_cpus": 8, "mem_usage": 1000}),
        ({"max_cpu": 0, "max_mem": 2048}, {"num_cpus": 0, "mem_usage": 2048}),
    ],
)
def test_mysarkar_preserves_cpu_and_memory_parameters(
    patch_constructor, algo_params, expected_max_dop
):
    """MySarkar receives the established max_dop mapping unchanged."""

    constructor, result = patch_constructor("MySarkarPGTP")
    pgt = object()

    returned = implementation.partition(
        pgt,
        "mysarkar",
        num_partitions=3,
        num_islands=1,
        partition_label="sarkar-label",
        **algo_params,
    )

    assert constructor.calls == [
        ((pgt, 3, "sarkar-label", expected_max_dop), {"merge_parts": True})
    ]
    assert_pg_spec_output(result, returned, num_partitions=3, num_islands=1)


@pytest.mark.parametrize(
    ("algo_params", "expected_deadline", "expected_max_cpu", "expected_optimistic_factor"),
    [
        ({}, None, 8, 0.5),
        ({"deadline": None, "max_cpu": None, "time_greedy": None}, None, 8, 0.5),
        ({"deadline": 60, "max_cpu": 0, "time_greedy": 0}, 60, 0, 1.0),
    ],
)
def test_min_num_parts_preserves_deadline_cpu_and_time_greedy_conversion(
    patch_constructor,
    algo_params,
    expected_deadline,
    expected_max_cpu,
    expected_optimistic_factor,
):
    """MinNumParts keeps the established greedy-time conversion in its branch."""

    constructor, result = patch_constructor("MinNumPartsPGTP")
    pgt = object()

    returned = implementation.partition(
        pgt,
        "min_num_parts",
        num_partitions=5,
        num_islands=2,
        partition_label="min-parts-label",
        **algo_params,
    )

    assert constructor.calls == [
        (
            (pgt, expected_deadline, 5, "min-parts-label", expected_max_cpu),
            {
                "merge_parts": True,
                "optimistic_factor": expected_optimistic_factor,
            },
        )
    ]
    assert_pg_spec_output(result, returned, num_partitions=5, num_islands=2)


@pytest.mark.parametrize(
    ("algo_params", "expected_max_dop", "expected_deadline", "expected_topk", "expected_swarm_size"),
    [
        ({}, {"num_cpus": 8, "mem_usage": 1000}, None, 30, 40),
        (
            {
                "max_cpu": None,
                "max_mem": None,
                "deadline": None,
                "topk": None,
                "swarm_size": None,
            },
            {"num_cpus": 8, "mem_usage": 1000},
            None,
            30,
            40,
        ),
        (
            {
                "max_cpu": 0,
                "max_mem": 0,
                "deadline": 45,
                "topk": 0,
                "swarm_size": 0,
            },
            {"num_cpus": 0, "mem_usage": 0},
            45,
            0,
            0,
        ),
    ],
)
def test_pso_preserves_constructor_parameters(
    patch_constructor,
    algo_params,
    expected_max_dop,
    expected_deadline,
    expected_topk,
    expected_swarm_size,
):
    """PSO receives its existing default and explicit parameter values."""

    constructor, result = patch_constructor("PSOPGTP")
    pgt = object()

    returned = implementation.partition(
        pgt,
        "pso",
        num_partitions=7,
        num_islands=4,
        partition_label="pso-label",
        **algo_params,
    )

    assert constructor.calls == [
        (
            (pgt, "pso-label", expected_max_dop),
            {
                "deadline": expected_deadline,
                "topk": expected_topk,
                "swarm_size": expected_swarm_size,
                "merge_parts": True,
            },
        )
    ]
    assert_pg_spec_output(result, returned, num_partitions=7, num_islands=4)
