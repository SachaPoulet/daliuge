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
"""Contract tests for the wiring helpers and handler validation rules of unroll.

Covers the parts of ``wire.py``, ``link.py`` and ``stage.py`` that are not
reached by the full-graph tests, plus the ``validate_link`` /
``degree_of_parallelism`` rules of the Gather, GroupBy, Loop, Service and
Subgraph handlers.

* ``wire.py``: chunking helpers, the Gather deferral cache (``_link_or_defer``),
  the splice of deferred Gather inputs onto the first output drop, and the
  no-op Sub-graph resolution.
* ``link.py``: the streaming-flag branch of ``link_drops``.
* ``stage.py``: the ``zerorun`` and ``app`` options of ``unroll``.

Everything uses small fakes: no graph files, no METIS, no partitioning, so the
results do not depend on the platform.
"""

# pylint: disable=protected-access
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import dlg.translator.stages.unroll.stage as stage_module
import dlg.translator.stages.unroll.wire as wire_module
from dlg.common import dropdict
from dlg.translator.errors import GInvalidLink, GInvalidNode
from dlg.translator.stages.unroll.constructs.gather import GatherHandler
from dlg.translator.stages.unroll.constructs.groupby import GroupByHandler
from dlg.translator.stages.unroll.constructs.loop import LoopHandler
from dlg.translator.stages.unroll.constructs.service import ServiceHandler
from dlg.translator.stages.unroll.constructs.subgraph import SubgraphHandler
from dlg.translator.stages.unroll.link import (
    LinkContext,
    _is_stream_link,
    link_drops,
)
from dlg.translator.vocabulary import Categories


def _node(category, **attributes):
    """Minimal stand-in for ``LGNode`` with only what these tests read."""
    node_id = attributes.pop("id", category)
    node = SimpleNamespace(
        id=node_id,
        name=attributes.pop("name", node_id),
        category=category,
        is_group=attributes.pop("is_group", False),
        jd={
            "category": category,
            "categoryType": attributes.pop("category_type", "Data"),
        },
        group=None,
        h_level=0,
        gid=node_id,
        inputs=[],
        is_group_start=False,
        gather_width=1,
        groupby_width=1,
    )
    node.dop_diff = Mock(return_value=1)
    node.getPortName = Mock(return_value="port")
    for key, value in attributes.items():
        setattr(node, key, value)
    return node


def _construct(category, **attributes):
    attributes.setdefault("category_type", "Construct")
    return _node(category, is_group=True, **attributes)


def _gather(**attributes):
    return _construct(Categories.GATHER, **attributes)


def _groupby(**attributes):
    return _construct(Categories.GROUP_BY, **attributes)


def _drop(oid):
    return dropdict({"oid": oid})


class TestChunkingHelpers(unittest.TestCase):
    """``_split_list`` and ``_get_chunk_size`` decide how drops are grouped."""

    def test_split_list_yields_chunks_in_order(self):
        self.assertEqual(
            [[1, 2], [3, 4], [5]], list(wire_module._split_list([1, 2, 3, 4, 5], 2))
        )

    def test_split_list_with_an_exact_multiple_has_no_short_chunk(self):
        self.assertEqual([[1, 2], [3, 4]], list(wire_module._split_list([1, 2, 3, 4], 2)))

    def test_split_list_of_nothing_is_empty(self):
        self.assertEqual([], list(wire_module._split_list([], 3)))

    def test_chunk_size_of_a_gather_is_its_gather_width(self):
        target = _gather(gather_width=4)
        self.assertEqual(4, wire_module._get_chunk_size(_node("A"), target))

    def test_chunk_size_of_a_groupby_is_its_groupby_width(self):
        target = _groupby(groupby_width=6)
        self.assertEqual(6, wire_module._get_chunk_size(_node("A"), target))

    def test_chunk_size_otherwise_is_the_dop_difference(self):
        source, target = _node("A"), _node("B")
        source.dop_diff.return_value = 7
        self.assertEqual(7, wire_module._get_chunk_size(source, target))
        source.dop_diff.assert_called_once_with(target)


