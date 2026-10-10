"""Gather sequentialisation.

No corpus graph reaches the sequentialisation branch, so these graphs are built
from SuperBasicScatterGather: the Gather loses its input application and links
back to a group-start application inside the Scatter it gathers.
"""

import collections
import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from dlg.common import dropdict
from dlg.translator.stages.unroll import wire as wire_module
from dlg.translator.stages.unroll.constructs.registry import is_construct
from dlg.translator.stages.unroll.lg import LG
from dlg.translator.stages.unroll.link import LinkContext
from dlg.translator.vocabulary import Categories


TEST_SSID = "gather-sequentialisation"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BASE_GRAPH = (
    REPOSITORY_ROOT
    / "test"
    / "corpus"
    / "graphs"
    / "eagle-test-graphs"
    / "SuperBasicScatterGather.graph"
)

SCATTER_ID = "3b1d3054-b9db-4442-a99b-2ad9eafd8f0a"
GATHER_ID = "ef2d6860-b3d0-428b-8b7d-0c5031a33e4b"
FILE_ID = "80559d50-8759-44a7-8fd2-40dc48b741df"
START_ID = "sequentialised-start"
OUTER_ID = "outer-scatter"

# name -> (scatter dop, gather width, outer scatter dop or None)
CASES = {
    "top_level_even": (4, 2, None),
    "top_level_uneven_3_2": (3, 2, None),
    "top_level_uneven_5_2": (5, 2, None),
    "width_equals_dop": (4, 4, None),
    "nested_even_2x4": (4, 2, 2),
    "nested_even_3x4": (4, 2, 3),
    "nested_uneven_2x5": (5, 2, 2),
}


def _field(name, value, value_type):
    return {
        "name": name,
        "value": value,
        "parameterType": "ComponentParameter",
        "type": value_type,
    }


def sequentialisation_graph(dop, width, outer_dop=None):
    """Return a logical graph whose Gather sequentialises its Scatter.

    The Scatter has ``dop`` copies of a File; the Gather collects them in
    chunks of ``width`` and links back to a group-start PythonApp inside the
    Scatter. With ``outer_dop``, the Scatter is nested in an outer Scatter
    and the Gather stays at the top level.
    """
    with open(BASE_GRAPH, encoding="utf-8") as graph_file:
        graph = json.load(graph_file)
    nodes = {node["id"]: node for node in graph["nodeDataArray"]}

    nodes[SCATTER_ID]["fields"] = [_field("num_of_copies", dop, "Integer")]

    gather = nodes[GATHER_ID]
    gather["fields"] = [_field("num_of_inputs", width, "Integer")]
    gather["inputApplicationType"] = "None"
    gather["inputApplicationId"] = None
    gather.pop("inputApplicationName", None)

    # Copy the File for its EAGLE bookkeeping keys, then make it an app.
    start = copy.deepcopy(nodes[FILE_ID])
    start.update(
        {
            "id": START_ID,
            "name": "start",
            "category": "PythonApp",
            "categoryType": "Application",
            "parentId": SCATTER_ID,
            "fields": [
                _field("group_start", True, "Boolean"),
                _field("dropclass", "dlg.apps.simple.SleepApp", "String"),
            ],
        }
    )
    graph["nodeDataArray"].append(start)
    graph["linkDataArray"].append(
        {"from": GATHER_ID, "to": START_ID, "loop_aware": "0"}
    )

    if outer_dop is not None:
        outer = copy.deepcopy(nodes[SCATTER_ID])
        outer.update(
            {
                "id": OUTER_ID,
                "name": "outer",
                "inputApplicationId": OUTER_ID + "-app",
                "fields": [_field("num_of_copies", outer_dop, "Integer")],
            }
        )
        graph["nodeDataArray"].append(outer)
        nodes[SCATTER_ID]["parentId"] = OUTER_ID

    return graph


def sequentialisation_lg(dop, width, outer_dop=None):
    return LG(sequentialisation_graph(dop, width, outer_dop), ssid=TEST_SSID)


def chained_edges(lg):
    """Unroll ``lg`` and return each chained edge as (File iid, start iid)."""
    lg.unroll_to_tpl()
    iids = {
        drop["oid"]: drop["iid"]
        for drops in lg._drop_dict.values()
        for drop in drops
        if "iid" in drop
    }
    # "ports" has one shape whether or not the edge carries a port name.
    return sorted(
        (iids[port["oid"]], start["iid"])
        for start in lg._drop_dict[START_ID]
        for port in start.get("ports", [])
        if port["direction"] == "input"
    )


