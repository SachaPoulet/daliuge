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
Compatibility shim. Every function that lived here moved into the stage that
owns its transition when Tier 1 code was relocated into `stages/` (issue #16):

    fill, apply_config, fill_config  -> stages/prepare/
    unroll                           -> stages/unroll/stage.py
    partition, known_algorithms      -> stages/partition/stage.py
    resource_map                     -> stages/map/stage.py

Nothing is implemented here any more. Re-exports only -- do not add logic.

Note the logger name changed with the code: records formerly emitted under
`dlg.dlg.dropmake.pg_generator` now come from the stage module that owns the
function.
"""


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
from dlg.translator.stages.map.stage import resource_map

# pylint: enable=unused-import

__all__ = [
    "apply_config",
    "fill",
    "fill_config",
    "known_algorithms",
    "partition",
    "resource_map",
    "unroll",
]
