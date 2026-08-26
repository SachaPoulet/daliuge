from __future__ import annotations
from dataclasses import dataclass, field
from copy import deepcopy
from dlg.translator.artefacts import PhysicalGraphTemplate, PhysicalGraphTemplatePartitioned
from dlg.dropmake.pg_generator import partition
from dlg.common.reproducibility.reproducibility import init_pgt_partition_repro_data


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
            drops=partition(deepcopy(pgt.drops),
                            algo=self._opts.algo,
                            num_partitions=self._opts.num_partitions,
                            num_islands=self._opts.num_islands,
                            partition_label=self._opts.partition_label,
                            **self._opts.algo_params),
            reprodata=pgt.reprodata
        )

    def stamp(self, pgtp: PhysicalGraphTemplatePartitioned) -> PhysicalGraphTemplatePartitioned:
        return PhysicalGraphTemplatePartitioned.from_wire(
            init_pgt_partition_repro_data(pgtp.to_wire()))
