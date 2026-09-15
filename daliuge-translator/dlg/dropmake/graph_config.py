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
Compatibility shim. The implementation moved to
`dlg.translator.stages.prepare.config` when Tier 1 code was relocated into
`stages/` (issue #16).

`daliuge-engine` imports this module from production code
(`dlg/deploy/create_dlg_job.py`), so the name has to keep resolving. Re-exports
only -- do not add logic here. How long this shim lives is the client team's
release-coordination call.

Note the logger name changed with the module: records that used to be emitted
under `dlg.dlg.dropmake.graph_config` now come from
`dlg.dlg.translator.stages.prepare.config`.
"""

from dlg.translator.errors import (
    GraphConfigException,
    GraphConfigFieldDoesNotExist,
    GraphConfigNodeDoesNotExist,
)
from dlg.translator.stages.prepare.config import (
    ACTIVE_CONFIG_KEY,
    GRAPH_CONFIGS,
    GRAPH_FIELDS,
    GRAPH_NODES,
    apply_active_configuration,
    apply_configuration,
    change_active_configuration,
    crosscheck_ids,
    fill_config,
    find_config_id_from_name,
    get_key_idx_from_list,
    is_config_stored_in_graph,
)

__all__ = [
    "ACTIVE_CONFIG_KEY",
    "GRAPH_CONFIGS",
    "GRAPH_FIELDS",
    "GRAPH_NODES",
    "GraphConfigException",
    "GraphConfigFieldDoesNotExist",
    "GraphConfigNodeDoesNotExist",
    "apply_active_configuration",
    "apply_configuration",
    "change_active_configuration",
    "crosscheck_ids",
    "fill_config",
    "find_config_id_from_name",
    "get_key_idx_from_list",
    "is_config_stored_in_graph",
]
