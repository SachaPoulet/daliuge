from dataclasses import dataclass
from copy import deepcopy
from dlg.translator.artefacts import PhysicalGraphTemplatePartitioned, PhysicalGraph
from dlg.dropmake.pg_generator import resource_map
from dlg.common.reproducibility.reproducibility import init_pg_repro_data


@dataclass(frozen=True)
class MapOptions:
    nodes: list[str]
    num_islands: int = 1
    co_host_dim: bool = True    # Not used by the CLI, keep for signature


class MapStage:
    """
    PGT-partitioned -> PG
    """
    name = 'map'

    def __init__(self, opts: MapOptions):
        self._opts = opts

    def run(self, pgtp: PhysicalGraphTemplatePartitioned) -> PhysicalGraph:
        return PhysicalGraph(
            drops=resource_map(
                pgt=deepcopy(pgtp.drops),
                nodes=self._opts.nodes,
                num_islands=self._opts.num_islands,
                co_host_dim=self._opts.co_host_dim
            ),
            reprodata=deepcopy(pgtp.reprodata)
        )

    def stamp(self, pg: PhysicalGraph) -> PhysicalGraph:
        return PhysicalGraph.from_wire(init_pg_repro_data(pg.to_wire()))
