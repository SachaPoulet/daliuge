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
"""Contract tests for the small, stable building blocks of the unroll stage.

Covers ``constructs/base.py`` (``HLevelRelation``, ``validate_hierarchy``),
``constructs/registry.py`` (handler lookup and edge-key fallback order),
``constructs/scatter.py`` (link validation, degree of parallelism and
one-to-one edge pairing), ``coordinate.py`` (``InstanceId`` wire format) and the
exception classes in ``errors.py``.

Everything here is a pure unit test: no graph files, no METIS and no
partitioning, so the results do not depend on the platform.
"""

# pylint: disable=protected-access
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from dlg.common import dropdict
from dlg.translator.errors import (
    GInvalidLink,
    GInvalidNode,
    GraphConfigFieldDoesNotExist,
    GraphConfigNodeDoesNotExist,
    GraphException,
    StageException,
)
from dlg.translator.stages.unroll.constructs import registry
from dlg.translator.stages.unroll.constructs.base import (
    ANY_CONSTRUCT,
    HLevelRelation,
    validate_hierarchy,
)
from dlg.translator.stages.unroll.constructs.branch import BranchHandler
from dlg.translator.stages.unroll.constructs.leaf import LeafHandler
from dlg.translator.stages.unroll.constructs.scatter import ScatterHandler
from dlg.translator.stages.unroll.constructs.subgraph import SubgraphHandler
from dlg.translator.stages.unroll.coordinate import InstanceId
from dlg.translator.stages.unroll.model import Edge, LogicalLink
from dlg.translator.vocabulary import Categories


def _node(category, **attributes):
    """Build a minimal stand-in for ``LGNode`` with only what these tests read."""
    node = SimpleNamespace(
        id=attributes.pop("id", category),
        name=attributes.pop("name", category),
        category=category,
        is_group=attributes.pop("is_group", False),
        jd=attributes.pop("jd", {}),
        group=attributes.pop("group", None),
        dop=attributes.pop("dop", 1),
        group_hierarchy=attributes.pop("group_hierarchy", ""),
        related=attributes.pop("related", False),
    )
    node.h_related = lambda other: node.related
    for key, value in attributes.items():
        setattr(node, key, value)
    return node


def _loop(dop, group=None, **attributes):
    return _node(Categories.LOOP, is_group=True, dop=dop, group=group, **attributes)


class TestHLevelRelation(unittest.TestCase):
    """The relation drives which handler resolves a link."""

    def test_between_reports_which_side_is_higher(self):
        self.assertIs(HLevelRelation.between(3, 1), HLevelRelation.SOURCE_HIGHER)
        self.assertIs(HLevelRelation.between(1, 3), HLevelRelation.TARGET_HIGHER)

    def test_between_reports_equal_levels(self):
        self.assertIs(HLevelRelation.between(2, 2), HLevelRelation.EQUAL)
        self.assertIs(HLevelRelation.between(0, 0), HLevelRelation.EQUAL)


