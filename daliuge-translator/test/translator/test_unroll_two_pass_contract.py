"""Contract tests for Phase 4's two-pass unroll orchestration."""

import unittest
from pathlib import Path
from unittest.mock import patch

import dlg.translator.stages.unroll.lg as lg_module
from dlg.translator.stages.unroll.lg import LG


TEST_SSID = "two-pass-contract"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class TestTwoPassUnrollContract(unittest.TestCase):
    """Guard the orchestration boundary between instantiation and wiring."""

    @staticmethod
    def _hello_world_lg():
        graph_path = (
            REPOSITORY_ROOT
            / "test"
            / "corpus"
            / "graphs"
            / "eagle-test-graphs"
            / "HelloWorld_simple.graph"
        )
        return LG(str(graph_path), ssid=TEST_SSID)

    def test_unroll_runs_synthesis_instantiation_then_wiring(self):
        """The Phase 4 passes must keep their deliberate, observable order."""

        graph = self._hello_world_lg()
        events = []

        def record(name, implementation):
            def wrapped(lg):
                events.append(name)
                return implementation(lg)

            return wrapped

        with patch.object(
            lg_module,
            "synthesise_links",
            side_effect=record("synthesise_links", lg_module.synthesise_links),
        ), patch.object(
            lg_module,
            "instantiate",
            side_effect=record("instantiate", lg_module.instantiate),
        ), patch.object(
            lg_module,
            "wire",
            side_effect=record("wire", lg_module.wire),
        ):
            drops = graph.unroll_to_tpl()

        self.assertEqual(["synthesise_links", "instantiate", "wire"], events)
        self.assertEqual(2, len(drops))

    def test_wiring_starts_after_every_simple_node_has_a_drop(self):
        """Wiring must never need to create a missing ordinary-node drop."""

        graph = self._hello_world_lg()
        original_wire = lg_module.wire

        def assert_ready_then_wire(lg):
            for node_id in lg._done_dict:
                self.assertIn(node_id, lg._drop_dict)
                self.assertTrue(lg._drop_dict[node_id])

            relation_keys = ("inputs", "outputs", "producers", "consumers")
            for drops in lg._drop_dict.values():
                for drop in drops:
                    for key in relation_keys:
                        self.assertFalse(drop.get(key, []))

            return original_wire(lg)

        with patch.object(lg_module, "wire", side_effect=assert_ready_then_wire):
            drops = graph.unroll_to_tpl()

        self.assertEqual(2, len(drops))


if __name__ == "__main__":
    unittest.main()
