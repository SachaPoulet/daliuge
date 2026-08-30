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

LG_VER_OLD = 1
LG_VER_EAGLE_CONVERTED = 2
LG_VER_EAGLE = 3
LG_APPREF = "AppRef"


def get_lg_ver_type(lgo):
    """
    Get the version type of this logical graph
    """
    # with open(lg_name, 'r+') as file_object:
    #     lgo = json.load(file_object)

    nodes = lgo["nodeDataArray"]
    if len(nodes) == 0:
        raise Exception("Invalid LG, nodes not found")

    # First check whether modelData and schemaVersion is in graph
    if (
        "modelData" in lgo
        and len(lgo["modelData"]) > 0
        and "schemaVersion" in lgo["modelData"]
    ):
        if lgo["modelData"]["schemaVersion"] != "OJS":
            return lgo["modelData"]["schemaVersion"]

    # else do the old stuff...
    for i, node in enumerate(nodes):
        if i > 5:
            break
        if "fields" in node:
            fds = node["fields"]
            for fd in fds:
                if "name" in fd:
                    kw = fd["name"]
                    if kw in node and kw not in ["description"]:
                        return LG_VER_EAGLE_CONVERTED
                    else:
                        return LG_VER_EAGLE

    if "linkDataArray" in lgo and len(lgo["linkDataArray"]) > 0:
        lnk = lgo["linkDataArray"][0]
        if "fromPort" not in lnk:
            return LG_VER_OLD
        if lnk["fromPort"] in ["B", "T", "R", "L"]:
            # only the old lg links can be Bottom, Top, Right and Left
            return LG_VER_OLD
        else:
            return LG_VER_EAGLE_CONVERTED
    else:
        if "copiesArrayObjects" in lgo or "copiesArrays" in lgo:
            return LG_VER_EAGLE_CONVERTED
        else:
            return LG_VER_OLD
