import unittest
from unittest.mock import Mock, call, patch

from dlg.translator.stages.unroll.lg import LG


class TestPairwiseLinkValidationContract(unittest.TestCase):
    def setUp(self):
        self.logical_graph = object.__new__(LG)
        self.source = object()
        self.target = object()
        self.source_handler = Mock()
        self.target_handler = Mock()

    def test_validates_source_then_target_then_hierarchy(self):
        events = []
        self.source_handler.validate_link.side_effect = lambda src, tgt: events.append(
            ("source", src, tgt)
        )
        self.target_handler.validate_link.side_effect = lambda src, tgt: events.append(
            ("target", src, tgt)
        )

        with patch(
            "dlg.translator.stages.unroll.lg.get_handler_for_node",
            side_effect=[self.source_handler, self.target_handler],
        ) as get_handler, patch(
            "dlg.translator.stages.unroll.lg.validate_hierarchy",
            side_effect=lambda src, tgt: events.append(("hierarchy", src, tgt)),
        ) as validate_hierarchy:
            self.logical_graph.validate_link(self.source, self.target)

        self.assertEqual(
            [call(self.source), call(self.target)], get_handler.call_args_list
        )
        self.source_handler.validate_link.assert_called_once_with(
            self.source, self.target
        )
        self.target_handler.validate_link.assert_called_once_with(
            self.source, self.target
        )
        validate_hierarchy.assert_called_once_with(self.source, self.target)
        self.assertEqual(
            [
                ("source", self.source, self.target),
                ("target", self.source, self.target),
                ("hierarchy", self.source, self.target),
            ],
            events,
        )

    def test_stops_when_source_validation_fails(self):
        source_error = ValueError("source link is invalid")
        self.source_handler.validate_link.side_effect = source_error

        with patch(
            "dlg.translator.stages.unroll.lg.get_handler_for_node",
            return_value=self.source_handler,
        ) as get_handler, patch(
            "dlg.translator.stages.unroll.lg.validate_hierarchy"
        ) as validate_hierarchy:
            with self.assertRaisesRegex(ValueError, "source link is invalid"):
                self.logical_graph.validate_link(self.source, self.target)

        get_handler.assert_called_once_with(self.source)
        self.source_handler.validate_link.assert_called_once_with(
            self.source, self.target
        )
        validate_hierarchy.assert_not_called()

    def test_stops_before_hierarchy_when_target_validation_fails(self):
        target_error = ValueError("target link is invalid")
        self.target_handler.validate_link.side_effect = target_error

        with patch(
            "dlg.translator.stages.unroll.lg.get_handler_for_node",
            side_effect=[self.source_handler, self.target_handler],
        ) as get_handler, patch(
            "dlg.translator.stages.unroll.lg.validate_hierarchy"
        ) as validate_hierarchy:
            with self.assertRaisesRegex(ValueError, "target link is invalid"):
                self.logical_graph.validate_link(self.source, self.target)

        self.assertEqual(
            [call(self.source), call(self.target)], get_handler.call_args_list
        )
        self.source_handler.validate_link.assert_called_once_with(
            self.source, self.target
        )
        self.target_handler.validate_link.assert_called_once_with(
            self.source, self.target
        )
        validate_hierarchy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
