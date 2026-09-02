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

import logging

logger = logging.getLogger(f"dlg.{__name__}")


def convert_fields(lgo: dict) -> dict:
    """Convert fields of all logical graph nodes to node attributes

    Args:
        lgo: The logical graph object

    Returns:
        converted logical graph object
    """
    logger.debug("Converting fields")
    nodes = lgo["nodeDataArray"]
    for node in nodes:
        fields = node["fields"]
        node["inputPorts"] = {}
        node["outputPorts"] = {}
        for field in fields:
            name = field.get("name", "")
            if name != "":
                node[name] = field.get("value", "")
                if node[name] == "":
                    node[name] = field.get("defaultValue", "")
    return lgo
