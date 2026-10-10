import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import dlg.translator.stages.unroll.wire as wire_module
from dlg.translator.vocabulary import Categories


class FakeDrop(dict):
    """Small DROP stub that records physical wiring calls."""

    def __init__(self, **values):
        super().__init__(**values)
        self.addConsumer = Mock()
        self.addInput = Mock()


class TestGroupByHandlerWiring(unittest.TestCase):

    def test_wire_uses_groupby_pairs_and_preserves_port_names(self):
        source = SimpleNamespace(
            id="source",
            name="source",
            category=Categories.FILE,
            is_group=False,
            h_level=1,
            gid="scatter",
            group=None,
            jd={
                "category": Categories.FILE,
                "categoryType": "Data",
            },
            getPortName=Mock(return_value="source-output"),
        )

        target = SimpleNamespace(
            id="groupby",
            name="groupby",
            category=Categories.GROUP_BY,
            is_group=True,
            h_level=0,
            gid="groupby",
            group=None,
            group_keys=None,
            groupby_width=1,
            group_by_scatter_layers=(2, [], []),
            jd={
                "category": Categories.GROUP_BY,
                "categoryType": "Data",
            },
            getPortName=Mock(return_value="target-input"),
        )

        # Deliberately reverse the IID order so the test checks that
        # GroupByHandler pairing is actually used by wire().
        source_drops = [
            FakeDrop(oid="source-1", iid="1"),
            FakeDrop(oid="source-0", iid="0"),
        ]
        target_drops = [
            FakeDrop(oid="groupby-0"),
            FakeDrop(oid="groupby-1"),
        ]

        graph = SimpleNamespace(
            _session_id="session-",
            _done_dict={
                source.id: source,
                target.id: target,
            },
            _drop_dict={
                source.id: source_drops,
                target.id: target_drops,
                "new_added": [],
            },
            _lg_links=[
                {
                    "from": source.id,
                    "to": target.id,
                    "fromPort": "source-port",
                    "toPort": "target-port",
                }
            ],
            _loop_aware_set=set(),
        )

        wire_module.wire(graph)

        # IID 0 must pair with target 0, and IID 1 with target 1.
        source_drops[1].addConsumer.assert_called_once_with(
            target_drops[0],
            name="source-output",
        )
        target_drops[0].addInput.assert_called_once_with(
            source_drops[1],
            name="target-input",
        )

        source_drops[0].addConsumer.assert_called_once_with(
            target_drops[1],
            name="source-output",
        )
        target_drops[1].addInput.assert_called_once_with(
            source_drops[0],
            name="target-input",
        )

        source.getPortName.assert_any_call(
            "outputPorts",
            portId="source-port",
        )
        target.getPortName.assert_any_call(
            "inputPorts",
            portId="target-port",
        )


if __name__ == "__main__":
    unittest.main()
