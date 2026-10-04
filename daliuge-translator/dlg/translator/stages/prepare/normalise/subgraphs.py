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

import uuid

from dlg.translator.vocabulary import ConstructTypes
from dlg.translator.stages.prepare.normalise._helpers import (
    get_keyset,
    has_app_keywords,
    create_from_node,
)


def convert_subgraphs(lgo: dict) -> dict:
    """
    Identify any first-order SubGraph constructs in the Logical Graph, and exctract the
    InputApp and OutputApp fields.

    The steps involved in converting subgraphs are:
    1. Identify and extract the input and output applications from the subgraph construct
    2. Create nodes for both
    4. Re-order links to ensure output app is connected to final data output of subgraph
    5. Extract the subgraph from the current graph LGT and store in a separate input data
        node to the Input Python Application (SubGraph dropclass)
    6. Remove subgraph from current graph

    Note: This will update the logical_graph in-place, but we explicitly return
    the logical_graph to make it clear that it is updated.

    :param lgo: dict, logical Graph
    :return: dict, modified Logical Graph
    """

    keyset = get_keyset(lgo)
    old_new_grpk_map = dict()
    old_new_subgraph_map = {}
    new_nodes = []

    app_keywords = ["inputApplicationType", "outputApplicationType"]
    for node in lgo["nodeDataArray"]:
        if node["category"] != ConstructTypes.SUBGRAPH:
            continue

        node["isSubGraphConstruct"] = True
        node["hasInputApp"] = True
        if not has_app_keywords(node, app_keywords, requires_all=True):
            node["hasInputApp"] = False
            continue

        # Construct nodes
        app_node, out_node = _build_apps_from_subgraph_construct(node)

        # Connect output node to rest of graph
        lgo = _identify_and_connect_output_input(app_node, out_node, lgo)
        out_node["parentId"] = app_node["id"]
        new_nodes.extend([app_node, out_node])

        # Update group mappings and bump key
        new_id = str(uuid.uuid4())
        node["id"] = new_id
        keyset.add(new_id)
        old_new_grpk_map[app_node["id"]] = new_id

        # Replace the keys based on new input and output apps.
        if new_nodes:
            old_new_subgraph_map[app_node["id"]] = new_id
            lgo["nodeDataArray"].extend(new_nodes)

            lgo = _update_keys(old_new_grpk_map, lgo)

            # Manage SubGraph nodes and links
            subgraphNodes, subgraphLinks, lgo = _extract_subgraph_nodes(
                app_node, out_node, lgo
            )

            # Create SubGraph as InputData to the SubGraph Input App
            new_id = str(uuid.uuid4())
            keyset.add(new_id)
            subgraph = {
                "nodeDataArray": list(subgraphNodes.values()),
                "linkDataArray": subgraphLinks,
                "modelData": lgo["modelData"],
            }
            for n in lgo["nodeDataArray"]:
                if n["id"] == app_node["id"]:
                    app_node["subgraph"] = subgraph

    return lgo


def _identify_and_connect_output_input(
    input_node: dict, out_node: dict, logical_graph: dict
) -> dict:
    """
    # If the link is to a node that _isn't_ in the subgraph group
    # then it is an output node,  so check that group is either
    # non-existent, or not equal to the subgraph group.

    Note: This will update the logical_graph in-place, but we explicitly return
    the logical_graph to make it clear that it is updated.

    :param input_node: Input Application node to the subgraph
    :param out_node: Output Application node to the subgraph
    :param logical_graph: The input logical graph (template)
    :return: logical_graph: the updated logical_graph
    """

    for link in logical_graph["linkDataArray"]:
        if link["to"] == input_node["id"]:
            for n in logical_graph["nodeDataArray"]:

                if n["id"] == link["from"]:
                    try:
                        if n["parentId"] == input_node["parentId"]:
                            link["to"] = out_node["id"]
                    except KeyError:
                        pass
        if link["from"] == input_node["id"]:
            for n in logical_graph["nodeDataArray"]:
                if n["id"] == link["to"]:
                    try:
                        if n["parentId"] != input_node["parentId"]:
                            link["from"] = out_node["id"]
                    except KeyError:
                        link["from"] = out_node["id"]
    return logical_graph


