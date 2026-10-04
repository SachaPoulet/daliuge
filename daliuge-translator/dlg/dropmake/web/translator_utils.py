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
`dlg.translator.web.translator_utils` when `web/` was relocated out of
`dropmake/` (issue #21).

`daliuge-engine` imports this module from production code
(`graph_compatibility.py`) and from `test/end_to_end/deploy/
test_graph_to_manager.py`, which also gates itself on
`pytest.importorskip("dlg.dropmake.web.translator_utils")` -- so the module
must import cleanly, not merely exist. Both consumers want
`unroll_and_partition_with_params` and `prepare_lgt`; proposal 7.1 treats that
as contract. Re-exports only -- do not add logic here.

`ALGO_PARAMS` is re-exported as the same list object, so the two names stay in
sync under mutation. They would not stay in sync under rebinding: assigning to
`dlg.dropmake.web.translator_utils.ALGO_PARAMS` replaces only this name and
leaves the real module untouched. Nothing does that today; if you need to,
reach for `dlg.translator.web.translator_utils.ALGO_PARAMS`.

Note the logger name changed with the module: records formerly emitted under
`dlg.dlg.dropmake.web.translator_utils` now come from
`dlg.dlg.translator.web.translator_utils`.
"""

# pylint: disable=unused-import
from dlg.translator.web.translator_utils import (
    ALGO_PARAMS,
    file_as_string,
    filter_dict_to_algo_params,
    get_mgr_deployment_methods,
    lg_exists,
    lg_path,
    lg_repo_contents,
    make_algo_param_dict,
    parse_mgr_url,
    prepare_lgt,
    pgt_exists,
    pgt_path,
    pgt_repo_contents,
    unroll_and_partition_with_params,
)

# pylint: enable=unused-import

__all__ = [
    "ALGO_PARAMS",
    "file_as_string",
    "filter_dict_to_algo_params",
    "get_mgr_deployment_methods",
    "lg_exists",
    "lg_path",
    "lg_repo_contents",
    "make_algo_param_dict",
    "parse_mgr_url",
    "pgt_exists",
    "pgt_path",
    "pgt_repo_contents",
    "prepare_lgt",
    "unroll_and_partition_with_params",
]
