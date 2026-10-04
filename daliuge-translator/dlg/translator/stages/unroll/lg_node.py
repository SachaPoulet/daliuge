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

import json
import logging
import random

from dlg.translator.stages.unroll.constructs.registry import (
    get_handler_for_node,
    is_construct,
)
from dlg.translator.stages.unroll.model import LGNode as LGNodeModel
from dlg.common import CategoryType
from dlg.common import dropdict
from dlg.translator.errors import (
    GraphException,
    GInvalidNode,
)
from dlg.translator.vocabulary import Categories
from dlg.translator.stages.unroll.coordinate import InstanceId

logger = logging.getLogger(f"dlg.{__name__}")


class LGNode(LGNodeModel):

    def __str__(self):
        return self.name

    @property
    def nodetype(self):
        return self._nodetype

    @nodetype.setter
    def nodetype(self, value):
        self._nodetype = value

    @property
    def dropclass(self):
        return self._dropclass

    @dropclass.setter
    def dropclass(self, default_value):
        self.is_data = False
        self.is_app = False
        keys = []
        value = None
        if default_value is None or len(default_value) == 0:
            default_value = "dlg.apps.simple.SleepApp"
        if self.jd["categoryType"] == CategoryType.DATA:
            self.is_data = True
            keys = [
                "dropclass",
                "Data class",
                "dataclass",
            ]
        elif self.jd["categoryType"] == CategoryType.APPLICATION:
            keys = [
                "dropclass",
                "Application Class",
                "Application class",
                "appclass",
            ]
            self.is_app = True
        elif self.jd["categoryType"] in [
            CategoryType.CONSTRUCT,
            CategoryType.CONTROL,
        ]:
            keys = ["inputApplicationName"]
        elif self.jd["categoryType"] in ["Other"]:
            value = "Other"
        else:
            logger.error("Found unknown categoryType: %s", self.jd["categoryType"])
            # raise ValueError
        for key in keys:
            if key in self.jd:
                value = self.jd[key]
                break
            if value is None or value == "":
                value = default_value

        self._dropclass = value

    def has_group(self):
        return self.group is not None

    def has_converted(self):
        return self._converted

    def complete_conversion(self):
        self._converted = True

    @property
    def gid(self):
        if self.group is None:
            return 0
        else:
            return self.group.id

    @property
    def has_child(self):
        return len(self._children) > 0

    @property
    def has_output(self):
        return len(self._outputs) > 0

    @property
    def is_start_node(self):
        return self.jd["category"] == Categories.START

    @property
    def is_end_node(self):
        return self.jd["category"] == Categories.END

    @property
    def group_keys(self):
        """
        Return:
            None or a list of keys (each key is an integer)
        """
        if not is_construct(self, Categories.GROUP_BY):
            return None
        val = str(self.jd.get("group_key", "None"))
        if val in ["None", "-1", ""]:
            return None
        else:
            try:
                return [int(x) for x in val.split(",")]
            except ValueError as ve:
                raise GraphException(
                    "group_key must be an integer or comma-separated integers: {0}".format(
                        ve
                    )
                ) from ve

    @property
    def gather_width(self):
        """
        Gather width
        """
        if is_construct(self, Categories.GATHER):
            if self._gaw is None:
                try:
                    self._gaw = int(self.jd["num_of_inputs"])
                except KeyError:
                    self._gaw = 1
            return self._gaw
        else:
            # TODO: use OO style to replace all type-related statements!
            return None

    @property
    def groupby_width(self):
        """
        GroupBy count
        """
        if is_construct(self, Categories.GROUP_BY):
            if self._grpw is None:
                tlgn = self.inputs[0]
                re_dop = 1
                cg = tlgn.group  # exclude its own group
                while cg.has_group():
                    re_dop *= cg.group.dop
                    cg = cg.group
                self._grpw = re_dop
            return self._grpw
        else:
            return None

    @property
    def group_by_scatter_layers(self):
        """
        Return:
            scatter layers info associated with this group by logical node
            A tuple of three items:
                (1) DoP
                (2) layer indexes (list) from innser scatter to outer scatter
                (3) layers (list)
        """
        if not is_construct(self, Categories.GROUP_BY):
            return None

        tlgn = self.inputs[0]
        grpks = self.group_keys
        ret_dop = 1
        layer_index = []  # from inner to outer
        layers = []  # from inner to outer
        c = 0
        if is_construct(tlgn.group, Categories.GROUP_BY):
            # group by followed by another group by
            if grpks is None or len(grpks) < 1:
                raise GInvalidNode(
                    "Must specify group_key for Group By '{0}'".format(self.name)
                )
            # find the "root" groupby and get all of its scatters
            inputgrp = self
            while (inputgrp is not None) and is_construct(
                inputgrp.inputs[0].group, Categories.GROUP_BY
            ):
                inputgrp = inputgrp.inputs[0].group
            # inputgrp now is the "root" groupby that follows Scatter immiately
            # move it to Scatter
            inputgrp = inputgrp.inputs[0].group
            # go thru all the scatters
            while (inputgrp is not None) and is_construct(inputgrp, Categories.SCATTER):
                if inputgrp.id in grpks:
                    ret_dop *= inputgrp.dop
                    layer_index.append(c)
                    layers.append(inputgrp)
                inputgrp = inputgrp.group
                c += 1
        else:
            if grpks is None or len(grpks) < 1:
                ret_dop = tlgn.group.dop
                layer_index.append(0)
                layers.append(tlgn.group)
            else:
                if len(grpks) == 1:
                    if grpks[0] == tlgn.group.id:
                        ret_dop = tlgn.group.dop
                        layer_index.append(0)
                        layers.append(tlgn.group)
                    else:
                        raise GInvalidNode(
                            "Wrong single group_key for {0}".format(self.name)
                        )
                else:
                    inputgrp = tlgn.group
                    # find the "groupby column list" from all layers of scatter loops
                    while (inputgrp is not None) and is_construct(
                        inputgrp, Categories.SCATTER
                    ):
                        if inputgrp.id in grpks:
                            ret_dop *= inputgrp.dop
                            layer_index.append(c)
                            layers.append(inputgrp)
                        inputgrp = inputgrp.group
                        c += 1

        return ret_dop, layer_index, layers

    @property
    def dop(self):
        """
        Degree of Parallelism: integer
        default: 1
        """
        if self._dop is None:
            handler = get_handler_for_node(self)
            self._dop = handler.degree_of_parallelism(self)

        return self._dop

    def dop_diff(self, that_lgn):
        """
        TODO: This does not belong in the LGNode class

        dop difference between inner node/group and outer group
        e.g for each outer group, how many instances of inner nodes/groups
        """
        # if (self.is_group() or that_lgn.is_group()):
        #     raise GraphException("Cannot compute dop diff between groups.")
        # don't check h_related for efficiency since it should have been checked
        # if (self.h_related(that_lgn)):
        il = self.h_level
        al = that_lgn.h_level
        if il == al:
            return 1
        elif il > al:
            oln = that_lgn
            iln = self
        else:
            iln = that_lgn
            oln = self
        re_dop = 1
        cg = iln
        init_cond = cg.gid != oln.gid and cg.has_group()
        while init_cond or is_construct(cg, Categories.MPI):
            if is_construct(cg, Categories.MPI):
                re_dop *= cg.dop
            # else:
            if init_cond:
                re_dop *= cg.group.dop
            cg = cg.group
            if cg is None:
                break
            init_cond = cg.gid != oln.gid and cg.has_group()
        return re_dop
        # else:
        #     pass
        # raise GInvalidLink("{0} and {1} are not hierarchically related".format(self.id, that_lgn.id))

    def h_related(self, that_lgn):
        """
        TODO: This does not belong in the LGNode class
        """
        that_gh = that_lgn.group_hierarchy
        this_gh = self.group_hierarchy
        if len(that_gh) + len(this_gh) <= 1:
            # at least one is at the root level
            return True

        return that_gh.find(this_gh) > -1 or this_gh.find(that_gh) > -1

    def make_oid(self, iid=InstanceId((0,))):
        """
        return:
            ssid_id_iid (string), where
            ssid:   session id
            id:     logical graph node key
            iid:    instance id (for the physical graph node)
        """
        # TODO: This is rather ugly, but a quick and dirty fix. The iid is the rank data we need
        rank = list(iid.path)
        return "{0}_{1}_{2}".format(self._ssid, self.id, str(iid)), rank

    def _update_key_value_attributes(self, kwargs):
        """
        get all the arguments from new fields dictionary in a backwards compatible way
        """
        kwargs["applicationArgs"] = {}
        kwargs["constraintParams"] = {}
        kwargs["componentParams"] = {}
        if "fields" in self.jd:
            kwargs["fields"] = self.jd["fields"]
            for je in self.jd["fields"]:
                # The field to be used is not the text, but the name field
                self.jd[je["name"]] = je["value"]
                kwargs[je["name"]] = je["value"]
                if "parameterType" in je:
                    if je["parameterType"] == "ApplicationArgument":
                        kwargs["applicationArgs"].update({je["name"]: je})
                    elif je["parameterType"] == "ConstraintParameter":
                        kwargs["constraintParams"].update({je["name"]: je})
                    elif je["parameterType"] == "ComponentParameter":
                        kwargs["componentParams"].update({je["name"]: je})

        # NOTE: drop Argxx keywords

    def _create_groupby_drops(self, drop_spec):
        drop_spec.update(
            {
                "dropclass": "dlg.apps.simple.SleepApp",
                "categoryType": "Application",
            }
        )
        sij = self.inputs[0]
        if not sij.is_data:
            raise GInvalidNode(
                "GroupBy should be connected to a DataDrop, not '%s'" % sij.category
            )
        dw = sij.weight * self.groupby_width

        # additional generated drop
        dropSpec_grp = dropdict(
            {
                "oid": "{0}-grp-data".format(drop_spec["oid"]),
                "categoryType": CategoryType.DATA,
                "dropclass": "dlg.data.drops.memory.InMemoryDROP",
                "name": "grpdata",
                "weight": dw,
                "rank": drop_spec["rank"],
                "reprodata": self.jd.get("reprodata", {}),
            }
        )
        kwargs = {}
        kwargs["grp-data_drop"] = dropSpec_grp
        kwargs["weight"] = 1  # barrier literarlly takes no time for its own computation
        kwargs["sleep_time"] = 1
        drop_spec.update(kwargs)
        drop_spec.addOutput(dropSpec_grp, name="grpdata")
        dropSpec_grp.addProducer(drop_spec, name="grpdata")
        return drop_spec

    def _create_gather_drops(self, drop_spec):
        drop_spec.update(
            {
                "dropclass": "dlg.apps.simple.SleepApp",
                "categoryType": "Application",
            }
        )
        gi = self.inputs[0]
        if is_construct(gi, Categories.GROUP_BY):
            gii = gi.inputs[0]
            dw = int(gii.jd["data_volume"]) * gi.groupby_width * self.gather_width
        else:  # data
            dw = gi.weight * self.gather_width

            # additional generated drop
        dropSpec_gather = dropdict(
            {
                "oid": "{0}-gather-data".format(drop_spec["oid"]),
                "categoryType": CategoryType.DATA,
                "dropclass": "dlg.data.drops.memory.InMemoryDROP",
                "name": "gthrdt",
                "weight": dw,
                "rank": drop_spec["rank"],
                "reprodata": self.jd.get("reprodata", {}),
            }
        )
        kwargs = {}
        kwargs["gather-data_drop"] = dropSpec_gather
        kwargs["weight"] = 1
        kwargs["sleep_time"] = 1
        drop_spec.update(kwargs)
        drop_spec.addOutput(dropSpec_gather, name="gthrdata")
        dropSpec_gather.addProducer(drop_spec, name="gthrdata")
        return drop_spec

    def _create_listener_drops(self, drop_spec):
        # create socket listener DROP first
        drop_spec.update(
            {
                "oid": drop_spec["oid"],
                "categoryType": CategoryType.DATA,
                "dropclass": "dlg.data.drops.memory.InMemoryDROP",
            }
        )

        # additional generated drop
        dropSpec_socket = dropdict(
            {
                "oid": "{0}-s".format(drop_spec["oid"]),
                "categoryType": CategoryType.APPLICATION,
                "category": "DALiuGEApp",
                "dropclass": "dlg.apps.simple.SleepApp",
                "name": "lstnr",
                "weigth": 5,
                "sleep_time": 1,
                "reprodata": self.jd.get("reprodata", {}),
            }
        )
        # tw -- task weight
        dropSpec_socket["autostart"] = 1
        drop_spec.update({"listener_drop": dropSpec_socket})
        dropSpec_socket.addOutput(
            drop_spec, name=self.getPortName(ports="outputPorts")
        )
        return drop_spec

    def _create_app_drop(self, drop_spec):
        # default generic component becomes "sleep and copy"
        kwargs = {}
        if "appclass" in self.jd:
            app_class = self.jd["appclass"]
        elif self.dropclass is None or self.dropclass == "":
            logger.debug("No dropclass found in: %s", self)
            app_class = "dlg.apps.simple.SleepApp"
        else:
            app_class = self.dropclass
        if self.dropclass == "dlg.apps.simple.SleepApp":
            if self.category == "BashShellApp":
                app_class = "dlg.apps.bash_shell_app.BashShellApp"
            elif self.category == "Docker":
                app_class = "dlg.apps.dockerapp.DockerApp"
                drop_spec["name"] = self.jd["command"]
            else:
                logger.debug(
                    "Might be a problem with this node: %s",
                    json.dumps(self.jd, indent=2),
                )

        self.dropclass = app_class
        self.jd["dropclass"] = app_class
        self.dropclass = app_class
        logger.debug(
            "Creating app drop using class: %s, %s",
            app_class,
            drop_spec["name"],
        )
        if self.dropclass is None or self.dropclass == "":
            logger.warning("Something wrong with this node: %s", self.jd)
        if self.weight is not None:
            if self.weight < 0:
                raise GraphException(
                    f"Execution_time must be greater than 0 for Node {self.name}",
                )
            else:
                kwargs["weight"] = self.weight
        else:
            kwargs["weight"] = random.randint(3, 8)
        if app_class == "dlg.apps.simple.SleepApp":
            kwargs["sleep_time"] = self.weight

        kwargs["dropclass"] = app_class
        kwargs["num_cpus"] = int(self.jd.get("num_cpus", 1))
        drop_spec.update(kwargs)

        return drop_spec

    def _create_data_drop(self, drop_spec):
        # backwards compatibility
        kwargs = {}
        if "dataclass" in self.jd:
            self.dropclass = self.jd["dataclass"]
        # Backwards compatibility
        if (
            not hasattr(self, "dropclass")
            or self.dropclass == "dlg.apps.simple.SleepApp"
        ):
            if self.category == "File":
                self.dropclass = "dlg.data.drops.file.FileDROP"
            elif self.category == "Memory":
                self.dropclass = "dlg.data.drops.memory.InMemoryDROP"
            elif self.category == "SharedMemory":
                self.dropclass = "dlg.data.drops.memory.SharedMemoryDROP"
            elif self.category == "S3":
                self.dropclass = "dlg.data.drops.s3_drop.S3DROP"
            elif self.category == "NGAS":
                self.dropclass = "dlg.data.drops.ngas.NgasDROP"
            else:
                raise TypeError("Unknown dropclass for drop: {str(self.jd)}")
        logger.debug("Creating data drop using class: %s", self.dropclass)
        kwargs["dropclass"] = self.dropclass
        kwargs["weight"] = self.weight
        if self.is_start_listener:
            drop_spec = self._create_listener_drops(drop_spec)
        drop_spec.update(kwargs)
        return drop_spec

    def make_single_drop(self, iid=InstanceId((0,)), **kwargs):
        """
        make only one drop from a LG nodes
        one-one mapping

        Dummy implementation as of 09/12/15
        """
        if is_construct(self, Categories.LOOP):
            return {}

        oid, rank = self.make_oid(iid)
        # default spec
        drop_spec = dropdict(
            {
                "oid": oid,
                "name": self.name,
                "categoryType": self.categoryType,
                "category": self.category,
                "dropclass": self.dropclass,
                "storage": self.category,
                "rank": rank,
                "reprodata": self.jd.get("reprodata", {}),
            }
        )
        drop_spec.update(kwargs)
        if self.is_data:
            drop_spec = self._create_data_drop(drop_spec)
        elif self.is_app:
            drop_spec = self._create_app_drop(drop_spec)
        elif self.category == Categories.GROUP_BY:
            drop_spec = self._create_groupby_drops(drop_spec)
        elif self.category == Categories.GATHER:
            drop_spec = self._create_gather_drops(drop_spec)
        elif is_construct(self, Categories.SERVICE) or is_construct(
            self, Categories.BRANCH
        ):
            kwargs["categoryType"] = "Application"
            self.jd["categoryType"] = "Application"
            drop_spec = self._create_app_drop(drop_spec)
        self._update_key_value_attributes(kwargs)
        kwargs["iid"] = str(iid)
        kwargs["lg_key"] = self.id
        if is_construct(self, Categories.BRANCH):
            kwargs["categoryType"] = "Application"
        kwargs["name"] = self.name
        # Behaviour is that child-nodes inherit reproducibility data from their parents.
        if self._reprodata is not None:
            kwargs["reprodata"] = self._reprodata.copy()
        drop_spec.update(kwargs)
        return drop_spec

    @staticmethod
    def str_to_bool(value, default_value=False):
        res = True if value in ["1", "true", "True", "yes"] else default_value
        return res