class TestLinkOrDefer(unittest.TestCase):
    """Links into or out of a Gather are held back; everything else is wired."""

    def setUp(self):
        self.context = LinkContext("session-", [])

    def _defer(self, gathers, slgn, tlgn, src, tgt, llink=None):
        wire_module._link_or_defer(
            self.context, gathers, slgn, tlgn, src, tgt, llink or {"from": "s", "to": "t"}
        )

    def test_an_ordinary_input_into_a_gather_is_held_back(self):
        gathers, source, gather = {}, _drop("src"), _drop("gather")
        with patch.object(wire_module, "link_drops") as wired:
            self._defer(gathers, _node("A"), _gather(), source, gather)
        wired.assert_not_called()
        self.assertEqual(["gather"], list(gathers))
        held_gather, inputs, outputs, _ = gathers["gather"]
        self.assertIs(gather, held_gather)
        self.assertEqual([source], inputs)
        self.assertEqual([], outputs)

    def test_an_input_from_a_groupby_uses_its_group_data_drop(self):
        group_data = _drop("grp-data")
        source = dropdict({"oid": "groupby", "grp-data_drop": group_data})
        gathers = {}
        self._defer(gathers, _groupby(), _gather(), source, _drop("gather"))
        self.assertEqual([group_data], gathers["gather"][1])

    def test_an_input_from_another_gather_is_a_placeholder(self):
        gathers = {}
        self._defer(gathers, _gather(), _gather(), _drop("g1"), _drop("g2"))
        self.assertEqual([None], gathers["g2"][1])

    def test_later_inputs_extend_the_same_cache_entry(self):
        gathers, gather = {}, _drop("gather")
        first, second = _drop("a"), _drop("b")
        self._defer(gathers, _node("A"), _gather(), first, gather)
        self._defer(gathers, _node("A"), _gather(), second, gather)
        self.assertEqual([first, second], gathers["gather"][1])
        self.assertEqual(1, len(gathers))

    def test_the_cache_remembers_the_first_logical_link(self):
        gathers, gather = {}, _drop("gather")
        first, second = {"from": "a", "to": "g"}, {"from": "b", "to": "g"}
        self._defer(gathers, _node("A"), _gather(), _drop("a"), gather, first)
        self._defer(gathers, _node("A"), _gather(), _drop("b"), gather, second)
        self.assertIs(first, gathers["gather"][3])

    def test_an_output_of_a_gather_is_recorded_not_wired(self):
        gathers, gather, output = {}, _drop("gather"), _drop("out")
        with patch.object(wire_module, "link_drops") as wired:
            self._defer(gathers, _gather(), _node("B"), gather, output)
        wired.assert_not_called()
        self.assertEqual([output], gathers["gather"][2])
        self.assertEqual([], gathers["gather"][1])

    def test_an_application_source_is_wired_even_for_a_gather_node(self):
        slgn = _gather(category_type="Application")
        with patch.object(wire_module, "link_drops") as wired:
            self._defer({}, slgn, _node("B"), _drop("g"), _drop("out"))
        wired.assert_called_once()

    def test_a_stream_link_out_of_a_gather_is_wired_not_held(self):
        slgn = _gather(category_type=Categories.PYTHON_APP)
        tlgn = _node("B", category_type=Categories.PYTHON_APP)
        gathers = {}
        with patch.object(wire_module, "link_drops") as wired:
            self._defer(gathers, slgn, tlgn, _drop("g"), _drop("out"))
        wired.assert_called_once()
        self.assertEqual({}, gathers)

    def test_an_ordinary_link_is_wired_with_the_same_arguments(self):
        slgn, tlgn = _node("A"), _node("B")
        src, tgt, llink = _drop("s"), _drop("t"), {"from": "s", "to": "t"}
        gathers = {}
        with patch.object(wire_module, "link_drops") as wired:
            self._defer(gathers, slgn, tlgn, src, tgt, llink)
        wired.assert_called_once_with(self.context, slgn, tlgn, src, tgt, llink)
        self.assertEqual({}, gathers)


