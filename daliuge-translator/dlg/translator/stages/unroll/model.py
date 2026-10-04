import logging
import re
from dataclasses import dataclass
from typing import Optional

from dlg.common import CategoryType, dropdict
from dlg.translator.errors import GInvalidNode
from dlg.translator.vocabulary import APP_TYPES, DATA_TYPES, Categories

from .constructs.registry import get_handler_for_node, is_construct

logger = logging.getLogger(f"dlg.{__name__}")


class LGNode:
    """Core logical-graph node state and structural behavior."""

    def __init__(self, jd, group_q, done_dict, ssid):
        """
        jd: json_dict (dict)
        group_q: group queue (defaultdict)
        done_dict: LGNode that have been processed (Dict)
        ssid:   session id (string)
        """
        self.id = jd["id"]
        self.jd = jd
        self.group_q = group_q
        self.group = None
        self._children = []
        self._ssid = ssid
        self.is_app = self.jd["categoryType"] == CategoryType.APPLICATION
        self.is_data = self.jd["categoryType"] == CategoryType.DATA
        self.weight = 1
        self._converted = False
        self._h_level = None
        self._g_h = None
        self._dop = None
        self._gaw = None
        self._grpw = None
        self._inputs = []
        self._outputs = []
        self.dropclass = ""
        self.reprodata = jd.get("reprodata", {}).copy()
        if "isGroup" in jd and jd["isGroup"] is True:
            self.is_group = True
            for wn in group_q[self.id]:
                wn.group = self
                self.add_child(wn)
            group_q.pop(self.id)
        else:
            self.is_group = False

        if "parentId" in jd:
            grp_id = jd["parentId"]
            if grp_id in done_dict:
                grp_nd = done_dict[grp_id]
                self.group = grp_nd
                grp_nd.add_child(self)
            else:
                group_q[grp_id].append(self)

        done_dict[self.id] = self
        self.subgraph = jd["subgraph"] if "subgraph" in jd else None
        self.happy = False
        self.loop_ctx = None
        self.iid = None
        self.input_ports = self.getPortName(ports="inputPorts", index=-1)
        self.output_ports = self.getPortName(ports="outputPorts", index=-1)

    @property
    def input_ports(self):
        return self._input_ports

    @input_ports.setter
    def input_ports(self, value):
        self._input_ports = value

    @property
    def output_ports(self):
        return self._output_ports

    @output_ports.setter
    def output_ports(self, value):
        self._output_ports = value

    @property
    def reprodata(self):
        return self._reprodata

    @reprodata.setter
    def reprodata(self, value):
        self._reprodata = value

    @property
    def jd(self):
        return self._jd

    @jd.setter
    def jd(self, node_json):
        if "categoryType" not in node_json:
            if node_json["category"] in APP_TYPES:
                node_json["categoryType"] = CategoryType.APPLICATION
            elif node_json["category"] in DATA_TYPES:
                node_json["categoryType"] = CategoryType.DATA
            else:
                raise GInvalidNode(
                    f"Node '{node_json.get('name')}' ({self.id}) has category "
                    f"'{node_json['category']}' and no categoryType."
                )
        self._jd = node_json

    @property
    def is_group(self):
        return self._is_group

    @is_group.setter
    def is_group(self, value):
        self._is_group = value

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, value):
        self._id = value

    @property
    def name(self):
        return self.jd.get("name", "")

    @property
    def category(self):
        return self._jd.get("category", "Unknown")

    @property
    def categoryType(self):
        return self.jd.get("categoryType", "Unknown")

    @property
    def group(self):
        return self._grp

    @group.setter
    def group(self, value):
        self._grp = value

    def add_output(self, lg_node, srcPort=None):
        if lg_node not in self._outputs:
            self._outputs.append(lg_node)
        if self.jd.get("outputPorts") and srcPort is not None and srcPort in self.jd["outputPorts"]:
            self.jd["outputPorts"][srcPort]["target_id"] = lg_node.id

    def add_input(self, lg_node, tgtPort=None):
        if lg_node not in self._inputs:
            self._inputs.append(lg_node)
        if self.jd.get("inputPorts") and tgtPort is not None and tgtPort in self.jd["inputPorts"]:
            self.jd["inputPorts"][tgtPort]["source_id"] = lg_node.id

    def add_child(self, lg_node):
        """Add a member to this group."""
        if lg_node.is_group:
            handler = get_handler_for_node(lg_node)
            if handler.construct_type not in (
                Categories.SCATTER,
                Categories.LOOP,
                Categories.GROUP_BY,
            ):
                raise GInvalidNode(
                    "Only Scatters, Loops and GroupBys can be nested, but {0} is neither".format(
                        lg_node.id
                    )
                )
        self._children.append(lg_node)

    @property
    def children(self):
        return self._children

    @property
    def outputs(self):
        return self._outputs

    @property
    def inputs(self):
        return self._inputs

    @property
    def h_level(self):
        if self._h_level is None:
            _level = 0
            cg = self
            while cg.group is not None:
                cg = cg.group
                _level += 1
            if is_construct(self, Categories.MPI):
                _level += 1
            self._h_level = _level
        return self._h_level

    @property
    def group_hierarchy(self):
        if self._g_h is None:
            glist = []
            cg = self
            while cg.group is not None:
                glist.append(str(cg.group.id))
                cg = cg.group
            glist.append("0")
            self._g_h = "-".join(reversed(glist))
        return self._g_h

    @property
    def weight(self):
        return self._weight

    @weight.setter
    def weight(self, default_value):
        """Set a data node's volume or an app node's execution time."""
        key = []
        if self.is_app:
            key = [k for k in self.jd if re.match(r"execution[\s\_]time", k.lower())]
        elif self.is_data:
            key = [k for k in self.jd if re.match(r"data[\s\_]volume", k.lower())]
        try:
            self._weight = int(self.jd[key[0]])
        except (KeyError, ValueError, IndexError):
            self._weight = int(default_value)

    @property
    def is_data(self):
        return self._is_data

    @is_data.setter
    def is_data(self, value):
        self._is_data = value

    @property
    def is_app(self):
        return self._is_app

    @is_app.setter
    def is_app(self, value):
        self._is_app = value

    @property
    def is_start(self):
        return self.group is None

    @property
    def is_dag_root(self):
        leng = len(self.inputs)
        if leng > 1:
            return False
        elif leng == 0:
            if self.category == Categories.START:
                return False
            else:
                return True
        elif self.is_start:
            return True
        else:
            return False

    @property
    def is_start_listener(self):
        """Whether this node is a socket listener node."""
        return (
            len(self.inputs) == 1
            and self.category == Categories.START
            and self.is_data
        )

    @property
    def is_group_start(self):
        """Whether this node starts its group."""
        result = False
        if self.group is not None and (
            "group_start" in self.jd
            or "Group start" in self.jd
            or "Group Start" in self.jd
        ):
            gs = (
                self.jd.get("group_start", False)
                if "group_start" in self.jd
                else self.jd.get("Group start", False)
            )
            if isinstance(gs, bool):
                result = gs
            elif isinstance(gs, (float, int)):
                result = 1 == gs
            elif isinstance(gs, str):
                result = gs.lower() in ("true", "1")
        return result

    @property
    def is_group_end(self):
        """Whether this node ends its group."""
        result = False
        if self.group is not None and (
            "group_end" in self.jd or "Group end" in self.jd or "Group End" in self.jd
        ):
            ge = (
                self.jd.get("group_end", False)
                if "group_end" in self.jd
                else self.jd.get("Group end", False)
            )
            if isinstance(ge, bool):
                result = ge
            elif isinstance(ge, (float, int)):
                result = 1 == ge
            elif isinstance(ge, str):
                result = ge.lower() in ("true", "1")
        return result

    def getPortName(self, ports: str = "outputPorts", index: int = 0, portId=None):
        """Return port names or the name matching a port id."""
        port_selector = {
            "inputPorts": ["InputPort", "InputOutput"],
            "outputPorts": ["OutputPort", "InputOutput"],
        }
        ports_dict = {}
        name = None
        if ports in port_selector:
            for field in self.jd["fields"]:
                if "usage" not in field:
                    continue
                if field["usage"] in port_selector[ports]:
                    if portId is None or field["id"] == portId:
                        name = field["name"]
                    if field["id"] not in ports_dict:
                        ports_dict[field["id"]] = name
        logger.debug("Ports: %s; name: %s; index: %d", ports_dict, name, index)
        return name if index >= 0 else ports_dict


@dataclass(frozen=True)
class LogicalLink:
    source: "LGNode"
    target: "LGNode"
    source_port: Optional[str] = None
    target_port: Optional[str] = None
    is_stream: bool = False
    loop_aware: bool = False


@dataclass(frozen=True)
class Edge:
    link: LogicalLink
    source: dropdict
    target: dropdict
