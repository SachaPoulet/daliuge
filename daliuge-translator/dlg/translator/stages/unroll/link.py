#
#    ICRAR - International Centre for Radio Astronomy Research
#    (c) UWA - The University of Western Australia, 2026
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
"""Physical DROP wiring helpers used during logical-graph unrolling."""

import logging

from dlg.common import CategoryType, dropdict

from dlg.translator.stages.unroll.lg_node import LGNode
from dlg.translator.vocabulary import Categories

logger = logging.getLogger(f"dlg.{__name__}")


class LinkContext:
    """State needed to create physical links for one unrolled graph."""

    def __init__(self, session_id, new_drops):
        self.session_id = session_id
        self.new_drops = new_drops


def _is_stream_link(source_type, target_type):
    stream_types = [
        Categories.COMPONENT,
        Categories.DYNLIB_APP,
        Categories.DYNLIB_PROC_APP,
        Categories.PYTHON_APP,
        Categories.DALIUGE_APP,
    ]
    return source_type in stream_types and target_type in stream_types


def link_drops(
    context: LinkContext,
    slgn: LGNode,
    tlgn: LGNode,
    src_drop: dropdict,
    tgt_drop: dropdict,
    llink: dict,
):
    """Wire two physical DROPs that are not deferred Gather links."""
    if slgn.is_gather:
        sdrop = None
    elif slgn.is_groupby:
        sdrop = src_drop["grp-data_drop"]
    else:
        sdrop = src_drop

    tdrop = tgt_drop
    source_type = slgn.jd["categoryType"]
    target_type = tlgn.jd["categoryType"]

    if _is_stream_link(source_type, target_type):
        bridge_drop = dropdict(
            {
                "oid": "{0}-{1}-stream".format(
                    sdrop["oid"],
                    tdrop["oid"].replace(context.session_id, ""),
                ),
                "categoryType": CategoryType.DATA,
                "dropclass": "dlg.data.drops.data_base.NullDROP",
                "name": "StreamNull",
                "weight": 0,
            }
        )
        sdrop.addOutput(bridge_drop, name="stream")
        bridge_drop.addProducer(sdrop, name="stream")
        bridge_drop.addStreamingConsumer(tdrop, name="stream")
        tdrop.addStreamingInput(bridge_drop, name="stream")
        context.new_drops.append(bridge_drop)

    elif source_type in ["Application", "Control"]:
        logger.debug(
            "Getting source and traget port names and IDs of %s and %s",
            slgn.name,
            tlgn.name,
        )
        source_names = slgn.getPortName("outputPorts", index=-1)
        target_names = tlgn.getPortName("inputPorts", index=-1)

        output_port_name = source_names[llink["fromPort"]]
        input_port_name = target_names[llink["toPort"]]
        sdrop.addOutput(tdrop, name=output_port_name)
        tdrop.addProducer(sdrop, name=input_port_name)

        if "port_map" not in tdrop:
            tdrop["port_map"] = {input_port_name: output_port_name}
        else:
            tdrop["port_map"][input_port_name] = output_port_name

        if Categories.BASH_SHELL_APP == source_type:
            src_drop["command"].add_output_param(tlgn.id, tgt_drop["oid"])
    else:
        source_port_id = llink.get("fromPort")
        source_name = slgn.getPortName("outputPorts", portId=source_port_id)
        target_port_id = llink.get("toPort")
        target_name = tlgn.getPortName("inputPorts", portId=target_port_id)
        logger.debug(
            "Found port names: IN: %s, OUT: %s", source_name, target_name
        )

        if llink.get("is_stream", False):
            logger.debug(
                "link stream connection %s to %s",
                sdrop["oid"],
                tdrop["oid"],
            )
            sdrop.addStreamingConsumer(tdrop, name=source_name)
            tdrop.addStreamingInput(sdrop, name=target_name)
        else:
            sdrop.addConsumer(tdrop, name=source_name)
            tdrop.addInput(sdrop, name=target_name)
        if Categories.BASH_SHELL_APP == target_type:
            tgt_drop["command"].add_input_param(slgn.id, src_drop["oid"])
