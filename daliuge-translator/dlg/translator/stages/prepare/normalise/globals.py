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

from typing import Callable


def extract_globals(logical_graph: dict):
    """
    Extract variables defined in the GlobalVariableDROP and replace them across the
    graph. Once all globals are extracted/replaced, we remove the GlobalVariableDrop from
    the Logical Graph.

    :param logical_graph:
    :return:
    """
    type_converter: dict[str, Callable] = {
        "Integer": int,
        "Float": float,
        "String": str,
        "Boolean": lambda x: x.lower() in ("true", "1")
    }

    global_nodes = [
        node
        for node in logical_graph["nodeDataArray"]
        if node["category"] == "GlobalVariable"
    ]

    # Remove all globals from graph
    for gn in global_nodes:
        logical_graph["nodeDataArray"].remove(gn)

    global_map = {}
    for gn in global_nodes:
        for fields in gn["fields"]:
            global_map[fields["name"]] = {
                'value': fields["value"],
                'type': fields['type']
            }

    for node in logical_graph["nodeDataArray"]:
        for field in node['fields']:
            for gn, gv in global_map.items():
                if isinstance(field['value'], str) and f"{{{gn}}}" in field["value"]:
                    if gv['type'] in type_converter:
                        converter = type_converter[gv['type']]
                    else:
                        raise ValueError(f"Unknown field type '{gv['type']}' in globals")
                    field['type'] = gv['type']
                    field['value'] = converter(field['value'].replace(
                        f"{{{gn}}}", str(gv['value'])
                    ))

    return logical_graph
