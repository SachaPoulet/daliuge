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
Compatibility shim. The implementations moved to
`dlg.translator.stages.partition.scheduler` when Tier 1 code was relocated into
`stages/` (issue #16).

Unlike the other shims in this package, this one exists for the **documentation
build**, not for daliuge-engine: `docs/api/dropmake.rst` carries an
`automodule:: dlg.dropmake.scheduler` directive, which fails to import without
it. No production code outside the translator imports this module.

Re-exports only -- do not add logic here.

`DEBUG` is deliberately not re-exported. It is an int, so a copy here would not
track the real module: setting `dlg.dropmake.scheduler.DEBUG` would rebind only
this name and silently fail to enable anything. Reach for
`dlg.translator.stages.partition.scheduler.DEBUG` instead.

Note the logger name changed with the module: records formerly emitted under
`dlg.dlg.dropmake.scheduler` now come from
`dlg.dlg.translator.stages.partition.scheduler`.
"""

from dlg.translator.stages.partition.scheduler import (
    DAGUtil,
    KFamilyPartition,
    MinNumPartsScheduler,
    MySarkarScheduler,
    Partition,
    PSOScheduler,
    Schedule,
    Scheduler,
    SchedulerException,
)

__all__ = [
    "DAGUtil",
    "KFamilyPartition",
    "MinNumPartsScheduler",
    "MySarkarScheduler",
    "PSOScheduler",
    "Partition",
    "Schedule",
    "Scheduler",
    "SchedulerException",
]
