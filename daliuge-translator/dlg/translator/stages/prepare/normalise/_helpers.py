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
Helpers for normalisers.
"""


def get_keyset(lgo):
    return set([x["id"] for x in lgo["nodeDataArray"]])


def create_from_node(node: dict, category: str, app_params: dict) -> dict:
    """
    Create a new dictionary from the node based on the category of the new drop, and any
    specific attributes for the application

    The follow node attributes will be setup by default for new nodes:
    - 'reprodata'
    - "id"
    - group (conditional)
    - fields (conditional)

    Conditional attributes will be based on their existence in the existing node.

    Any alternatives to the defaults above, or non-default attributes, can be addressed
    by the app_params.

    :param node: The node from which we are deriving the new application
    :param category: The category of the new dictionary
    :param app_params: dict, any non-generic
    :return: new_node: dict, node based on the existing node
    """
    new_node = {}
    new_node["reprodata"] = node.get("reprodata", {}).copy()
    new_node["id"] = node["id"]
    new_node["category"] = category

    new_node["name"] = node["text"] if "text" in node else node["name"]

    if "parentId" in node:
        new_node["parentId"] = node["parentId"]

    if "fields" in app_params:
        field = app_params.pop("fields")
        if field in node:
            new_node["fields"] = list(node[field])
            new_node["fields"] += node["fields"]
            for afd in node[field]:
                new_node[afd["name"]] = afd["value"]

    # Construct-specific mapping behaviour
    for key, value in app_params.items():
        new_node[key] = value

    return new_node


def has_app_keywords(node: dict, keywords: list, requires_all: bool = False) -> str:
    """
    Check if a single or all keywords exist in the Logical Graph node.

    Default behaviour will return the first keyword that exists in the keywords list.

    :param node: Logical Graph construct node
    :param keywords: keywords we want to check
    :param requires_all: bool, If True, this will return the last keyword if it is exists,
    otherwise it will return None.
    :return: app: the application name
    """

    app = ""
    for ak in keywords:
        if ak in node and node[ak] != "None" and node[ak] != "UnknownApplication":
            if not requires_all:
                return ak
            app = ak
        else:
            if requires_all:
                return ""
    return app