class TestValidateHierarchy(unittest.TestCase):
    """``validate_hierarchy`` accepts nested or loop-synchronised nodes only."""

    def test_hierarchically_related_nodes_pass(self):
        source = _node("A", related=True)
        target = _node("B")
        validate_hierarchy(source, target)

    def test_unrelated_nodes_without_groups_are_rejected(self):
        source = _node("A", id="s", name="src", group_hierarchy="g1")
        target = _node("B", id="t", name="tgt", group_hierarchy="g2")
        with self.assertRaises(GInvalidLink) as raised:
            validate_hierarchy(source, target)
        message = str(raised.exception)
        self.assertIn("not hierarchically related", message)
        self.assertIn("src", message)
        self.assertIn("tgt", message)

    def test_only_one_side_in_a_group_is_rejected(self):
        for source_group, target_group in ((_loop(2), None), (None, _loop(2))):
            with self.subTest(source_group=source_group, target_group=target_group):
                source = _node("A", group=source_group)
                target = _node("B", group=target_group)
                with self.assertRaises(GInvalidLink):
                    validate_hierarchy(source, target)

    def test_mixed_loop_and_non_loop_groups_are_rejected(self):
        loop = _loop(2)
        scatter = _node(Categories.SCATTER, is_group=True)
        for source_group, target_group in ((loop, scatter), (scatter, loop)):
            with self.subTest(source_group=source_group.category):
                source = _node("A", group=source_group)
                target = _node("B", group=target_group)
                with self.assertRaises(GInvalidLink):
                    validate_hierarchy(source, target)

    def test_non_loop_groups_are_rejected(self):
        source = _node("A", group=_node(Categories.SCATTER, is_group=True))
        target = _node("B", group=_node(Categories.SCATTER, is_group=True))
        with self.assertRaises(GInvalidLink):
            validate_hierarchy(source, target)

    def test_loops_with_equal_dop_are_synchronised(self):
        source = _node("A", group=_loop(4))
        target = _node("B", group=_loop(4))
        validate_hierarchy(source, target)

    def test_loops_with_different_dop_are_rejected(self):
        source = _node("A", group=_loop(4, id="loop-s"))
        target = _node("B", group=_loop(3, id="loop-t"))
        with self.assertRaises(GInvalidLink) as raised:
            validate_hierarchy(source, target)
        message = str(raised.exception)
        self.assertIn("not loop synchronised", message)
        self.assertIn("loop-s", message)
        self.assertIn("loop-t", message)

    def test_nested_loops_are_checked_level_by_level(self):
        source = _node("A", group=_loop(2, group=_loop(5, id="outer-s")))
        target = _node("B", group=_loop(2, group=_loop(6, id="outer-t")))
        with self.assertRaises(GInvalidLink) as raised:
            validate_hierarchy(source, target)
        self.assertIn("outer-s", str(raised.exception))

    def test_nested_loops_with_equal_dop_at_every_level_pass(self):
        source = _node("A", group=_loop(2, group=_loop(5)))
        target = _node("B", group=_loop(2, group=_loop(5)))
        validate_hierarchy(source, target)

    def test_loops_of_different_depth_pass_once_the_shallower_ends(self):
        source = _node("A", group=_loop(2, group=_loop(5)))
        target = _node("B", group=_loop(2))
        validate_hierarchy(source, target)

    def test_walk_stops_when_an_ancestor_is_not_a_loop(self):
        scatter = _node(Categories.SCATTER, is_group=True)
        source = _node("A", group=_loop(2, group=scatter))
        target = _node("B", group=_loop(2, group=_loop(9)))
        validate_hierarchy(source, target)


class TestRegistryLookup(unittest.TestCase):
    """Handler lookup rules that wiring and instantiation both rely on."""

    def test_every_vocabulary_construct_has_a_handler(self):
        for construct in (
            Categories.SCATTER,
            Categories.GATHER,
            Categories.GROUP_BY,
            Categories.LOOP,
            Categories.MPI,
            Categories.BRANCH,
            Categories.SERVICE,
            Categories.SUBGRAPH,
            "leaf",
        ):
            with self.subTest(construct=construct):
                self.assertEqual(construct, registry.get_handler(construct).construct_type)

    def test_unknown_construct_is_a_key_error(self):
        with self.assertRaises(KeyError):
            registry.get_handler("NoSuchConstruct")

    def test_group_node_resolves_to_its_group_handler(self):
        node = _node(Categories.SCATTER, is_group=True)
        handler = registry.get_handler_for_node(node)
        self.assertEqual(Categories.SCATTER, handler.construct_type)

    def test_unrecognised_group_category_is_rejected(self):
        node = _node("Mystery", is_group=True)
        with self.assertRaises(GInvalidNode) as raised:
            registry.get_handler_for_node(node)
        self.assertIn("Mystery", str(raised.exception))

    def test_group_flagged_as_subgraph_app_uses_the_subgraph_handler(self):
        node = _node("Mystery", is_group=True, jd={"isSubGraphApp": True})
        handler = registry.get_handler_for_node(node)
        self.assertIsInstance(handler, SubgraphHandler)
        self.assertEqual(Categories.SUBGRAPH, handler.construct_type)

    def test_subgraph_category_without_the_app_flag_is_rejected(self):
        node = _node(Categories.SUBGRAPH, is_group=True, jd={"isSubGraphApp": False})
        with self.assertRaises(GInvalidNode):
            registry.get_handler_for_node(node)

    def test_subgraph_category_without_any_flag_uses_the_subgraph_handler(self):
        node = _node(Categories.SUBGRAPH, is_group=True)
        handler = registry.get_handler_for_node(node)
        self.assertEqual(Categories.SUBGRAPH, handler.construct_type)

    def test_branch_node_uses_the_branch_handler(self):
        node = _node(Categories.BRANCH)
        handler = registry.get_handler_for_node(node)
        self.assertIsInstance(handler, BranchHandler)
        self.assertEqual(Categories.BRANCH, handler.construct_type)

    def test_ordinary_node_falls_back_to_the_leaf_handler(self):
        node = _node("PythonApp")
        handler = registry.get_handler_for_node(node)
        self.assertIsInstance(handler, LeafHandler)
        self.assertEqual("leaf", handler.construct_type)

    def test_a_group_construct_name_on_a_plain_node_falls_back_to_leaf(self):
        node = _node(Categories.GATHER, is_group=False)
        self.assertEqual("leaf", registry.get_handler_for_node(node).construct_type)


