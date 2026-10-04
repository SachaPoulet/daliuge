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
from dlg.translator.stages.unroll.instantiate import (
    instantiate,
    lgn_to_pgn,
    synthesise_links,
)
from dlg.translator.stages.unroll.wire import wire
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

        0. add the artificial links constructs need (synthesise_links)
        1. create every drop, no edges (instantiate)
        2. wire every link (wire); only stream NullDROPs are created here
        3. clean up the construct placeholder drops
        """
        synthesise_links(self)
        instantiate(self)

        logger.debug(
            "Unroll progress - lgn_to_pgn done %d for session %s",
            len(self._start_list),
            self._session_id,
        )
        wire(self)

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