def _build_apps_from_subgraph_construct(subgraph_node: dict) -> tuple[dict, dict]:
    """
    Initialise the input and output apps based on the subgraph construct node

    :param subgraph_node: The SubGraph construct node on the graph, that contains the
    input and output nodes.
    :return: The input and output nodes
    """

    input_app_args = {
        "isSubGraphApp": True,
        "isSubGraphConstruct": False,
        "SubGraphGroupKey": subgraph_node["id"],
        "parentId": subgraph_node["id"],
        "group_start": 1,
        "fields": "inputAppFields",
        "inputApp": True,
    }

    input_node = create_from_node(
        subgraph_node, subgraph_node["inputApplicationType"], input_app_args
    )

    output_app_args = {
        "id": subgraph_node["outputApplicationId"],
        "isSubGraphApp": True,
        "isSubGraphConstruct": False,
        "SubGraphGroupKey": input_node["id"],
        "parentId": input_node["id"],
        "group_start": 1,
        "fields": "outputAppFields",
        "outputApp": True,
    }
    output_node = create_from_node(
        subgraph_node, subgraph_node["outputApplicationType"], output_app_args
    )

    return input_node, output_node


def _update_keys(old_new_grpk_map: dict, lgo: dict) -> dict:
    """
    Iterate through the group keys and replace them based on updated
    logical graph structure

    Note: This will update the logical_graph in-place, but we explicitly return
    the logical_graph to make it clear that it is updated.

    :param old_new_grpk_map: old-new map of group keys, where old is the existing group
    key from the original logical graph template construct, and new is the new group key
    based on the InputApp.
    :param lgo: logical graph template
    :return: the updated logical graph template
    """

    for n in lgo["nodeDataArray"]:
        if "parentId" in n and n["parentId"] in old_new_grpk_map:
            k_old = n["parentId"]
            n["parentId"] = old_new_grpk_map[k_old]

    return lgo


def _extract_subgraph_nodes(
    input_node: dict, out_node: dict, logical_graph: dict
) -> tuple[dict, list, dict]:
    """
    1. Identify the SubGraph nodes that are not from the Construct
    2. Find the data inputs to the outputApp
    3. Remove the subgraph nodes (besides the input into the outputapp) from the
       main graph
    4. Create links from the subgraph output to input/output applications

    :param input_node: Input Application node to the subgraph
    :param out_node: Output Application node to the subgraph
    :param logical_graph: The input logical graph (template)
    :return: subgraphNodes: Dictionary of nodes in the subgraph
             subgraphLinks: List of links in the subgraph
             logical_graph: The modified logical_graph
    """
    subgraphNodes = {}
    subgraphLinks = []
    construct_apps = {input_node["id"], out_node["id"]}

    # 1. Identifying subgraph nodes that are not the input/ouput app
    for n in logical_graph["nodeDataArray"]:
        if (
            "parentId" in n
            and n["parentId"] == input_node["parentId"]
            and n["id"] not in construct_apps
        ):
            subgraphNodes[n["id"]] = n

    output_links: dict = {}

    for link in logical_graph["linkDataArray"]:
        if link["from"] in subgraphNodes:
            # Find links from inside the SubGraph to the Output App to preserve
            if link["to"] in construct_apps:
                key = subgraphNodes[link["from"]]
                output_links[key["id"]] = {}
                output_links[key["id"]]["node"] = key
                output_links[key["id"]]["link"] = link
            subgraphLinks.append(link)
        if link["to"] in subgraphNodes.keys() and link not in subgraphLinks:
            subgraphLinks.append(link)

    for e in subgraphNodes.values():
        if e["id"] not in output_links:
            logical_graph["nodeDataArray"].remove(e)
    for e in subgraphLinks:
        logical_graph["linkDataArray"].remove(e)

    # Ensure we aren't linking from the Input/Output app into the subgraph
    # Any nodes outside the subgraph won't exist when it is deployed.
    subgraphLinks = [
        link for link in subgraphLinks if (link["from"] not in construct_apps)
    ]
    subgraphLinks = [
        link for link in subgraphLinks if (link["to"] not in construct_apps)
    ]
    # 4. Create links from the subgraph output data to input/output applications

    for n in output_links.values():
        logical_graph["linkDataArray"].append(
            {"to": n["node"]["id"], "from": input_node["id"]}
        )
        logical_graph["linkDataArray"].append(n["link"])

    return subgraphNodes, subgraphLinks, logical_graph