class TestIsConstruct(unittest.TestCase):
    """``is_construct`` combines the category with node-specific rules."""

    def test_matching_category_is_a_construct(self):
        self.assertTrue(
            registry.is_construct(_node(Categories.GATHER, is_group=True), Categories.GATHER)
        )

    def test_different_category_is_not_a_construct(self):
        self.assertFalse(
            registry.is_construct(_node(Categories.GATHER, is_group=True), Categories.GROUP_BY)
        )

    def test_unregistered_construct_type_is_never_matched(self):
        self.assertFalse(registry.is_construct(_node("Mystery"), "Mystery"))

    def test_scatter_and_loop_names_on_plain_nodes_are_not_constructs(self):
        for construct in (Categories.SCATTER, Categories.LOOP):
            with self.subTest(construct=construct):
                node = _node(construct, is_group=False)
                self.assertFalse(registry.is_construct(node, construct))

    def test_subgraph_flag_overrides_the_category(self):
        flagged = _node(Categories.SUBGRAPH, is_group=True, jd={"isSubGraphApp": True})
        unflagged = _node(Categories.SUBGRAPH, is_group=True, jd={"isSubGraphApp": False})
        self.assertTrue(registry.is_construct(flagged, Categories.SUBGRAPH))
        self.assertFalse(registry.is_construct(unflagged, Categories.SUBGRAPH))


class _StubHandler:
    is_group_construct = False

    def __init__(self, construct_type, edge_keys=()):
        self.construct_type = construct_type
        self.edge_keys = edge_keys