class TestGatherSplice(unittest.TestCase):
    """After all links are wired, deferred Gather inputs reach the first output."""

    @staticmethod
    def _graph(source, gather):
        return SimpleNamespace(
            _session_id="session-",
            _done_dict={source.id: source, gather.id: gather},
            _drop_dict={source.id: [_drop("a")], gather.id: [_drop("g")], "new_added": []},
            _lg_links=[{"from": source.id, "to": gather.id, "is_stream": False}],
            _loop_aware_set=set(),
        )

    def _run(self, outputs, is_stream=False, inputs=None):
        """Wire a graph whose Gather resolver feeds the cache by hand."""
        source = _node("source")
        gather = _gather(id="gather")
        graph = self._graph(source, gather)
        graph._lg_links[0]["is_stream"] = is_stream
        input_drops = inputs if inputs is not None else [graph._drop_dict[source.id][0]]
        output_node = _node("sink")

        def resolve(context, link, slgn, tlgn, sdrops, tdrops, lk):
            del context, sdrops
            for drop in input_drops:
                link(slgn, tlgn, drop, tdrops[0], lk)
            for drop in outputs:
                link(tlgn, output_node, tdrops[0], drop, lk)

        with patch.object(wire_module, "_resolve_gather_edges", side_effect=resolve):
            wire_module.wire(graph)
        return input_drops

    def test_inputs_are_wired_to_the_first_output_only(self):
        first, second, third = _drop("o1"), _drop("o2"), _drop("o3")
        a, b = _drop("a"), _drop("b")
        self._run([first, second], inputs=[a, b])
        for drop in (a, b):
            self.assertEqual([{"o1": "port"}], drop["consumers"])
        self.assertEqual([{"a": "port"}, {"b": "port"}], first["inputs"])
        self.assertNotIn("inputs", second)
        self.assertNotIn("inputs", third)

    def test_a_streaming_link_uses_streaming_relations(self):
        output, a = _drop("out"), _drop("a")
        self._run([output], is_stream=True, inputs=[a])
        self.assertEqual([{"out": "port"}], a["streamingConsumers"])
        self.assertEqual([{"a": "port"}], output["streamingInputs"])
        self.assertNotIn("consumers", a)
        self.assertNotIn("inputs", output)

    def test_a_gather_without_outputs_leaves_its_inputs_unwired(self):
        a = _drop("a")
        self._run([], inputs=[a])
        self.assertNotIn("consumers", a)
        self.assertNotIn("streamingConsumers", a)

    @staticmethod
    def _wire_with_unrelated_link(unrelated_last, is_stream):
        source = _node("source", h_level=1)
        gather = _gather(id="gather")
        sink = _node("sink", gid=gather.id)
        other = _node("other")
        other_sink = _node("other_sink")
        nodes = (source, gather, sink, other, other_sink)
        for node in nodes:
            node.getPortName = Mock(return_value=f"{node.id}_port")
            node.h_related = Mock(return_value=True)
            node.is_start_node = False

        drops = {node.id: [_drop(f"{node.id}_drop")] for node in nodes}
        drops["new_added"] = []
        gather_links = [
            {"from": source.id, "to": gather.id, "is_stream": is_stream},
            {"from": gather.id, "to": sink.id},
        ]
        unrelated_link = {"from": other.id, "to": other_sink.id}
        links = (
            gather_links + [unrelated_link]
            if unrelated_last
            else [unrelated_link] + gather_links
        )
        graph = SimpleNamespace(
            _session_id="session-",
            _done_dict={node.id: node for node in nodes},
            _drop_dict=drops,
            _lg_links=links,
            _loop_aware_set=set(),
        )
        wire_module.wire(graph)
        return drops[source.id][0], drops[sink.id][0]

    @unittest.expectedFailure
    def test_unrelated_link_order_does_not_change_gather_ports(self):
        """The splice currently reads the last link's source for Gather ports."""
        first_source, first_sink = self._wire_with_unrelated_link(False, False)
        last_source, last_sink = self._wire_with_unrelated_link(True, False)
        self.assertEqual(first_source["consumers"], last_source["consumers"])
        self.assertEqual(first_sink["inputs"], last_sink["inputs"])

    @unittest.expectedFailure
    def test_unrelated_link_order_does_not_change_streaming_gather_ports(self):
        """The same stale source affects streaming Gather ports."""
        first_source, first_sink = self._wire_with_unrelated_link(False, True)
        last_source, last_sink = self._wire_with_unrelated_link(True, True)
        self.assertEqual(
            first_source["streamingConsumers"], last_source["streamingConsumers"]
        )
        self.assertEqual(first_sink["streamingInputs"], last_sink["streamingInputs"])


