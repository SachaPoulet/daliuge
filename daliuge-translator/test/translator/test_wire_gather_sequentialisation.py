"""Gather sequentialisation.

No corpus graph reaches the sequentialisation branch, so these graphs are built
from SuperBasicScatterGather: the Gather loses its input application and links
back to a group-start application inside the Scatter it gathers.
"""

import copy
import json
import unittest
from pathlib import Path

from dlg.translator.stages.unroll.constructs.registry import is_construct
from dlg.translator.stages.unroll.lg import LG
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


if __name__ == "__main__":
    unittest.main()
