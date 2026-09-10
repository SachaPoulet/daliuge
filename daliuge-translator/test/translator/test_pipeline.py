"""Unit tests for the Stage protocol, Pipeline, and UnrollStage.

The pipeline intentionally accepts structural Stage implementations, so the
tests use small recording stages rather than a second production hierarchy.
"""

import unittest
from unittest.mock import patch

from dlg.translator.artefacts import LogicalGraphTemplate, PhysicalGraphTemplate
from dlg.translator.errors import StageException
from dlg.translator.pipeline import Pipeline
from dlg.translator.stages.unroll.stage import UnrollOptions, UnrollStage


class RecordingStage:
    """A structural Stage implementation that records Pipeline interactions."""

    def __init__(self, name, events, run, stamp):
        self.name = name
        self._events = events
        self._run = run
        self._stamp = stamp

    def run(self, artefact):
        self._events.append((self.name, "run", artefact))
        return self._run(artefact)

    def stamp(self, artefact):
        self._events.append((self.name, "stamp", artefact))
        return self._stamp(artefact)


class PipelineTest(unittest.TestCase):
    def test_runs_stages_and_stamps_each_boundary_in_order(self):
        events = []
        first = RecordingStage(
            "first", events, lambda value: value + 1, lambda value: value * 10
        )
        second = RecordingStage(
            "second", events, lambda value: value + 2, lambda value: value + 100
        )

        self.assertEqual(Pipeline([first, second]).run(1), 122)
        self.assertEqual(
            events,
            [
                ("first", "run", 1),
                ("first", "stamp", 2),
                ("second", "run", 20),
                ("second", "stamp", 22),
            ],
        )

    def test_repro_disabled_skips_stamping_but_still_runs_stages(self):
        events = []
        stage = RecordingStage(
            "only", events, lambda value: value + 1, lambda value: value * 10
        )

        self.assertEqual(Pipeline([stage], repro=False).run(1), 2)
        self.assertEqual(events, [("only", "run", 1)])

    def test_then_returns_an_extended_pipeline_without_mutating_the_original(self):
        events = []
        first = RecordingStage(
            "first", events, lambda value: value + 1, lambda value: value
        )
        second = RecordingStage(
            "second", events, lambda value: value * 2, lambda value: value
        )
        original = Pipeline([first], repro=False)
        extended = original.then(second)

        self.assertEqual(original.run(1), 2)
        self.assertEqual(extended.run(1), 4)
        self.assertEqual(
            events,
            [
                ("first", "run", 1),
                ("first", "run", 1),
                ("second", "run", 2),
            ],
        )

    def test_run_failure_is_wrapped_with_the_failing_stage_name(self):
        def fail(_artefact):
            raise ValueError("bad input")

        stage = RecordingStage("unroll", [], fail, lambda artefact: artefact)

        with self.assertRaises(StageException) as context:
            Pipeline([stage]).run("logical graph")

        self.assertEqual(context.exception.stage, "unroll")
        self.assertEqual(str(context.exception), "stage 'unroll' failed: bad input")
        self.assertIsInstance(context.exception.__cause__, ValueError)

    def test_stamp_failure_is_wrapped_with_the_failing_stage_name(self):
        def fail(_artefact):
            raise LookupError("missing reprodata")

        stage = RecordingStage("partition", [], lambda artefact: artefact, fail)

        with self.assertRaises(StageException) as context:
            Pipeline([stage]).run("physical graph template")

        self.assertEqual(context.exception.stage, "partition")
        self.assertEqual(
            str(context.exception), "stage 'partition' failed: missing reprodata"
        )
        self.assertIsInstance(context.exception.__cause__, LookupError)


class UnrollStageTest(unittest.TestCase):
    @staticmethod
    def logical_graph():
        return {
            "modelData": {"name": "fixture"},
            "nodeDataArray": [{"id": 1, "fields": [{"name": "input"}]}],
            "linkDataArray": [],
            "reprodata": {"rmode": "1"},
        }

    @patch("dlg.translator.stages.unroll.stage.unroll")
    def test_run_delegates_with_options_and_does_not_expose_lgt_storage(
        self, unroll
    ):
        unroll.return_value = [
            {"oid": "session_-1_0", "categoryType": "Application"},
            {"rmode": "1"},
        ]
        logical_graph = LogicalGraphTemplate.from_wire(self.logical_graph())
        before = logical_graph.to_wire()
        stage = UnrollStage(
            UnrollOptions(oid_prefix="session", zerorun=True, app="test.App")
        )

        output = stage.run(logical_graph)

        self.assertIsInstance(output, PhysicalGraphTemplate)
        self.assertEqual(output.to_wire(), unroll.return_value)
        unroll.assert_called_once()
        kwargs = unroll.call_args.kwargs
        self.assertEqual(kwargs["oid_prefix"], "session")
        self.assertTrue(kwargs["zerorun"])
        self.assertEqual(kwargs["app"], "test.App")
        self.assertEqual(kwargs["lg"], before)

        kwargs["lg"]["nodeDataArray"][0]["fields"].append({"name": "changed"})
        self.assertEqual(logical_graph.to_wire(), before)

    @patch("dlg.translator.stages.unroll.stage.init_pgt_unroll_repro_data")
    def test_stamp_wraps_the_repro_hook_result_and_keeps_input_isolated(self, hook):
        pgt = PhysicalGraphTemplate.from_wire(
            [
                {"oid": "session_-1_0", "categoryType": "Application"},
                {"rmode": "1"},
            ]
        )
        before = pgt.to_wire()
        hook.return_value = [
            {
                "oid": "session_-1_0",
                "categoryType": "Application",
                "reprodata": {"merkleroot": "abc"},
            },
            {"rmode": "1"},
        ]

        stamped = UnrollStage().stamp(pgt)

        self.assertIsInstance(stamped, PhysicalGraphTemplate)
        self.assertEqual(stamped.to_wire(), hook.return_value)
        hook.assert_called_once_with(before)
        hook_input = hook.call_args.args[0]
        hook_input[0]["oid"] = "changed"
        self.assertEqual(pgt.to_wire(), before)


if __name__ == "__main__":
    unittest.main()
