import unittest
from pathlib import Path

from dlg.translator.stages.unroll.constructs.registry import is_construct
from dlg.translator.stages.unroll.lg import LG
from dlg.translator.vocabulary import Categories


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCATTER_GRAPH = (
    REPOSITORY_ROOT
    / "test"
    / "corpus"
    / "graphs"
    / "eagle-test-graphs"
    / "SuperBasicScatterGather.graph"
)


class TestScatterEdgeResolution(unittest.TestCase):
    def test_scatter_expands_input_link_to_each_child_drop(self):
        lg = LG(
            str(SCATTER_GRAPH),
            ssid="scatter-edge-resolution",
            apply_config=False,
        )
        scatter = next(
            node
            for node in lg._done_dict.values()
            if is_construct(node, Categories.SCATTER)
        )
        child_file = next(
            node for node in scatter.children if node.category == "File"
        )
        input_app = child_file.inputs[0]

        drops = lg.unroll_to_tpl()

        scatter_drops = lg._drop_dict[scatter.id]
        child_drops = lg._drop_dict[child_file.id]
        input_drop = lg._drop_dict[input_app.id][0]
        linked_drop_oids = [
            next(iter(output)) for output in input_drop["outputs"]
        ]

        self.assertGreater(scatter.dop, 1)
        self.assertEqual([], scatter_drops)
        self.assertEqual(scatter.dop, len(child_drops))
        self.assertEqual([drop["oid"] for drop in child_drops], linked_drop_oids)
        self.assertIn(input_drop, drops)


if __name__ == "__main__":
    unittest.main()