# Edges the translator produced before the branch moved into GatherHandler.
# The uneven top-level cases raise IndexError there, so have no entry.
# nested_uneven_2x5 chains across outer iterations (0-0-3 -> 0-1-0); that is
# the existing behaviour, kept as is.
PINNED_EDGES = {
    "top_level_even": [("0-0", "0-2"), ("0-1", "0-3")],
    "width_equals_dop": [],
    "nested_even_2x4": [
        ("0-0-0", "0-0-2"),
        ("0-0-1", "0-0-3"),
        ("0-1-0", "0-1-2"),
        ("0-1-1", "0-1-3"),
    ],
    "nested_even_3x4": [
        ("0-0-0", "0-0-2"),
        ("0-0-1", "0-0-3"),
        ("0-1-0", "0-1-2"),
        ("0-1-1", "0-1-3"),
        ("0-2-0", "0-2-2"),
        ("0-2-1", "0-2-3"),
    ],
    "nested_uneven_2x5": [
        ("0-0-0", "0-0-2"),
        ("0-0-1", "0-0-3"),
        ("0-0-2", "0-0-4"),
        ("0-0-3", "0-1-0"),
        ("0-0-4", "0-1-1"),
        ("0-1-0", "0-1-2"),
        ("0-1-1", "0-1-3"),
        ("0-1-2", "0-1-4"),
    ],
}


class TestSequentialisationGraphs(unittest.TestCase):
    def test_every_case_reaches_the_sequentialisation_branch(self):
        """Each case has exactly one Gather -> foreign group-start link."""

        for name, params in CASES.items():
            with self.subTest(case=name):
                lg = sequentialisation_lg(*params)
                hits = [
                    link
                    for link in lg._lg_links
                    if is_construct(lg._done_dict[link["from"]], Categories.GATHER)
                    and lg._done_dict[link["from"]].is_group
                    and not lg._done_dict[link["to"]].is_group
                    and lg._done_dict[link["to"]].gid != link["from"]
                ]
                self.assertEqual(1, len(hits))
                self.assertTrue(lg._done_dict[hits[0]["to"]].is_group_start)

    def test_chained_edges_match_the_pinned_pairing(self):
        for name, expected in PINNED_EDGES.items():
            with self.subTest(case=name):
                lg = sequentialisation_lg(*CASES[name])
                self.assertEqual(expected, chained_edges(lg))


def _node(category, category_type, is_group=False):
    return SimpleNamespace(
        id=category,
        name=category,
        category=category,
        is_group=is_group,
        jd={"category": category, "categoryType": category_type},
    )


class TestGatherSources(unittest.TestCase):
    """Links into a Gather are recorded with the input's own node and link."""

    def setUp(self):
        self.context = LinkContext("session-", [])
        self.gathers = {}
        self.sources = collections.defaultdict(list)
        self.gather = _node(Categories.GATHER, "Construct", is_group=True)

    def _defer(self, slgn, tlgn, src, tgt, llink):
        wire_module._link_or_defer(
            self.context,
            self.gathers,
            slgn,
            tlgn,
            src,
            tgt,
            llink,
            gather_sources=self.sources,
        )

    def test_an_input_is_recorded_with_its_raw_drop(self):
        groupby = _node(Categories.GROUP_BY, "Construct", is_group=True)
        group_data = dropdict({"oid": "group-data"})
        source = dropdict({"oid": "groupby", "grp-data_drop": group_data})
        llink = {"from": "groupby", "to": "gather"}

        self._defer(groupby, self.gather, source, dropdict({"oid": "g"}), llink)

        self.assertEqual(
            [wire_module.GatherSource(groupby, source, llink)], self.sources["g"]
        )
        # the cache itself is unchanged: it still holds the substituted drop
        self.assertEqual([group_data], self.gathers["g"][1])

    def test_an_output_of_a_gather_is_not_recorded(self):
        output = _node("File", "Data")

        self._defer(
            self.gather,
            output,
            dropdict({"oid": "g"}),
            dropdict({"oid": "out"}),
            {"from": "gather", "to": "File"},
        )

        self.assertEqual({}, dict(self.sources))


if __name__ == "__main__":
    unittest.main()