class TestEdgeHandlerFallback(unittest.TestCase):
    """Edge keys are tried from most to least specific."""

    def test_candidates_are_ordered_from_specific_to_wildcard(self):
        relation = HLevelRelation.EQUAL
        candidates = list(registry._edge_key_candidates("S", "T", relation))
        self.assertEqual(
            [
                ("S", "T", relation),
                ("S", "T", None),
                ("S", ANY_CONSTRUCT, relation),
                ("S", ANY_CONSTRUCT, None),
                (ANY_CONSTRUCT, "T", relation),
                (ANY_CONSTRUCT, "T", None),
                (ANY_CONSTRUCT, ANY_CONSTRUCT, relation),
                (ANY_CONSTRUCT, ANY_CONSTRUCT, None),
            ],
            candidates,
        )

    def test_exact_key_wins_over_wildcards(self):
        exact = _StubHandler("exact")
        wildcard = _StubHandler("wildcard")
        edge_handlers = {
            ("S", "T", HLevelRelation.EQUAL): exact,
            (ANY_CONSTRUCT, ANY_CONSTRUCT, None): wildcard,
        }
        with patch.dict(registry._edge_handlers, edge_handlers, clear=True):
            found = registry.get_edge_handler("S", "T", HLevelRelation.EQUAL)
        self.assertIs(exact, found)

    def test_wildcard_is_used_when_nothing_more_specific_exists(self):
        wildcard = _StubHandler("wildcard")
        edge_handlers = {(ANY_CONSTRUCT, "T", None): wildcard}
        with patch.dict(registry._edge_handlers, edge_handlers, clear=True):
            found = registry.get_edge_handler("S", "T", HLevelRelation.SOURCE_HIGHER)
        self.assertIs(wildcard, found)

    def test_lookup_falls_back_through_every_candidate(self):
        relation = HLevelRelation.EQUAL
        candidates = list(registry._edge_key_candidates("S", "T", relation))
        handlers = {
            key: _StubHandler(f"candidate-{index}")
            for index, key in enumerate(candidates)
        }
        with patch.dict(registry._edge_handlers, handlers, clear=True):
            for key in candidates:
                with self.subTest(key=key):
                    self.assertIs(
                        handlers[key], registry.get_edge_handler("S", "T", relation)
                    )
                    del registry._edge_handlers[key]

    def test_missing_key_is_a_key_error_carrying_the_request(self):
        with patch.dict(registry._edge_handlers, {}, clear=True):
            with self.assertRaises(KeyError) as raised:
                registry.get_edge_handler("S", "T", HLevelRelation.EQUAL)
        self.assertEqual(("S", "T", HLevelRelation.EQUAL), raised.exception.args[0])

    def test_register_handler_records_the_type_and_its_edge_keys(self):
        key = ("S", "T", None)
        handler = _StubHandler("StubConstruct", edge_keys=(key,))
        with patch.dict(registry._handlers, {}), patch.dict(registry._edge_handlers, {}):
            registry.register_handler(handler)
            self.assertIs(handler, registry.get_handler("StubConstruct"))
            self.assertIs(handler, registry.get_edge_handler("S", "T", HLevelRelation.EQUAL))


class TestScatterHandler(unittest.TestCase):
    """Scatter creates no placeholder drop; it only validates and pairs."""

    handler = ScatterHandler()

    def test_linking_directly_to_a_scatter_is_rejected(self):
        scatter = _node(Categories.SCATTER, is_group=True, name="scatter")
        plain = _node("PythonApp", name="app")
        for source, target in ((scatter, plain), (plain, scatter)):
            with self.subTest(source=source.name, target=target.name):
                with self.assertRaises(GInvalidLink) as raised:
                    self.handler.validate_link(source, target)
                self.assertIn("Input App Type", str(raised.exception))

    def test_links_between_other_nodes_are_accepted(self):
        self.handler.validate_link(_node("A"), _node("B"))

    def test_degree_of_parallelism_reads_the_known_keys(self):
        for key in ("num_of_copies", "num_of_splits", "Number of copies"):
            with self.subTest(key=key):
                node = _node(Categories.SCATTER, is_group=True, jd={key: "4"})
                self.assertEqual(4, self.handler.degree_of_parallelism(node))

    def test_degree_of_parallelism_prefers_the_first_non_empty_key(self):
        node = _node(
            Categories.SCATTER,
            is_group=True,
            jd={"num_of_copies": 0, "num_of_splits": 3, "Number of copies": 7},
        )
        self.assertEqual(3, self.handler.degree_of_parallelism(node))

    def test_missing_degree_of_parallelism_is_reported_with_the_node(self):
        node = _node(Categories.SCATTER, is_group=True, id="42", name="my scatter")
        with self.assertRaises(GInvalidNode) as raised:
            self.handler.degree_of_parallelism(node)
        self.assertIn("my scatter", str(raised.exception))
        self.assertIn("42", str(raised.exception))

    def test_resolve_edges_pairs_sources_and_targets_in_order(self):
        link = LogicalLink(source=_node("S", id="s"), target=_node("T", id="t"))
        sources = [dropdict({"oid": f"s{i}"}) for i in range(3)]
        targets = [dropdict({"oid": f"t{i}"}) for i in range(3)]
        edges = self.handler.resolve_edges(link, sources, targets, ctx=None)
        self.assertEqual(
            [("s0", "t0"), ("s1", "t1"), ("s2", "t2")],
            [(edge.source["oid"], edge.target["oid"]) for edge in edges],
        )
        self.assertTrue(all(isinstance(edge, Edge) and edge.link is link for edge in edges))

    def test_resolve_edges_of_nothing_is_empty(self):
        link = LogicalLink(source=_node("S"), target=_node("T"))
        self.assertEqual([], self.handler.resolve_edges(link, [], [], ctx=None))

    def test_resolve_edges_rejects_unequal_counts(self):
        link = LogicalLink(source=_node("S", id="s"), target=_node("T", id="t"))
        sources = [dropdict({"oid": "s0"}), dropdict({"oid": "s1"})]
        targets = [dropdict({"oid": "t0"})]
        with self.assertRaises(GraphException) as raised:
            self.handler.resolve_edges(link, sources, targets, ctx=None)
        self.assertIn("within-group", str(raised.exception))

    def test_resolve_edges_rejects_extra_targets_and_one_sided_empty_inputs(self):
        link = LogicalLink(source=_node("S", id="s"), target=_node("T", id="t"))
        for source_count, target_count in ((1, 2), (0, 1), (1, 0)):
            with self.subTest(sources=source_count, targets=target_count):
                sources = [dropdict({"oid": f"s{i}"}) for i in range(source_count)]
                targets = [dropdict({"oid": f"t{i}"}) for i in range(target_count)]
                with self.assertRaises(GraphException):
                    self.handler.resolve_edges(link, sources, targets, ctx=None)


