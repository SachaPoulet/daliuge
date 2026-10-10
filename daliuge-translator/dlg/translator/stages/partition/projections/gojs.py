#
#    ICRAR - International Centre for Radio Astronomy Research
#    (c) UWA - The University of Western Australia, 2026
#    Copyright by UWA (in the framework of the ICRAR)
#    All rights reserved
#

"""Read-only GoJS projection for partition graphs."""

from dlg.common import CategoryType


def project_gojs(drop_list, extra_drops, links):
    """Build the GoJS graph model without mutating the partition graph."""

    nodes = []

    for index, drop in enumerate(drop_list):
        node = {
            "key": index + 1,
            "oid": drop["oid"],
            "name": drop["name"],
            "iid": drop.get("iid", 0),
        }

        category_type = drop["categoryType"]
        if category_type == CategoryType.DATA:
            node["category"] = "Data"
        elif category_type == CategoryType.APPLICATION:
            node["category"] = "Application"

        nodes.append(node)

    for index, drop in enumerate(extra_drops):
        node = {
            "key": (index + 1) * -1,
            "oid": drop["oid"],
            "name": drop["name"],
            "iid": drop.get("iid", 0),
        }

        category_type = drop["categoryType"]
        if category_type == CategoryType.DATA:
            node["category"] = "Data"
        elif category_type == CategoryType.APPLICATION:
            node["category"] = "PythonApp"

        nodes.append(node)

    return {
        "class": "go.GraphLinksModel",
        "nodeDataArray": nodes,
        "linkDataArray": links,
    }
