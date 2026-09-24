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
import collections
import datetime
import logging
import time
from itertools import product

from dlg.common import CategoryType, dropdict

from dlg.translator.errors import GraphException
from dlg.translator.stages.prepare.versions import (
    LG_APPREF,
    get_lg_ver_type,
    LG_VER_EAGLE,
    LG_VER_EAGLE_CONVERTED,
)
from dlg.translator.stages.prepare.loader import load_lg
from dlg.translator.stages.prepare.config import apply_active_configuration
from dlg.translator.stages.prepare.normalise.constructs import convert_construct
from dlg.translator.stages.prepare.normalise.fields import convert_fields
from dlg.translator.stages.prepare.normalise.subgraphs import convert_subgraphs
from dlg.translator.stages.prepare.normalise.globals import extract_globals
from dlg.translator.vocabulary import Categories
from dlg.translator.stages.unroll.lg_node import LGNode
from dlg.translator.stages.unroll.coordinate import InstanceId
from dlg.translator.stages.unroll.instantiate import instantiate, lgn_to_pgn
from dlg.translator.stages.unroll.constructs.base import validate_hierarchy
from dlg.translator.stages.unroll.constructs.registry import get_handler_for_node

logger = logging.getLogger(f"dlg.{__name__}")


class LG:
    """
    An object representation of a Logical Graph

    TODO: This is a lot more than just a LG class,
    it is doing all the conversion inside __init__
    """

    def __init__(self, f, ssid=None, apply_config=True):
        """
        parse JSON into LG object graph first
        """
        self._g_var = []
        lg = load_lg(f)
        if ssid is None:
            ts = time.time()
            ssid = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%S")
        self._session_id = ssid
        self._loop_aware_set = set()

        # key - gather drop oid, value - a tuple with two elements
        # input drops list and output drops list
        self._gather_cache = {}

        lgver = get_lg_ver_type(lg)
        logger.info("Loading graph: %s", lg["modelData"]["filePath"])
        logger.info("Found LG version: %s", lgver)

        if apply_config:
            lg = apply_active_configuration(lg)

        if LG_VER_EAGLE == lgver:
            lg = extract_globals(lg)
            lg = convert_fields(lg)
            lg = convert_construct(lg)
            lg = convert_subgraphs(lg)
        elif LG_VER_EAGLE_CONVERTED == lgver:
            lg = convert_construct(lg)
        elif LG_APPREF == lgver:
            lg = convert_fields(lg)
        # This ensures that future schema version mods are catched early
        else:
            raise GraphException(
                "Logical graph version '{0}' not supported!".format(lgver)
            )

        self._done_dict = {}
        self._group_q = collections.defaultdict(list)
        self._output_q = collections.defaultdict(list)
        self._start_list = []
        self._lgn_list = []
        stream_output_ports = {}  # key - port_id, value - construct key
        for jd in lg["nodeDataArray"]:
            lgn = LGNode(jd, self._group_q, self._done_dict, ssid)
            self._lgn_list.append(lgn)
            node_ouput_ports = jd.get("outputPorts", {})
            node_ouput_ports.update(jd.get("outputLocalPorts", {}))
            # check all the outports of this node, and store "stream" output
            if len(node_ouput_ports) > 0:
                for name, out_port in node_ouput_ports.items():
                    if name.lower().endswith("stream"):
                        stream_output_ports[out_port["Id"]] = jd["id"]
        # Need to go through the list again, since done_dict is recursive
        for lgn in self._lgn_list:
            if lgn.is_start and lgn.category not in [
                Categories.COMMENT,
                Categories.DESCRIPTION,
            ]:
                if lgn.category == Categories.VARIABLES:
                    self._g_var.append(lgn)
                else:
                    self._start_list.append(lgn)

        self._lg_links = lg["linkDataArray"]

        for lk in self._lg_links:
            src = self._done_dict[lk["from"]]
            srcPort = lk.get("fromPort", None)
            tgt = self._done_dict[lk["to"]]
            tgtPort = lk.get("toPort", None)
            self.validate_link(src, tgt)
            src.add_output(tgt, srcPort)
            tgt.add_input(src, tgtPort)
            # check stream links
            from_port = lk.get("fromPort", "__None__")
            if stream_output_ports.get(from_port, None) == lk["from"]:
                lk["is_stream"] = True
                logger.debug("Found stream from %s to %s", lk["from"], lk["to"])
            else:
                lk["is_stream"] = False
            if "1" == lk.get("loop_aware", "0"):
                self._loop_aware_set.add("%s-%s" % (lk["from"], lk["to"]))

        # key - lgn id, val - a list of pgns associated with this lgn
        self._drop_dict = collections.defaultdict(list)
        self._reprodata = lg.get("reprodata", {})

    def validate_link(self, src, tgt):
        get_handler_for_node(src).validate_link(src, tgt)
        get_handler_for_node(tgt).validate_link(src, tgt)
        validate_hierarchy(src, tgt)

    def lgn_to_pgn(self, lgn, iid=InstanceId((0,)), lpcxt=None):
        """
        See dlg.translator.stages.unroll.instantiate.lgn_to_pgn
        """
        lgn_to_pgn(self, lgn, iid, lpcxt)

    @staticmethod
    def _split_list(ls, n):
        """
        Yield successive n-sized chunks from l.
        """
        for i in range(0, len(ls), n):
            yield ls[i: i + n]

    def _unroll_gather_as_output(self, slgn, tlgn, sdrops, tdrops, chunk_size, llink):
        if slgn.h_level < tlgn.h_level:
            raise GraphException(
                "Gather {0} has higher h-level than its input {1}".format(
                    tlgn.id, slgn.id
                )
            )
        # src must be data
        for i, chunk in enumerate(self._split_list(sdrops, chunk_size)):
            for sdrop in chunk:
                self._link_drops(slgn, tlgn, sdrop, tdrops[i], llink)

    def _get_chunk_size(self, s, t):
        """
        Assumption:
        s or t cannot be Scatter as Scatter does not convert into DROPs
        """
        if t.is_gather:
            ret = t.gather_width
        elif t.is_groupby:
            ret = t.groupby_width
        else:
            ret = s.dop_diff(t)
        return ret

    def _is_stream_link(self, s_type, t_type):
        return s_type in [
            Categories.COMPONENT,
            Categories.DYNLIB_APP,
            Categories.DYNLIB_PROC_APP,
            Categories.PYTHON_APP,
            Categories.DALIUGE_APP
        ] and t_type in [
            Categories.COMPONENT,
            Categories.DYNLIB_APP,
            Categories.DYNLIB_PROC_APP,
            Categories.PYTHON_APP,
            Categories.DALIUGE_APP
        ]

    def _link_drops(
        self,
        slgn: LGNode,
        tlgn: LGNode,
        src_drop: dropdict,
        tgt_drop: dropdict,
        llink: dict,
    ):
        """ """
        sdrop = None
        if slgn.is_gather:
            # sdrop = src_drop['gather-data_drop']
            pass
        elif slgn.is_groupby:
            sdrop = src_drop["grp-data_drop"]
        else:
            sdrop = src_drop

        if tlgn.is_gather:
            gather_oid = tgt_drop["oid"]
            if gather_oid not in self._gather_cache:
                # [self, input_list, output_list]
                self._gather_cache[gather_oid] = [tgt_drop, [], [], llink]
            self._gather_cache[gather_oid][1].append(sdrop)
            logger.debug(
                "Hit gather, link is from %s to %s", llink["from"], llink["to"]
            )
            return

        tdrop = tgt_drop
        s_type = slgn.jd["categoryType"]
        t_type = tlgn.jd["categoryType"]

        if self._is_stream_link(s_type, t_type):
            # 1. create a null_drop in the middle
            # 2. link sdrop to null_drop
            # 3. link tdrop to null_drop as a streamingConsumer

            dropSpec_null = dropdict(
                {
                    "oid": "{0}-{1}-stream".format(
                        sdrop["oid"],
                        tdrop["oid"].replace(self._session_id, ""),
                    ),
                    "categoryType": CategoryType.DATA,
                    "dropclass": "dlg.data.drops.data_base.NullDROP",
                    "name": "StreamNull",
                    "weight": 0,
                }
            )
            sdrop.addOutput(dropSpec_null, name="stream")
            dropSpec_null.addProducer(sdrop, name="stream")
            dropSpec_null.addStreamingConsumer(tdrop, name="stream")
            tdrop.addStreamingInput(dropSpec_null, name="stream")
            self._drop_dict["new_added"].append(dropSpec_null)

        elif s_type in ["Application", "Control"]:
            logger.debug("Getting source and traget port names and IDs of %s and %s", slgn.name, tlgn.name)
            sname = slgn.getPortName("outputPorts", index=-1)
            tname = tlgn.getPortName("inputPorts", index=-1)

            # sname is dictionary of all output ports on the sDROP.

            output_portname = sname[llink["fromPort"]]
            input_portname = tname[llink["toPort"]]
            sdrop.addOutput(tdrop, name=output_portname)
            tdrop.addProducer(sdrop, name=input_portname)

            if "port_map" not in tdrop:
                tdrop["port_map"] = {input_portname: output_portname}
            else:
                tdrop["port_map"][input_portname] = output_portname

            if Categories.BASH_SHELL_APP == s_type:
                bc = src_drop["command"]
                bc.add_output_param(tlgn.id, tgt_drop["oid"])
        else:
            if slgn.is_gather:  # don't really add them
                gather_oid = src_drop["oid"]
                if gather_oid not in self._gather_cache:
                    # [self, input_list, output_list]
                    self._gather_cache[gather_oid] = [src_drop, [], [], llink]
                self._gather_cache[gather_oid][2].append(tgt_drop)
            else:  # sdrop is a data drop
                # there should be only one port, get the name
                # ^ TODO This comment is no longer true, need to address
                portId = llink["fromPort"] if "fromPort" in llink else None
                sname = slgn.getPortName("outputPorts", portId=portId)
                # could be multiple ports, need to identify
                portId = llink["toPort"] if "toPort" in llink else None
                tname = tlgn.getPortName("inputPorts", portId=portId)
                logger.debug("Found port names: IN: %s, OUT: %s", sname, tname)

                if llink.get("is_stream", False):
                    logger.debug(
                        "link stream connection %s to %s",
                        sdrop["oid"],
                        tdrop["oid"],
                    )
                    sdrop.addStreamingConsumer(tdrop, name=sname)
                    tdrop.addStreamingInput(sdrop, name=tname)

                else:
                    sdrop.addConsumer(tdrop, name=sname)
                    tdrop.addInput(sdrop, name=tname)
            if Categories.BASH_SHELL_APP == t_type:
                bc = tgt_drop["command"]
                bc.add_input_param(slgn.id, src_drop["oid"])

    def unroll_to_tpl(self):
        """
        Not thread-safe!

        1. just create pgn anyway
        2. sort out the links
        """
        instantiate(self)

        logger.debug(
            "Unroll progress - lgn_to_pgn done %d for session %s",
            len(self._start_list),
            self._session_id,
        )
        for lk in self._lg_links:
            sid = lk["from"]  # source key
            tid = lk["to"]  # target key
            slgn = self._done_dict[sid]
            tlgn = self._done_dict[tid]
            sdrops = self._drop_dict[sid]
            tdrops = self._drop_dict[tid]
            chunk_size = self._get_chunk_size(slgn, tlgn)
            if slgn.is_group and not tlgn.is_group:
                # this link must be artifically added (within group link)
                # since
                # 1. GroupBy's "natural" output must be a Scatter (i.e. group)
                # 2. Scatter "naturally" does not have output
                if (
                    slgn.is_gather and tlgn.gid != sid
                ):  # not the artifical link between gather and its own start child
                    # gather iteration case, tgt must be a Group-Start Component
                    # this is a way to manually sequentialise a Scatter that has a high DoP
                    for i, ga_drop in enumerate(sdrops):
                        if ga_drop["oid"] not in self._gather_cache:
                            logger.warning(
                                "Gather %s Drop not yet in cache, sequentialisation may fail!",
                                slgn.name,
                            )
                            continue
                        j = (i + 1) * slgn.gather_width
                        if j >= tlgn.group.dop and j % tlgn.group.dop == 0:
                            continue
                        while j < (i + 2) * slgn.gather_width and j < tlgn.group.dop * (
                            i + 1
                        ):
                            # TODO merge this code into the function
                            # def _link_drops(self, slgn, tlgn, src_drop, tgt_drop, llink)
                            tname = tlgn.getPortName(port="inputPorts")
                            # Go through gather cache list
                            for gddrop in self._gather_cache[ga_drop["oid"]][1]:
                                gddrop.addConsumer(tdrops[j], name=tname)
                                tdrops[j].addInput(gddrop, name=tname)
                                j += 1

                elif slgn.is_subgraph or tlgn.is_subgraph:
                    pass
                else:
                    if len(sdrops) != len(tdrops):
                        err_info = "For within-group links, # {2} Group Inputs {0} must be the same as # {3} of Component Outputs {1}".format(
                            slgn.id, tlgn.id, len(sdrops), len(tdrops)
                        )
                        raise GraphException(err_info)
                    for i, sdrop in enumerate(sdrops):
                        self._link_drops(slgn, tlgn, sdrop, tdrops[i], lk)
            elif slgn.is_group and tlgn.is_group:
                # slgn must be GroupBy and tlgn must be Gather
                self._unroll_gather_as_output(
                    slgn, tlgn, sdrops, tdrops, chunk_size, lk
                )
            elif not slgn.is_group and (not tlgn.is_group):
                if slgn.is_start_node:
                    continue
                if (
                    (slgn.group is not None)
                    and slgn.group.is_loop
                    and slgn.gid == tlgn.gid
                    and slgn.is_group_end
                    and tlgn.is_group_start
                ):
                    # Re-link to the next iteration's start
                    lsd = len(sdrops)
                    if lsd != len(tdrops):
                        raise GraphException(
                            "# of sdrops '{0}' != # of tdrops '{1}'for Loop '{2}'".format(
                                slgn.name, tlgn.name, slgn.group.name
                            )
                        )
                    # first add the outer construct (scatter, gather, group-by) boundary
                    loop_chunk_size = slgn.group.dop
                    for i, chunk in enumerate(
                        self._split_list(sdrops, loop_chunk_size)
                    ):
                        for j, sdrop in enumerate(chunk):
                            if j < loop_chunk_size - 1:
                                self._link_drops(
                                    slgn,
                                    tlgn,
                                    sdrop,
                                    tdrops[i * loop_chunk_size + j + 1],
                                    lk,
                                )
                elif (
                    slgn.group is not None
                    and slgn.group.is_loop
                    and tlgn.group is not None
                    and tlgn.group.is_loop
                    and (not slgn.h_related(tlgn))
                ):
                    # stepwise locking for links between two Loops
                    for sdrop, tdrop in product(sdrops, tdrops):
                        if sdrop["loop_ctx"] == tdrop["loop_ctx"]:
                            self._link_drops(slgn, tlgn, sdrop, tdrop, lk)
                else:
                    lpaw = ("%s-%s" % (sid, tid)) in self._loop_aware_set
                    if (
                        slgn.group is not None
                        and slgn.group.is_loop
                        and lpaw
                        and slgn.h_level > tlgn.h_level
                    ):
                        loop_iter = slgn.group.dop
                        for i, chunk in enumerate(self._split_list(sdrops, chunk_size)):
                            for j, sdrop in enumerate(chunk):
                                # only link drops in the last loop iteration
                                if j % loop_iter == loop_iter - 1:
                                    self._link_drops(slgn, tlgn, sdrop, tdrops[i], lk)
                    elif (
                        tlgn.group is not None
                        and tlgn.group.is_loop
                        and lpaw
                        and slgn.h_level < tlgn.h_level
                    ):
                        loop_iter = tlgn.group.dop
                        for i, chunk in enumerate(self._split_list(tdrops, chunk_size)):
                            for j, tdrop in enumerate(chunk):
                                # only link drops in the first loop iteration
                                if j % loop_iter == 0:
                                    self._link_drops(slgn, tlgn, sdrops[i], tdrop, lk)

                    elif slgn.h_level >= tlgn.h_level:
                        for i, chunk in enumerate(self._split_list(sdrops, chunk_size)):
                            # distribute slgn evenly to tlgn
                            for sdrop in chunk:
                                self._link_drops(slgn, tlgn, sdrop, tdrops[i], lk)
                    else:
                        for i, chunk in enumerate(self._split_list(tdrops, chunk_size)):
                            # distribute tlgn evenly to slgn
                            for tdrop in chunk:
                                self._link_drops(slgn, tlgn, sdrops[i], tdrop, lk)
            else:  # slgn is not group, but tlgn is group
                if tlgn.is_groupby:
                    grpby_dict = collections.defaultdict(list)
                    layer_index = tlgn.group_by_scatter_layers[1]
                    for gdd in sdrops:
                        src_ctx = gdd["iid"].split("-")
                        if tlgn.group_keys is None:
                            # the last bit of iid (current h id) is the local GrougBy key, i.e. inner most loop context id
                            gby = src_ctx[-1]
                            if (
                                slgn.h_level - 2 == tlgn.h_level and tlgn.h_level > 0
                            ):  # groupby itself is nested inside a scatter
                                # group key consists of group context id + inner most loop context id
                                gctx = "-".join(src_ctx[0:-2])
                                gby = f"{gctx}-{gby}"
                        else:
                            # find the "group by" scatter level
                            gbylist = []
                            if slgn.group.is_groupby:  # a chain of group bys
                                try:
                                    src_ctx = gdd["iid"].split("$")[1].split("-")
                                except IndexError as e:
                                    raise GraphException(
                                        "The group by hiearchy in the multi-key group by '{0}' is not specified for node '{1}'".format(
                                            slgn.group.name, slgn.name
                                        )
                                    ) from e
                            else:
                                src_ctx.reverse()
                            for lid in layer_index:
                                gbylist.append(src_ctx[lid])
                            gby = "-".join(gbylist)
                        grpby_dict[gby].append(gdd)
                    grp_keys = grpby_dict.keys()
                    if len(grp_keys) != len(tdrops):
                        # this happens when groupby itself is nested inside a scatter
                        raise GraphException(
                            "# of Group keys {0} != # of Group Drops {1} for LGN {2}".format(
                                len(grp_keys), len(tdrops), tlgn.id
                            )
                        )
                    grp_keys = sorted(grp_keys)
                    for i, gk in enumerate(grp_keys):
                        grpby_drop = tdrops[i]
                        drop_list = grpby_dict[gk]
                        for drp in drop_list:
                            self._link_drops(slgn, tlgn, drp, grpby_drop, lk)
                            # drp.addOutput(grpby_drop)
                            # grpby_drop.addInput(drp)
                elif tlgn.is_gather:
                    self._unroll_gather_as_output(
                        slgn, tlgn, sdrops, tdrops, chunk_size, lk
                    )
                elif tlgn.is_subgraph:
                    pass
                else:
                    raise GraphException(
                        "Unsupported target group {0}".format(tlgn.jd.category)
                    )

        for _, v in self._gather_cache.items():
            input_list = v[1]
            try:
                output_drop = v[2][0]  # "peek" the first element of the output list
            except IndexError:
                continue  # the gather hasn't got output drops, just move on
            llink = v[-1]
            for data_drop in input_list:
                # TODO merge this code into the function
                # def _link_drops(self, slgn, tlgn, src_drop, tgt_drop, llink)
                sname = slgn.getPortName(ports="outputPorts")
                if llink.get("is_stream", False):
                    logger.debug(
                        "link stream connection %s to %s",
                        data_drop["oid"],
                        output_drop["oid"],
                    )
                    data_drop.addStreamingConsumer(output_drop, name=sname)
                    output_drop.addStreamingInput(data_drop, name=sname)
                else:
                    data_drop.addConsumer(output_drop, name=sname)
                    output_drop.addInput(data_drop, name=sname)

        logger.info(
            "Unroll progress - %d links done for session %s",
            len(self._lg_links),
            self._session_id,
        )

        # clean up extra drops
        for lid, lgn in self._done_dict.items():
            if (lgn.is_start_node) and lid in self._drop_dict:
                del self._drop_dict[lid]
            elif lgn.is_start_listener:
                for sl_drop in self._drop_dict[lid]:
                    if "listener_drop" in sl_drop:
                        del sl_drop["listener_drop"]
            elif lgn.is_groupby:
                for sl_drop in self._drop_dict[lid]:
                    if "grp-data_drop" in sl_drop:
                        del sl_drop["grp-data_drop"]
            elif lgn.is_gather:
                del self._drop_dict[lid]
            elif lgn.is_subgraph:
                # Remove the SubGraph construct drop
                if lgn.jd["isSubGraphConstruct"]:
                    del self._drop_dict[lid]
                else:
                    pass

        logger.info(
            "Unroll progress - extra drops done for session %s",
            self._session_id,
        )
        ret = []
        for drop_list in self._drop_dict.values():
            ret += drop_list

        return ret

    @property
    def reprodata(self):
        return self._reprodata
