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
Compatibility shim. `LG` moved to `dlg.translator.stages.unroll.lg` when Tier 1
code was relocated into `stages/` (issue #16).

`daliuge-engine` imports this module (`test/dlg_end_to_end_utils.py`), which
proposal 7.1 treats as contract. Re-exports only -- do not add logic here.

`GraphException` and `load_lg` are re-exported to preserve this module's exact
pre-move import surface, but neither was ever defined here: `lg.py` imported
both for its own use and callers picked them up incidentally. Their real homes
are `dlg.translator.errors` and `dlg.translator.stages.prepare.loader` -- new
code should import them from there, not from this shim.

Note the logger name changed with the module: records formerly emitted under
`dlg.dlg.dropmake.lg` now come from `dlg.dlg.translator.stages.unroll.lg`.
"""

from dlg.translator.errors import GraphException
from dlg.translator.stages.prepare.loader import load_lg
from dlg.translator.stages.unroll.lg import LG

__all__ = ["LG", "GraphException", "load_lg"]
