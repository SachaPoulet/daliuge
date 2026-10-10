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
# These passes were lifted out of LG.unroll_to_tpl and still work on LG's
# own state, until the handler contexts replace it.
# pylint: disable=protected-access
import logging

import numpy as np

from dlg.translator.errors import GInvalidNode
from dlg.translator.stages.unroll.constructs.registry import (
    get_handler_for_node,
    is_construct,
)
from dlg.translator.stages.unroll.coordinate import InstanceId
from dlg.translator.vocabulary import Categories

logger = logging.getLogger(f"dlg.{__name__}")


class _HandlerInstantiationContext:
    """Expose legacy LG state through the handler instantiation interface."""

    def __init__(self, lg, loop_context=None):
        self._lg = lg
        self.session_id = lg._session_id
        self.loop_context = loop_context

    def node(self, node_id):
        return self._lg._done_dict[node_id]

    def drops_of(self, node_id):
        return self._lg._drop_dict[node_id]

    def add_drop(self, node_id, drop):
        self._lg._drop_dict[node_id].append(drop)


def synthesise_links(lg):
    """
    Append the artificial links of every construct reachable from
    lg._start_list to lg._lg_links.

    These links are appended after LG.__init__ has processed the graph's own
    links, so they never pass through validate_link, never get "is_stream"
    stamped and never enter _loop_aware_set. They reach wiring as bare
    {"from", "to"} dicts.

    The walk visits a construct once per instance of its enclosing
    construct, as lgn_to_pgn does, so a nested construct appends its links
    more than once. Wiring does not deduplicate them, and the repeated links
    show up as repeated consumers/inputs in the PGT; keep the walk as is
    until that is fixed on purpose (migration map B9).
    """
    for lgn in lg._start_list:
        _synthesise(lg, lgn)


def _synthesise(lg, lgn):
    if not lgn.is_group:
        return
    if not is_construct(lgn, Categories.SCATTER):
        non_inputs = []
        grp_starts = []
        grp_ends = []
        for child in lgn.children:
            if len(child.inputs) == 0:
                non_inputs.append(child)
            if child.is_group_start:
                grp_starts.append(child)
            elif child.is_group_end:
                grp_ends.append(child)
        if len(grp_starts) == 0:
            gs_list = non_inputs
        else:
            gs_list = grp_starts
        if is_construct(lgn, Categories.LOOP):
            if len(grp_starts) == 0 or len(grp_ends) == 0:
                raise GInvalidNode(
                    f"Loop {lgn.name} should have at least one Start "
                    "Component and one End Data"
                )
            for ge in grp_ends:
                for gs in grp_starts:  # make an artificial circle
                    lk = {}
                    if gs not in ge.outputs:
                        ge.add_output(gs)
                    if ge not in gs.inputs:
                        gs.add_input(ge)
                    lk["from"] = ge.id
                    lk["to"] = gs.id
                    lg._lg_links.append(lk)
                    logger.debug("Loop constructed: %s", gs.inputs)
        else:
            for (
                gs
            ) in (
                gs_list
            ):  # add artificial logical links to the "first" children
                lgn.add_input(gs)
                gs.add_output(lgn)
                lk = {}
                lk["from"] = lgn.id
                lk["to"] = gs.id
                lg._lg_links.append(lk)

    for _ in range(lgn.dop):
        for child in lgn.children:
            _synthesise(lg, child)


def instantiate(lg):
    """
    Create the drops of every node reachable from lg._start_list into
    lg._drop_dict.
    """
    for lgn in lg._start_list:
        lgn_to_pgn(lg, lgn)


def get_child_lp_ctx(lgn, lpcxt, idx):
    if is_construct(lgn, Categories.LOOP):
        if lpcxt is None:
            return "{0}".format(idx)
        else:
            return "{0}-{1}".format(lpcxt, idx)
    else:
        return None


def lgn_to_pgn(lg, lgn, iid=InstanceId((0,)), lpcxt=None):
    """
    convert a logical graph node to physical graph node(s)
    without considering pg links. This is a recursive method, creating also
    all child nodes required by constructs.

    iid:    instance id (InstanceId)
    lpcxt:  Loop context
    """
    if lgn.is_group:
        multikey_grpby = False
        lgk = lgn.group_keys
        shape = []
        if lgk is not None and len(lgk) > 1:
            multikey_grpby = True
            # inner most scatter to outer most scatter
            scatters = lgn.group_by_scatter_layers[2]
            # inner most is also the slowest running index
            shape = [x.dop for x in scatters]

        for i in range(lgn.dop):
            miid = iid.child(i)
            if multikey_grpby:
                # set up more refined hierarchical context for group by with multiple keys
                # recover multl-dimension indexes from i
                grp_h = tuple(int(x) for x in np.unravel_index(i, shape))
                miid = miid.with_group_key(grp_h)

            if is_construct(lgn, Categories.SERVICE):
                context = _HandlerInstantiationContext(lg, lpcxt)
                handler = get_handler_for_node(lgn)
                for src_drop in handler.instantiate(lgn, miid, context):
                    context.add_drop(lgn.id, src_drop)
            elif not is_construct(lgn, Categories.SCATTER) and not is_construct(
                lgn, Categories.LOOP
            ):
                # make GroupBy and Gather drops
                src_drop = lgn.make_single_drop(miid)
                lg._drop_dict[lgn.id].append(src_drop)
                if is_construct(lgn, Categories.GROUP_BY):
                    lg._drop_dict["new_added"].append(src_drop["grp-data_drop"])
                elif is_construct(lgn, Categories.GATHER):
                    pass
                    # lg._drop_dict['new_added'].append(src_drop['gather-data_drop'])
            for child in lgn.children:
                lgn_to_pgn(lg, child, miid, get_child_lp_ctx(lgn, lpcxt, i))
    elif is_construct(lgn, Categories.MPI):
        for i in range(lgn.dop):
            miid = iid.child(i)
            src_drop = lgn.make_single_drop(miid, loop_ctx=lpcxt, proc_index=i)
            lg._drop_dict[lgn.id].append(src_drop)
    elif is_construct(lgn, Categories.SERVICE):
        # no action required, inputapp node aleady created and marked with "isService"
        pass
    elif is_construct(lgn, Categories.SUBGRAPH) and lgn.jd.get(
        "isSubGraphApp", False
    ):
        src_drop = lgn.make_single_drop(iid, loop_ctx=lpcxt)
        if lgn.subgraph:
            kwargs = {"subgraph": lgn.subgraph}
            src_drop.update(kwargs)
        lg._drop_dict[lgn.id].append(src_drop)
    else:
        src_drop = lgn.make_single_drop(iid, loop_ctx=lpcxt)
        lg._drop_dict[lgn.id].append(src_drop)
        if lgn.is_start_listener:
            lg._drop_dict["new_added"].append(src_drop["listener_drop"])
