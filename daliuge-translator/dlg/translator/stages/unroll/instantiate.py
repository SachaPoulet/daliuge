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
import copy
import logging

import numpy as np

from dlg.translator.errors import GInvalidNode
from dlg.translator.stages.unroll.coordinate import InstanceId

logger = logging.getLogger(f"dlg.{__name__}")


def instantiate(lg):
    """
    Create the drops of every node reachable from lg._start_list into
    lg._drop_dict.
    """
    for lgn in lg._start_list:
        lgn_to_pgn(lg, lgn)


def get_child_lp_ctx(lgn, lpcxt, idx):
    if lgn.is_loop:
        if lpcxt is None:
            return "{0}".format(idx)
        else:
            return "{0}-{1}".format(lpcxt, idx)
    else:
        return None


def lgn_to_pgn(lg, lgn, iid=InstanceId((0,)), lpcxt=None, recursive=True):
    """
    convert a logical graph node to physical graph node(s)
    without considering pg links. This is a recursive method, creating also
    all child nodes required by constructs.

    iid:    instance id (InstanceId)
    lpcxt:  Loop context
    """
    if lgn.is_group:
        # group nodes are replaced with the input application of the
        # construct
        if not lgn.is_scatter:
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
            if lgn.is_loop:
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

            if not lgn.is_scatter and not lgn.is_loop:
                # make GroupBy and Gather drops
                src_drop = lgn.make_single_drop(miid)
                lg._drop_dict[lgn.id].append(src_drop)
                if lgn.is_groupby:
                    lg._drop_dict["new_added"].append(src_drop["grp-data_drop"])
                elif lgn.is_gather:
                    pass
                    # lg._drop_dict['new_added'].append(src_drop['gather-data_drop'])
            if recursive:
                for child in lgn.children:
                    lgn_to_pgn(lg, child, miid, get_child_lp_ctx(lgn, lpcxt, i))
            else:
                for child in lgn.children:
                    # Approach next 'set' of children
                    c_copy = copy.deepcopy(child)
                    c_copy.happy = True
                    c_copy.loop_ctx = get_child_lp_ctx(lgn, lpcxt, i)
                    c_copy.iid = miid
                    lg._start_list.append(c_copy)
    elif lgn.is_mpi:
        for i in range(lgn.dop):
            if lgn.loop_ctx:
                lpcxt = lgn.loop_ctx
                iid = lgn.iid
            miid = iid.child(i)
            src_drop = lgn.make_single_drop(miid, loop_ctx=lpcxt, proc_index=i)
            lg._drop_dict[lgn.id].append(src_drop)
    elif lgn.is_service:
        # no action required, inputapp node aleady created and marked with "isService"
        pass
    elif lgn.is_subgraph and lgn.jd["isSubGraphApp"]:
        if lgn.loop_ctx:
            iid = lgn.iid
        src_drop = lgn.make_single_drop(iid, loop_ctx=lpcxt)
        if lgn.subgraph:
            kwargs = {"subgraph": lgn.subgraph}
            src_drop.update(kwargs)
        lg._drop_dict[lgn.id].append(src_drop)
    else:
        if lgn.loop_ctx or lgn.iid:
            lpcxt = lgn.loop_ctx
            iid = lgn.iid
        src_drop = lgn.make_single_drop(iid, loop_ctx=lpcxt)
        lg._drop_dict[lgn.id].append(src_drop)
        if lgn.is_start_listener:
            lg._drop_dict["new_added"].append(src_drop["listener_drop"])
