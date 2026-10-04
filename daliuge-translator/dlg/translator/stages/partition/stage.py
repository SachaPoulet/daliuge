#
#    ICRAR - International Centre for Radio Astronomy Research
#    (c) UWA - The University of Western Australia, 2020
#    Copyright by UWA (in the framework of the ICRAR)
#    All rights reserved
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston,
#    MA 02111-1307  USA
#

import logging
from dataclasses import dataclass, field
from copy import deepcopy

from dlg.translator.errors import GraphException
from dlg.translator.artefacts import PhysicalGraphTemplate, PhysicalGraphTemplatePartitioned
from dlg.common.reproducibility.reproducibility import init_pgt_partition_repro_data
from dlg.translator.stages.partition.pgt import PGT
from dlg.translator.stages.partition.pgtp import MetisPGTP, MySarkarPGTP, MinNumPartsPGTP, PSOPGTP
from dlg.translator.stages.partition.algorithms.registry import (
    ALGO_NONE,
    ALGO_METIS,
    ALGO_MY_SARKAR,
    ALGO_MIN_NUM_PARTS,
    ALGO_PSO,
    algorithm_code,
    algorithm_name,
    build_options,
    get_algorithm,
    known_algorithms as registry_known_algorithms,
)

logger = logging.getLogger(f"dlg.{__name__}")


@dataclass(frozen=True)
class PartitionOptions:
    algo: str = "metis"
    num_partitions: int = 1
    num_islands: int = 1
    partition_label: str = "partition"
    algo_params: dict = field(default_factory=dict)


class PartitionStage:
    """
    PGT -> PGT-partitioned
    """
    name = "partition"

    def __init__(self, opts: PartitionOptions = PartitionOptions()):
        self._opts = opts

    def run(self, pgt: PhysicalGraphTemplate) -> PhysicalGraphTemplatePartitioned:
        return PhysicalGraphTemplatePartitioned(
            drops=partition(
                pgt=deepcopy(pgt.drops),
                algo=self._opts.algo,
                num_partitions=self._opts.num_partitions,
                num_islands=self._opts.num_islands,
                partition_label=self._opts.partition_label,
                **self._opts.algo_params
            ),
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
        try:
            algo = algorithm_code(algo)
        except KeyError:
            raise ValueError(
                "Unknown partitioning algorithm: %s. Known algorithms are: %r"
                % (algo, registry_known_algorithms())
            )

    try:
        resolved_algo_name = algorithm_name(algo)
    except KeyError:
        raise GraphException(
            "Unknown partition algorithm: %d. Known algorithms are: %r"
            % (algo, registry_known_algorithms())
        )

    logger.info(
        "Running partitioning with algorithm=%s, %d partitions, "
        "%d islands, and parameters=%r",
        resolved_algo_name,
        num_partitions,
        num_islands,
        algo_params,
    )

    algorithm = get_algorithm(algo)
    options = build_options(algo, algo_params)

    pgt = algorithm.partition(
        pgt,
        num_partitions=num_partitions,
        partition_label=partition_label,
        options=options,
    )

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
    return registry_known_algorithms()
