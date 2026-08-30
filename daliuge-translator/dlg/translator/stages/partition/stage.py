import logging
from dataclasses import dataclass, field
from copy import deepcopy

from dlg.translator.errors import GraphException
from dlg.translator.artefacts import PhysicalGraphTemplate, PhysicalGraphTemplatePartitioned
from dlg.common.reproducibility.reproducibility import init_pgt_partition_repro_data
from dlg.translator.stages.partition.pgt import PGT
from dlg.translator.stages.partition.pgtp import MetisPGTP, MySarkarPGTP, MinNumPartsPGTP, PSOPGTP

logger = logging.getLogger(f"dlg.{__name__}")

ALGO_NONE = 0
ALGO_METIS = 1
ALGO_MY_SARKAR = 2
ALGO_MIN_NUM_PARTS = 3
ALGO_PSO = 4

_known_algos = {
    "none": ALGO_NONE,
    "metis": ALGO_METIS,
    "mysarkar": ALGO_MY_SARKAR,
    "min_num_parts": ALGO_MIN_NUM_PARTS,
    "pso": ALGO_PSO,
    ALGO_NONE: "none",
    ALGO_METIS: "metis",
    ALGO_MY_SARKAR: "mysarkar",
    ALGO_MIN_NUM_PARTS: "min_num_parts",
    ALGO_PSO: "pso",
}


@dataclass(frozen=True)
class PartitionOptions:
    algo: str = "metis"
    num_partitions: int = 1
    num_islands: int = 1
    partition_label: str = "partition"
    algo_params: dict = field(default_factory=dict)


class PartitionStage:
    name = "partition"

    def __init__(self, opts: PartitionOptions = PartitionOptions()):
        self._opts = opts

    def run(self, pgt: PhysicalGraphTemplate) -> PhysicalGraphTemplatePartitioned:
        return PhysicalGraphTemplatePartitioned(
            drops=partition(pgt=deepcopy(pgt.drops),
                            algo=self._opts.algo,
                            num_partitions=self._opts.num_partitions,
                            num_islands=self._opts.num_islands,
                            partition_label=self._opts.partition_label,
                            **self._opts.algo_params),
            reprodata=deepcopy(pgt.reprodata)
        )

    def stamp(self, pgtp: PhysicalGraphTemplatePartitioned) -> PhysicalGraphTemplatePartitioned:
        return PhysicalGraphTemplatePartitioned.from_wire(
            init_pgt_partition_repro_data(pgtp.to_wire()))


def partition(
    pgt,
    algo,
    num_partitions=1,
    num_islands=1,
    partition_label="partition",
    show_gojs=False,
    **algo_params,
):
    """Partitions a Physical Graph Template"""

    if isinstance(algo, str):
        if algo not in _known_algos:
            raise ValueError(
                "Unknown partitioning algorithm: %s. Known algorithms are: %r"
                % (algo, _known_algos.keys())
            )
        algo = _known_algos[algo]

    if algo not in _known_algos:
        raise GraphException(
            "Unknown partition algorithm: %d. Known algorithm are: %r"
            % (algo, _known_algos.keys())
        )

    logger.info(
        "Running partitioning with algorithm=%s, %d partitions, "
        "%d islands, and parameters=%r",
        _known_algos[algo],
        num_partitions,
        num_islands,
        algo_params,
    )

    # Read all possible values with defaults
    # Not all algorithms use them, but makes the coding easier
    # do_merge = num_islands > 1
    could_merge = True
    min_goal = _get_algo_param(algo_params, "min_goal", 0)
    ptype = _get_algo_param(algo_params, "ptype", 0)
    max_load_imb = _get_algo_param(algo_params, "max_load_imb", 90)
    max_cpu = _get_algo_param(algo_params, "max_cpu", 8)
    max_mem = _get_algo_param(algo_params, "max_mem", 1000)
    time_greedy = _get_algo_param(algo_params, "time_greedy", 50)
    deadline = _get_algo_param(algo_params, "deadline", None)
    topk = _get_algo_param(algo_params, "topk", 30)
    swarm_size = _get_algo_param(algo_params, "swarm_size", 40)

    max_dop = {"num_cpus": max_cpu, "mem_usage": max_mem}

    if algo == ALGO_NONE:
        pgt = PGT(pgt)

    elif algo == ALGO_METIS:
        ufactor = 100 - max_load_imb + 1
        if ufactor <= 0:
            ufactor = 1
        pgt = MetisPGTP(
            pgt,
            num_partitions,
            min_goal,
            partition_label,
            ptype,
            ufactor,
            merge_parts=could_merge,
        )

    elif algo == ALGO_MY_SARKAR:
        pgt = MySarkarPGTP(
            pgt,
            num_partitions,
            partition_label,
            max_dop,
            merge_parts=could_merge,
        )

    elif algo == ALGO_MIN_NUM_PARTS:
        time_greedy = 1 - time_greedy / 100.0  # assuming between 1 to 100
        pgt = MinNumPartsPGTP(
            pgt,
            deadline,
            num_partitions,
            partition_label,
            max_cpu,
            merge_parts=could_merge,
            optimistic_factor=time_greedy,
        )

    elif algo == ALGO_PSO:
        pgt = PSOPGTP(
            pgt,
            partition_label,
            max_dop,
            deadline=deadline,
            topk=topk,
            swarm_size=swarm_size,
            merge_parts=could_merge,
        )

    else:
        raise GraphException("Unknown partition algorithm: {0}".format(algo))

    pgt.to_gojs_json(string_rep=False, visual=show_gojs)
    if not show_gojs:
        pgt = pgt.to_pg_spec(
            [],
            ret_str=False,
            num_islands=num_islands,
            tpl_nodes_len=num_partitions + num_islands,
        )
    return pgt


def _get_algo_param(algo_params, param_name, default):
    """
    Make sure that default is set even if value has been passed as None.
    """
    param = algo_params.get(param_name)
    return param if param is not None else default


def known_algorithms():
    return [x for x in _known_algos.keys() if isinstance(x, str)]
