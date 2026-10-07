#
#    ICRAR - International Centre for Radio Astronomy Research
#    (c) UWA - The University of Western Australia, 2026
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

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from dlg.common import CategoryType
from dlg.translator.stages.unroll.constructs.registry import get_handler
from dlg.translator.stages.unroll.lg import LG
from dlg.translator.stages.unroll.link import LinkContext, link_drops
from dlg.translator.stages.unroll.wire import wire
from dlg.translator.vocabulary import Categories


class FakeDrop(dict):
    def __init__(self, **values):
        super().__init__(**values)
        self.addConsumer = Mock()
        self.addInput = Mock()
        self.addOutput = Mock()
        self.addStreamingInput = Mock()


class TestLinkDrops(unittest.TestCase):
    def setUp(self):
        self.context = LinkContext(session_id="session-", new_drops=[])

    def test_stream_link_creates_and_records_a_bridge_drop(self):
        source = SimpleNamespace(
            category=Categories.PYTHON_APP,
            jd={"categoryType": Categories.PYTHON_APP},
        )
        target = SimpleNamespace(
            category=Categories.DALIUGE_APP,
            jd={"categoryType": Categories.DALIUGE_APP},
        )
        source_drop = FakeDrop(oid="source")
        target_drop = FakeDrop(oid="session-target")

        link_drops(
            self.context,
            source,
            target,
            source_drop,
            target_drop,
            {"from": "source", "to": "target"},
        )

        bridge_drop = self.context.new_drops[0]
        self.assertEqual("source-target-stream", bridge_drop["oid"])
        self.assertEqual(CategoryType.DATA, bridge_drop["categoryType"])
        source_drop.addOutput.assert_called_once_with(bridge_drop, name="stream")
        target_drop.addStreamingInput.assert_called_once_with(
            bridge_drop, name="stream"
        )

    def test_data_link_uses_the_declared_ports(self):
        source = SimpleNamespace(
            category=Categories.FILE,
            jd={"categoryType": CategoryType.DATA},
            getPortName=Mock(return_value="source-output"),
        )
        target = SimpleNamespace(
            category=Categories.FILE,
            jd={"categoryType": CategoryType.DATA},
            getPortName=Mock(return_value="target-input"),
        )
        source_drop = FakeDrop(oid="source")
        target_drop = FakeDrop(oid="target")

        link_drops(
            self.context,
            source,
            target,
            source_drop,
            target_drop,
            {"fromPort": "source-port", "toPort": "target-port"},
        )

        source_drop.addConsumer.assert_called_once_with(
            target_drop, name="source-output"
        )
        target_drop.addInput.assert_called_once_with(source_drop, name="target-input")

    def test_lg_no_longer_owns_the_link_helpers(self):
        self.assertFalse(hasattr(LG, "_is_stream_link"))
        self.assertFalse(hasattr(LG, "_link_drops"))

    def test_within_group_pairing_uses_scatter_handler_then_common_linker(self):
        source = SimpleNamespace(
            id="group",
            name="group",
            category=Categories.GROUP_BY,
            is_group=True,
            group=None,
            dop_diff=Mock(return_value=1),
            jd={"category": Categories.GROUP_BY},
        )
        target = SimpleNamespace(
            id="component",
            name="component",
            category="Component",
            is_group=False,
            group=None,
            gid="group",
            jd={"category": "Component"},
        )
        source_drops = [FakeDrop(oid="source-0"), FakeDrop(oid="source-1")]
        target_drops = [FakeDrop(oid="target-0"), FakeDrop(oid="target-1")]
        logical_link = {"from": source.id, "to": target.id}
        lg = SimpleNamespace(
            _session_id="session",
            _drop_dict={
                "new_added": [],
                source.id: source_drops,
                target.id: target_drops,
            },
            _done_dict={source.id: source, target.id: target},
            _lg_links=[logical_link],
            _loop_aware_set=set(),
        )

        with (
            patch(
                "dlg.translator.stages.unroll.wire.get_handler",
                side_effect=get_handler,
            ) as handler_lookup,
            patch("dlg.translator.stages.unroll.wire._link_or_defer") as common_linker,
        ):
            wire(lg)

        handler_lookup.assert_called_once_with(Categories.SCATTER)
        self.assertEqual(
            list(zip(source_drops, target_drops)),
            [call.args[4:6] for call in common_linker.call_args_list],
        )
        context = common_linker.call_args_list[0].args[0]
        self.assertIs(context.node(source.id), source)
        self.assertEqual(1, context.chunk_size(source, target))
        self.assertEqual(
            [[source_drops[0]], [source_drops[1]]],
            list(context.split(source_drops, 1)),
        )


if __name__ == "__main__":
    unittest.main()