class TestGatherSequentialisation(unittest.TestCase):
    """A Gather can connect one batch's inputs to the next batch of starts."""

    @staticmethod
    def _wire_gather_to_starts(dop, gather_width, source_count):
        source = _node("source", h_level=1)
        gather = _gather(id="gather", gather_width=gather_width)
        target = _node("target", gid="scatter", group=SimpleNamespace(dop=dop))
        source_drops = [_drop(f"s{i}") for i in range(source_count)]
        target_drops = [_drop(f"t{i}") for i in range(dop)]
        graph = SimpleNamespace(
            _session_id="session-",
            _done_dict={node.id: node for node in (source, gather, target)},
            _drop_dict={
                source.id: source_drops,
                gather.id: [
                    _drop(f"g{i}") for i in range((dop + gather_width - 1) // gather_width)
                ],
                target.id: target_drops,
                "new_added": [],
            },
            _lg_links=[
                {"from": source.id, "to": gather.id},
                {"from": gather.id, "to": target.id},
            ],
            _loop_aware_set=set(),
        )
        wire_module.wire(graph)
        return source_drops, target_drops

    def test_full_width_batch_connects_to_the_next_starts(self):
        sources, targets = self._wire_gather_to_starts(4, 2, 4)
        self.assertEqual([{"t2": "port"}], sources[0]["consumers"])
        self.assertEqual([{"t3": "port"}], sources[1]["consumers"])
        self.assertEqual([{"s0": "port"}], targets[2]["inputs"])
        self.assertEqual([{"s1": "port"}], targets[3]["inputs"])
        self.assertNotIn("consumers", sources[2])
        self.assertNotIn("consumers", sources[3])

    @unittest.expectedFailure
    def test_partial_final_batch_stops_at_the_last_start(self):
        """A short final batch currently indexes past the last target drop."""
        sources, targets = self._wire_gather_to_starts(5, 3, 5)
        self.assertEqual([{"t3": "port"}], sources[0]["consumers"])
        self.assertEqual([{"t4": "port"}], sources[1]["consumers"])
        self.assertEqual([{"s0": "port"}], targets[3]["inputs"])
        self.assertEqual([{"s1": "port"}], targets[4]["inputs"])
        self.assertNotIn("consumers", sources[2])

    def test_no_cached_inputs_leave_sequential_starts_unwired(self):
        gather = _gather(id="gather", gather_width=2)
        own_start = _node("own_start", gid=gather.id)
        later_start = _node("later_start", gid="scatter", group=SimpleNamespace(dop=4))
        own_drops = [_drop("own0"), _drop("own1")]
        later_drops = [_drop(f"later{i}") for i in range(4)]
        graph = SimpleNamespace(
            _session_id="session-",
            _done_dict={node.id: node for node in (gather, own_start, later_start)},
            _drop_dict={
                gather.id: [_drop("g0"), _drop("g1")],
                own_start.id: own_drops,
                later_start.id: later_drops,
                "new_added": [],
            },
            _lg_links=[
                {"from": gather.id, "to": own_start.id},
                {"from": gather.id, "to": later_start.id},
            ],
            _loop_aware_set=set(),
        )
        wire_module.wire(graph)
        for drop in own_drops + later_drops:
            self.assertNotIn("inputs", drop)


class TestSubgraphResolution(unittest.TestCase):
    """Sub-graph edges keep the legacy behaviour of creating no links."""

    def test_no_links_are_created(self):
        link = Mock()
        wire_module._resolve_subgraph_edges(
            LinkContext("session-", []),
            link,
            _node("A"),
            _node(Categories.SUBGRAPH, is_group=True),
            [_drop("s")],
            [_drop("t")],
            {"fromPort": "x", "toPort": "y"},
        )
        link.assert_not_called()

    def test_missing_port_keys_are_tolerated(self):
        link = Mock()
        wire_module._resolve_subgraph_edges(
            LinkContext("session-", []), link, _node("A"), _node("B"), [], [], {}
        )
        link.assert_not_called()


class TestLinkDrops(unittest.TestCase):
    """``link_drops`` chooses the relation type from the link's stream flag."""

    context = LinkContext("session-", [])

    def _link(self, is_stream):
        source, target = _node("A"), _node("B")
        source.getPortName = Mock(return_value="out")
        target.getPortName = Mock(return_value="in")
        src, tgt = _drop("s"), _drop("t")
        link_drops(
            self.context, source, target, src, tgt,
            {"fromPort": "p1", "toPort": "p2", "is_stream": is_stream},
        )
        return src, tgt, source, target

    def test_a_streaming_link_uses_streaming_relations(self):
        src, tgt, source, target = self._link(True)
        self.assertEqual([{"t": "out"}], src["streamingConsumers"])
        self.assertEqual([{"s": "in"}], tgt["streamingInputs"])
        self.assertNotIn("consumers", src)
        source.getPortName.assert_called_once_with("outputPorts", portId="p1")
        target.getPortName.assert_called_once_with("inputPorts", portId="p2")

    def test_a_plain_link_uses_ordinary_relations(self):
        src, tgt, _, _ = self._link(False)
        self.assertEqual([{"t": "out"}], src["consumers"])
        self.assertEqual([{"s": "in"}], tgt["inputs"])
        self.assertNotIn("streamingConsumers", src)

    def test_is_stream_link_needs_application_like_types_on_both_sides(self):
        self.assertTrue(_is_stream_link(Categories.PYTHON_APP, Categories.COMPONENT))
        self.assertFalse(_is_stream_link(Categories.PYTHON_APP, "Data"))
        self.assertFalse(_is_stream_link("Data", Categories.PYTHON_APP))


class TestUnrollOptions(unittest.TestCase):
    """The ``zerorun`` and ``app`` options post-process the unrolled drops."""

    @staticmethod
    def _unroll(specs, **options):
        fake_graph = SimpleNamespace(
            unroll_to_tpl=Mock(return_value=specs), reprodata={"reprodata": True}
        )
        with patch.object(stage_module, "LG", return_value=fake_graph) as lg_class:
            result = stage_module.unroll({"nodeDataArray": []}, oid_prefix="p", **options)
        lg_class.assert_called_once_with({"nodeDataArray": []}, ssid="p")
        return result

    def test_defaults_leave_the_drops_untouched_and_append_reprodata(self):
        specs = [{"oid": "a", "categoryType": "Application", "sleep_time": 5}]
        result = self._unroll(specs)
        self.assertEqual({"oid": "a", "categoryType": "Application", "sleep_time": 5}, result[0])
        self.assertEqual({"reprodata": True}, result[-1])
        self.assertEqual(2, len(result))

    def test_zerorun_zeroes_only_existing_sleep_times(self):
        specs = [{"oid": "a", "sleep_time": 5}, {"oid": "b"}]
        result = self._unroll(specs, zerorun=True)
        self.assertEqual(0, result[0]["sleep_time"])
        self.assertNotIn("sleep_time", result[1])

    def test_app_replaces_the_class_of_application_drops_only(self):
        specs = [
            {"oid": "app", "categoryType": "Application", "dropclass": "x.Real"},
            {"oid": "data", "categoryType": "Data", "dropclass": "x.Data"},
            {"oid": "plain", "categoryType": "Application"},
        ]
        result = self._unroll(specs, app="dlg.apps.simple.SleepApp")
        self.assertEqual("dlg.apps.simple.SleepApp", result[0]["dropclass"])
        self.assertEqual("x.Data", result[1]["dropclass"])
        self.assertNotIn("dropclass", result[2])

    def test_app_sleep_time_defaults_to_two_or_uses_the_execution_time(self):
        specs = [
            {"oid": "a", "categoryType": "Application", "dropclass": "x"},
            {"oid": "b", "categoryType": "Application", "dropclass": "x", "execution_time": 9},
        ]
        result = self._unroll(specs, app="y")
        self.assertEqual(2, result[0]["sleep_time"])
        self.assertEqual(9, result[1]["sleep_time"])

    def test_app_overrides_zerorun_only_for_application_drops_with_a_class(self):
        specs = [
            {
                "oid": "app", "categoryType": "Application", "dropclass": "x",
                "sleep_time": 5, "execution_time": 9,
            },
            {
                "oid": "app-default", "categoryType": "Application",
                "dropclass": "x", "sleep_time": 5,
            },
            {"oid": "data", "categoryType": "Data", "sleep_time": 5},
        ]
        result = self._unroll(specs, zerorun=True, app="replacement")
        self.assertEqual(
            ("replacement", 9), (result[0]["dropclass"], result[0]["sleep_time"])
        )
        self.assertEqual(
            ("replacement", 2), (result[1]["dropclass"], result[1]["sleep_time"])
        )
        self.assertEqual(0, result[2]["sleep_time"])


class TestGatherValidation(unittest.TestCase):
    handler = GatherHandler()

    @staticmethod
    def _gather_with_input(h_level=1):
        return _gather(inputs=[_node("in", h_level=h_level)])

    @staticmethod
    def _start_app(h_level=1, group_start=True, category_type="Application"):
        return _node(
            "App", category_type=category_type, h_level=h_level, is_group_start=group_start
        )

    def test_a_group_start_application_at_the_same_level_is_a_valid_output(self):
        self.handler.validate_link(self._gather_with_input(1), self._start_app(1))

    def test_application_type_is_matched_case_insensitively_for_the_known_spellings(self):
        for spelling in ("app", "application", "Application"):
            with self.subTest(spelling=spelling):
                self.handler.validate_link(
                    self._gather_with_input(1), self._start_app(1, category_type=spelling)
                )

    def test_an_output_that_is_not_an_application_is_rejected(self):
        with self.assertRaises(GInvalidLink) as raised:
            self.handler.validate_link(
                self._gather_with_input(), self._start_app(category_type="Data")
            )
        self.assertIn("Group-Start", str(raised.exception))

    def test_an_output_that_is_not_a_group_start_is_rejected(self):
        with self.assertRaises(GInvalidLink):
            self.handler.validate_link(
                self._gather_with_input(), self._start_app(group_start=False)
            )

    def test_an_output_at_a_different_level_is_rejected(self):
        with self.assertRaises(GInvalidLink):
            self.handler.validate_link(self._gather_with_input(1), self._start_app(2))

    def test_data_and_groupby_inputs_are_accepted(self):
        for source in (_node("D", category_type="Data"), _node("D2", category_type="data"), _groupby()):
            with self.subTest(source=source.id):
                self.handler.validate_link(source, _gather())

    def test_an_application_input_is_rejected(self):
        with self.assertRaises(GInvalidLink) as raised:
            self.handler.validate_link(_node("App", category_type="Application"), _gather())
        self.assertIn("GroupBy or Data", str(raised.exception))

    def test_a_gather_without_input_has_no_degree_of_parallelism(self):
        with self.assertRaises(GInvalidLink) as raised:
            self.handler.degree_of_parallelism(_gather(id="g1", inputs=[]))
        self.assertIn("does not have input", str(raised.exception))


class TestGroupByValidation(unittest.TestCase):
    handler = GroupByHandler()

    def test_a_valid_input_is_accepted(self):
        source = _node("A", gid="scatter-1")
        self.handler.validate_link(source, _groupby(inputs=[]))

    def test_a_group_input_is_rejected(self):
        with self.assertRaises(GInvalidLink) as raised:
            self.handler.validate_link(_node("S", is_group=True), _groupby(inputs=[]))
        self.assertIn("must not be a group", str(raised.exception))

    def test_a_second_input_is_rejected(self):
        target = _groupby(id="gb", inputs=[_node("first")])
        with self.assertRaises(GInvalidLink) as raised:
            self.handler.validate_link(_node("A", gid="s"), target)
        self.assertIn("already has input", str(raised.exception))

    def test_an_input_outside_any_scatter_is_rejected(self):
        with self.assertRaises(GInvalidLink) as raised:
            self.handler.validate_link(_node("A", gid=0), _groupby(inputs=[]))
        self.assertIn("at least one Scatter", str(raised.exception))

    def test_a_groupby_may_only_feed_a_gather(self):
        self.handler.validate_link(_groupby(), _gather())
        with self.assertRaises(GInvalidLink) as raised:
            self.handler.validate_link(_groupby(), _node("App", category_type="Application"))
        self.assertIn("must be Gather", str(raised.exception))


class TestLoopValidation(unittest.TestCase):
    handler = LoopHandler()

    @staticmethod
    def _loop(**jd):
        node = _node(Categories.LOOP, is_group=True, category_type="Construct", id="L", name="loop")
        node.jd.update(jd)
        return node

    def test_linking_directly_to_or_from_a_loop_is_rejected(self):
        loop, plain = self._loop(), _node("A", name="app")
        for source, target in ((loop, plain), (plain, loop)):
            with self.subTest(source=source.name):
                with self.assertRaises(GInvalidLink):
                    self.handler.validate_link(source, target)

    def test_other_links_are_accepted(self):
        self.handler.validate_link(_node("A"), _node("B"))

    def test_iteration_count_is_read_from_the_known_keys(self):
        for key in ("num_of_iter", "Number of Iterations", "Number of loops"):
            with self.subTest(key=key):
                self.assertEqual(3, self.handler.degree_of_parallelism(self._loop(**{key: "3"})))

    def test_the_first_non_empty_key_wins(self):
        loop = self._loop(num_of_iter=0, **{"Number of Iterations": 4, "Number of loops": 9})
        self.assertEqual(4, self.handler.degree_of_parallelism(loop))

    def test_a_loop_without_an_iteration_count_is_rejected(self):
        with self.assertRaises(GInvalidNode) as raised:
            self.handler.degree_of_parallelism(self._loop())
        self.assertIn("iteration count", str(raised.exception))


class TestTrivialHandlers(unittest.TestCase):
    """Service and Sub-graph accept any link and are never replicated."""

    def test_service_accepts_links_and_has_unit_parallelism(self):
        handler = ServiceHandler()
        handler.validate_link(_node("A"), _node("B"))
        self.assertEqual(1, handler.degree_of_parallelism(_node(Categories.SERVICE)))

    def test_subgraph_accepts_links_and_has_unit_parallelism(self):
        handler = SubgraphHandler()
        handler.validate_link(_node("A"), _node("B"))
        self.assertEqual(1, handler.degree_of_parallelism(_node(Categories.SUBGRAPH)))
        self.assertEqual([], handler.resolve_edges(Mock(), [_drop("s")], [_drop("t")], None))


if __name__ == "__main__":
    unittest.main()