class TestInstanceId(unittest.TestCase):
    """The wire form of an instance id is what iids in drops are built from."""

    def test_wire_form_joins_the_path_with_dashes(self):
        self.assertEqual("0", str(InstanceId((0,))))
        self.assertEqual("1-2-3", str(InstanceId((1, 2, 3))))

    def test_group_key_is_appended_after_a_dollar_sign(self):
        self.assertEqual("1-2$3-4", str(InstanceId((1, 2), (3, 4))))

    def test_child_extends_the_path_and_the_wire_form(self):
        child = InstanceId((1, 2)).child(7)
        self.assertEqual((1, 2, 7), child.path)
        self.assertEqual("1-2-7", str(child))

    def test_child_of_a_keyed_instance_keeps_the_group_key(self):
        parent = InstanceId((1, 2), (3, 4))
        child = parent.child(7)
        self.assertEqual((1, 2, 7), child.path)
        self.assertEqual((3, 4), child.group_key)
        self.assertEqual("1-2$3-4", str(parent))

    def test_with_group_key_keeps_the_path(self):
        keyed = InstanceId((1, 2)).with_group_key((3, 4))
        self.assertEqual((1, 2), keyed.path)
        self.assertEqual((3, 4), keyed.group_key)
        self.assertEqual("1-2$3-4", str(keyed))

    def test_with_group_key_matches_constructing_it_directly(self):
        self.assertEqual(
            str(InstanceId((5,), (1,))),
            str(InstanceId((5,)).with_group_key((1,))),
        )

    def test_instance_ids_are_immutable(self):
        coord = InstanceId((1,))
        with self.assertRaises(AttributeError):
            coord.path = (2,)


class TestErrors(unittest.TestCase):
    """Messages are what users see when a graph or its config is wrong."""

    def test_stage_exception_names_the_stage(self):
        error = StageException("unroll")
        self.assertEqual("unroll", error.stage)
        self.assertEqual("stage 'unroll' failed", str(error))

    def test_stage_exception_appends_the_detail(self):
        self.assertEqual(
            "stage 'map' failed: no nodes", str(StageException("map", "no nodes"))
        )

    def test_missing_config_node_message_includes_the_id(self):
        self.assertIn("id: abc", str(GraphConfigNodeDoesNotExist("abc")))

    def test_missing_config_field_message_includes_the_id(self):
        self.assertIn("id: xyz", str(GraphConfigFieldDoesNotExist("xyz")))

    def test_graph_exceptions_form_a_hierarchy(self):
        self.assertTrue(issubclass(GInvalidLink, GraphException))
        self.assertTrue(issubclass(GInvalidNode, GraphException))


if __name__ == "__main__":
    unittest.main()
