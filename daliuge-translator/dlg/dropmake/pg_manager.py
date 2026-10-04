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
Compatibility shim. The implementation moved to `dlg.translator.web.pg_manager`
when `web/` was relocated out of `dropmake/` (issue #21).

**Temporary -- delete this file in P2b-3.** Like `dlg.dropmake.scheduler`, this
shim exists for the *documentation build*, not for daliuge-engine: nothing
outside the translator imports `pg_manager`, and inside it only
`web/translator_rest.py` does, already repointed at the real module. What keeps
the file alive is `automodule:: dlg.dropmake.pg_manager` in
`docs/api/dropmake.rst`, and `build-documentation` runs Sphinx with `-W`, so a
missing module fails the job. P2b-3 repoints that directive at
`dlg.translator.web.pg_manager`; the moment it does, this file has no consumer
left and should go with it.

The docs do keep rendering real content through this shim, contrary to the
warning in the issue plan's P2b-3 section: `automodule` consults `__all__`
first, so the names below are documented despite being imported, and
`api/dropmake.html` shows `PGManager`, `PGUtil` and their methods exactly as
before the move. Measured, not assumed -- `dlg.dropmake.scheduler` and
`dlg.dropmake.pg_generator` render 31 and 6 members through the same
mechanism. Drop `__all__` from a shim and that stops being true.

So this file is deletable in P2b-3 because the directive moves, not because it
is documenting nothing today.

Re-exports only -- do not add logic here.
"""

# pylint: disable=unused-import
from dlg.translator.web.pg_manager import (
    MAX_PGT_FN_CNT,
    PGManager,
    PGUtil,
)

# pylint: enable=unused-import

__all__ = ["MAX_PGT_FN_CNT", "PGManager", "PGUtil"]
