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
    create_from_node,
    has_app_keywords
)


def convert_construct(lgo):
    """
    1. for each scatter/gather, create a "new" application drop, which shares
       the same "id" as the construct
    2. reset the key of the scatter/gather construct to 'new_id'
    3. reset the "parentId" keyword of each drop inside the construct to 'new_id'
    """
    # print('%d nodes in lg' % len(lgo['nodeDataArray']))
    keyset = get_keyset(lgo)
    old_new_grpk_map = dict()
    old_new_gather_map = dict()
    old_newnew_gather_map = dict()
    new_nodes = []

    duplicated_gather_app = dict()  # temmporarily duplicate gather as an extra
    # application drop if a gather has internal input, which will result in
    # a cycle that is not allowed in DAG during graph translation

    # CAUTION: THIS IS VERY LIKELY TO CAUSE ISSUES,
    # SINCE IT IS PICKING THE FIRST ONE FOUND!
    app_keywords = ["inputApplicationType", "outputApplicationType"]
    for node in lgo["nodeDataArray"]:
        if node["category"] not in [
            ConstructTypes.SCATTER,
            ConstructTypes.GATHER,
            ConstructTypes.SERVICE,
        ]:
            continue
        has_app = ""

        # try to find a application using several app_keywords
        # disregard app_keywords that are not present, or have value "None"
        has_app = has_app_keywords(node, app_keywords)
        if not has_app:
            continue

        # step 1
        app_args = {"fields": "inputAppFields"}
        if node["category"] == ConstructTypes.GATHER:
            app_args["group_start"] = 1

        if node["category"] == ConstructTypes.SERVICE:
            app_args["isService"] = True

        app_node = create_from_node(node, node[has_app], app_args)

        # step 2
        new_id = str(uuid.uuid4())
        node["id"] = new_id
        keyset.add(new_id)
        old_new_grpk_map[app_node["id"]] = new_id

        if ConstructTypes.GATHER == node["category"]:
            old_new_gather_map[app_node["id"]] = new_id
            app_node["parentId"] = new_id
            app_node["group_start"] = 1

            # extra step to deal with "internal output" from within Gather
            # dup_app_node_k = min(keyset) - 1
            dup_app_node_k = str(uuid.uuid4())
            keyset.add(dup_app_node_k)
            dup_app_args = {
                "id": dup_app_node_k,
                "fields": "appFields" if "appFields" in node else "inputAppFields",
            }
            tmp_node = create_from_node(
                node=node, category=node[has_app], app_params=dup_app_args
            )
            redundant_keys = ["fields", "reprodata"]
            tmp_node = {k: v for k, v in tmp_node.items() if k not in redundant_keys}
            duplicated_gather_app[new_id] = tmp_node

        new_nodes.append(app_node)

    if new_nodes:
        lgo["nodeDataArray"].extend(new_nodes)

        node_index = _build_node_index(lgo)

        # step 3
        for node in lgo["nodeDataArray"]:
            if "parentId" in node and node["parentId"] in old_new_grpk_map:
                k_old = node["parentId"]
                node["parentId"] = old_new_grpk_map[k_old]

        # step 4
        if old_new_gather_map:
            for link in lgo["linkDataArray"]:
                if link["to"] in old_new_gather_map:
                    k_old = link["to"]
                    new_id = old_new_gather_map[k_old]
                    link["to"] = new_id
                    # TODO Delete everything below this
                    # deal with the internal output from Gather
                    from_node = node_index[link["from"]]
                    # this is an obsolete and awkard way of checking internal output (for backward compatibility)
                    if "parentId" in from_node and from_node["parentId"] == new_id:
                        dup_app_node = duplicated_gather_app[new_id]
                        new_id_new = dup_app_node["id"]
                        link["to"] = new_id_new
                        if new_id_new not in node_index:
                            node_index[new_id_new] = dup_app_node
                            dup_app_node["reprodata"] = (
                                node_index[new_id].get("reprodata", {}).copy()
                            )
                            lgo["nodeDataArray"].append(dup_app_node)
                            old_newnew_gather_map[k_old] = new_id_new

            # step 5
            # relink the connection from gather to its external output if the gather
            # has internal output that has been delt with in Step 4
            for link in lgo["linkDataArray"]:
                if link["from"] in old_new_gather_map:
                    k_old = link["from"]
                    new_id = old_new_gather_map[k_old]
                    to_node = node_index[link["to"]]
                    gather_construct = node_index[new_id]
                    if "parentId" not in to_node and "parentId" not in gather_construct:
                        cond1 = True
                    elif (
                        "parentId" in to_node
                        and "parentId" in gather_construct
                        and to_node["parentId"] == gather_construct["parentId"]
                    ):
                        cond1 = True
                    else:
                        cond1 = False

                    if cond1 and (k_old in old_newnew_gather_map):
                        link["from"] = old_newnew_gather_map[k_old]
                    # print("from %d to %d to %d" % (link['from'], k_old, link['to']))
    # print('%d nodes in lg after construct conversion' % len(lgo['nodeDataArray']))
    return lgo


def _build_node_index(lgo):
    ret = dict()
    for node in lgo["nodeDataArray"]:
        ret[node["id"]] = node

    return ret
