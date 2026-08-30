#
#    ICRAR - International Centre for Radio Astronomy Research
#    (c) UWA - The University of Western Australia, 2015
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
"""
The DALiuGE resource manager uses the requested logical graphs, the available resources and
the profiling information and turns it into the partitioned physical graph,
which will then be deployed and monitored by the Physical Graph Manager
"""

import logging

# Frozen facade (proposal 7.1/7.2). These moved out to their stages, but the
# names must keep resolving here. daliuge-engine imports them from production
# code: `unroll` and `partition` in dlg/apps/subgraph.py, called inside a
# running workflow; `partition` again in the three deploy scripts; and
# `fill_config` in dlg/deploy/create_dlg_job.py. web/ imports `fill`, `unroll`
# and `partition`; the CLI imports `known_algorithms`.
# Re-export only -- do not drop, do not add logic.
# pylint: disable=unused-import
from dlg.translator.stages.prepare.config import fill_config
from dlg.translator.stages.prepare.params import apply_config, fill
from dlg.translator.stages.unroll.stage import unroll
from dlg.translator.stages.partition.stage import known_algorithms, partition

# pylint: enable=unused-import

logger = logging.getLogger(f"dlg.{__name__}")


def resource_map(pgt, nodes, num_islands=1, co_host_dim=True):
    """Maps a Physical Graph Template `pgt` to `nodes`"""

    logger.info(
        "Resource mapping called with nodes: %s, islands: %s and co_host_dim: %s",
        nodes, num_islands, co_host_dim
    )
    if not nodes:
        err_info = "Empty node_list, cannot map the PG template"
        raise ValueError(err_info)

    # if co_host_dim == True the island nodes appear twice
    dim_list = nodes[0:num_islands]
    nm_list = nodes[num_islands:]
    if type(pgt[0]) is str:
        pgt = pgt[1]  # remove the graph name TODO: we may want to retain that
    for drop_spec in pgt:
        if "node" in drop_spec and "island" in drop_spec:
            nidx = int(drop_spec["node"][1:])  # skip '#'
            drop_spec["node"] = nm_list[nidx]
            iidx = int(drop_spec["island"][1:])  # skip '#'
            drop_spec["island"] = dim_list[iidx]

    return pgt  # now it's a PG
