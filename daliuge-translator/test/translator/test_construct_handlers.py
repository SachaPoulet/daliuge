import unittest
from collections import defaultdict
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock, patch

from dlg.common import dropdict
from dlg.translator.errors import GInvalidLink, GInvalidNode, GraphException
from dlg.translator.stages.unroll.constructs.branch import BranchHandler
from dlg.translator.stages.unroll.constructs.gather import GatherHandler
from dlg.translator.stages.unroll.constructs.groupby import GroupByHandler
from dlg.translator.stages.unroll.constructs.leaf import LeafHandler
from dlg.translator.stages.unroll.constructs.loop import LoopHandler
from dlg.translator.stages.unroll.constructs.mpi import MPIHandler
from dlg.translator.stages.unroll.constructs.registry import (
    get_handler_for_node,
    is_construct,
    register_handler,
)
from dlg.translator.stages.unroll.constructs.scatter import ScatterHandler
from dlg.translator.stages.unroll.constructs.service import ServiceHandler
from dlg.translator.stages.unroll.constructs.subgraph import SubgraphHandler
from dlg.translator.stages.unroll.lg_node import LGNode
from dlg.translator.stages.unroll.model import LogicalLink
from dlg.translator.stages.unroll.wire import wire
from dlg.translator.vocabulary import Categories


class TestGroupByHandlerResolveEdges(unittest.TestCase):
    """Test the GroupBy edge pairing for IID-derived keys and error cases"""

    class UnusedWiringContext:
        session_id = "test"

        @staticmethod
        def node(node_id):
            raise AssertionError(f"Unexpected node lookup: {node_id}")

        @staticmethod
        def chunk_size(source, target):
            del source, target
            raise AssertionError("GroupBy edge resolution should not chunk drops")

        @staticmethod
        def split(drops, size):
            del drops, size
            raise AssertionError("GroupBy edge resolution should not split drops")

    @staticmethod
    def _node(category, **attributes):
        node = SimpleNamespace(
            id=attributes.pop("id", category),
            name=attributes.pop("name", category),
            category=category,
            is_group=category
            in (Categories.GROUP_BY, Categories.SCATTER, Categories.LOOP),
            jd={"category": category},
            group=None,
            h_level=0,
        )
        for name, value in attributes.items():
            setattr(node, name, value)
        return cast(LGNode, node)

    def _resolve(self, source_iids, target_count, **target_attributes):
        source_group = target_attributes.pop("source_group", None)
        source = self._node(
            Categories.PYTHON_APP,
            h_level=target_attributes.pop("source_h_level", 0),
        )
        source.group = source_group
        target = self._node(
            Categories.GROUP_BY,
            h_level=target_attributes.pop("target_h_level", 0),
            group_keys=target_attributes.pop("group_keys", None),
            group_by_scatter_layers=target_attributes.pop(
                "group_by_scatter_layers", (target_count, [], [])
            ),
        )
        link = LogicalLink(source=source, target=target)
        sources = [dropdict({"iid": iid}) for iid in source_iids]
        targets = [
            dropdict({"target": index}) for index in range(target_count)
        ]
        edges = GroupByHandler().resolve_edges(
            link,
            sources,
            targets,
            self.UnusedWiringContext(),
        )
        return source, target, sources, targets, edges

    def test_buckets_source_drops_and_sorts_group_keys(self):
        _, _, sources, targets, edges = self._resolve(
            ["2-1", "0-1", "0-2"],
            2,
        )

        self.assertEqual(
            [
                (sources[0], targets[0]),
                (sources[1], targets[0]),
                (sources[2], targets[1]),
            ],
            [(edge.source, edge.target) for edge in edges],
        )

    def test_includes_outer_group_context_for_nested_scatter(self):
        _, _, sources, targets, edges = self._resolve(
            ["4-2-1", "5-2-1"],
            2,
            source_h_level=3,
            target_h_level=1,
        )

        self.assertEqual(
            [(sources[0], targets[0]), (sources[1], targets[1])],
            [(edge.source, edge.target) for edge in edges],
        )

    def test_multi_key_groupby_reverses_iid_context(self):
        _, _, sources, targets, edges = self._resolve(
            ["0-1", "1-0"],
            2,
            group_keys=("first", "second"),
            group_by_scatter_layers=(2, [0], []),
            source_group=self._node(Categories.SCATTER),
        )

        self.assertEqual(
            [
                (sources[1], targets[0]),
                (sources[0], targets[1]),
            ],
            [(edge.source, edge.target) for edge in edges],
        )

    def test_multi_key_groupby_sorts_indices_numerically_above_nine(self):
        keys = [
            (2, 0),
            (10, 0),
            (11, 0),
            (2, 10),
            (2, 11),
            (10, 2),
            (11, 10),
        ]
        source_iids = [f"{second}-{first}" for first, second in keys]
        _, _, sources, targets, edges = self._resolve(
            source_iids,
            len(keys),
            group_keys=("first", "second"),
            group_by_scatter_layers=(len(keys), [0, 1], []),
            source_group=self._node(Categories.SCATTER),
        )
        numeric_order = [0, 3, 4, 1, 5, 2, 6]

        self.assertEqual(
            [
                (sources[source_index], targets[target_index])
                for target_index, source_index in enumerate(numeric_order)
            ],
            [(edge.source, edge.target) for edge in edges],
        )

    def test_chained_multi_key_groupby_reads_group_key_after_dollar(self):
        source = self._node(Categories.PYTHON_APP)
        source.group = self._node(
            Categories.GROUP_BY,
            name="outer-groupby",
        )
        target = self._node(
            Categories.GROUP_BY,
            group_keys=("first", "second"),
            group_by_scatter_layers=(2, [0, 1], []),
        )
        link = LogicalLink(source=source, target=target)
        sources = [
            dropdict({"iid": "0-1$2-3"}),
            dropdict({"iid": "0-1$1-3"}),
        ]
        targets = [dropdict({"target": 0}), dropdict({"target": 1})]

        edges = GroupByHandler().resolve_edges(
            link,
            sources,
            targets,
            self.UnusedWiringContext(),
        )

        self.assertEqual(
            [
                (sources[1], targets[0]),
                (sources[0], targets[1]),
            ],
            [(edge.source, edge.target) for edge in edges],
        )

    def test_chained_multi_key_groupby_requires_dollar_context(self):
        source = self._node(Categories.PYTHON_APP)
        source.group = self._node(Categories.GROUP_BY)
        target = self._node(
            Categories.GROUP_BY,
            group_keys=("first", "second"),
            group_by_scatter_layers=(1, [0], []),
        )
        link = LogicalLink(source=source, target=target)

        with self.assertRaisesRegex(GraphException, "hiearchy.*not specified"):
            GroupByHandler().resolve_edges(
                link,
                [dropdict({"iid": "0-1"})],
                [dropdict({"target": 0})],
                self.UnusedWiringContext(),
            )

    def test_rejects_mismatch_between_group_keys_and_target_drops(self):
        with self.assertRaisesRegex(GraphException, "# of Group keys 2 != # of Group Drops 1"):
            self._resolve(["0-1", "0-2"], 1)


class TestConstructHandlerDoP(unittest.TestCase):

    def test_gather_rejects_non_data_input(self):
        source = SimpleNamespace(
            id="source",
            category=Categories.PYTHON_APP,
            jd={
                "category": Categories.PYTHON_APP,
                "categoryType": "Application",
            },
        )
        target = SimpleNamespace(
            id="gather",
            category=Categories.GATHER,
            jd={"category": Categories.GATHER},
        )

        with self.assertRaises(GInvalidLink):
            GatherHandler().validate_link(source, target)

    def test_handler_dop_values(self):
        scatter = SimpleNamespace(
            jd={"num_of_copies": "4"},
            name="scatter",
            id="scatter",
        )
        self.assertEqual(
            4,
            ScatterHandler().degree_of_parallelism(scatter, None),
        )

        loop = SimpleNamespace(
            jd={"num_of_iter": "5"},
            name="loop",
            id="loop",
        )
        self.assertEqual(
            5,
            LoopHandler().degree_of_parallelism(loop, None),
        )

        mpi = SimpleNamespace(jd={"num_of_procs": "6"})
        self.assertEqual(
            6,
            MPIHandler().degree_of_parallelism(mpi, None),
        )

        groupby = SimpleNamespace(
            group_by_scatter_layers=(3, [], [])
        )
        self.assertEqual(
            3,
            GroupByHandler().degree_of_parallelism(groupby, None),
        )

        self.assertEqual(
            1,
            ServiceHandler().degree_of_parallelism(None, None),
        )
        self.assertEqual(
            1,
            SubgraphHandler().degree_of_parallelism(None, None),
        )
        self.assertEqual(
            1,
            LeafHandler().degree_of_parallelism(None, None),
        )

    def test_gather_dop(self):
        input_node = SimpleNamespace(
            category=Categories.GROUP_BY,
            jd={"category": Categories.GROUP_BY},
            dop=8,
        )
        gather = SimpleNamespace(
            inputs=[input_node],
            gather_width=2,
        )

        self.assertEqual(
            4,
            GatherHandler().degree_of_parallelism(gather, None),
        )

    @staticmethod
    def _group_node(category, **predicates):
        node = SimpleNamespace(
            is_group=True,
            category=category,
            jd={"category": category},
        )

        for name, value in predicates.items():
            setattr(node, name, value)

        return node

    def test_registry_dispatch(self):
        scatter = self._group_node(Categories.SCATTER)
        branch = SimpleNamespace(
            is_group=False,
            category=Categories.BRANCH,
            jd={"category": Categories.BRANCH},
        )
        mpi = SimpleNamespace(
            is_group=False,
            category=Categories.MPI,
            jd={"category": Categories.MPI},
        )
        leaf = SimpleNamespace(
            is_group=False,
            category="ordinary",
            jd={"category": "ordinary"},
        )

        self.assertIsInstance(
            get_handler_for_node(scatter),
            ScatterHandler,
        )
        self.assertIsInstance(get_handler_for_node(branch), BranchHandler)
        self.assertIsInstance(
            get_handler_for_node(mpi),
            MPIHandler,
        )
        self.assertIsInstance(
            get_handler_for_node(leaf),
            LeafHandler,
        )

    def test_group_handler_registration_adds_group_dispatch(self):
        handler = SimpleNamespace(
            construct_type="TestGroupConstruct",
            is_group_construct=True,
            edge_keys=(),
        )
        register_handler(handler)
        node = self._group_node(handler.construct_type)

        self.assertIs(get_handler_for_node(node), handler)

    def test_registry_rejects_group_node_matching_no_construct(self):
        for category in [Categories.MPI, Categories.BRANCH]:
            with self.subTest(category=category):
                with self.assertRaises(GInvalidNode):
                    get_handler_for_node(self._group_node(category))

    def test_registry_dispatch_prefers_construct_over_subgraph_flag(self):
        node = self._group_node(Categories.SCATTER)
        node.jd["isSubGraphApp"] = True

        self.assertIsInstance(get_handler_for_node(node), ScatterHandler)

    def test_registry_construct_checks_preserve_node_context(self):
        scatter = self._group_node(Categories.SCATTER)
        loop = self._group_node(Categories.LOOP)
        non_group_scatter = SimpleNamespace(
            is_group=False,
            category=Categories.SCATTER,
            jd={"category": Categories.SCATTER},
        )
        non_group_loop = SimpleNamespace(
            is_group=False,
            category=Categories.LOOP,
            jd={"category": Categories.LOOP},
        )
        subgraph_flagged = SimpleNamespace(
            is_group=False,
            category=Categories.PYTHON_APP,
            jd={"category": Categories.PYTHON_APP, "isSubGraphApp": True},
        )
        subgraph_disabled = SimpleNamespace(
            is_group=True,
            category=Categories.SUBGRAPH,
            jd={"category": Categories.SUBGRAPH, "isSubGraphApp": False},
        )

        self.assertTrue(is_construct(scatter, Categories.SCATTER))
        self.assertTrue(is_construct(loop, Categories.LOOP))
        self.assertFalse(is_construct(non_group_scatter, Categories.SCATTER))
        self.assertFalse(is_construct(non_group_loop, Categories.LOOP))
        self.assertTrue(is_construct(subgraph_flagged, Categories.SUBGRAPH))
        self.assertFalse(is_construct(subgraph_disabled, Categories.SUBGRAPH))

    def test_registry_rejects_group_node_without_category(self):
        node = self._group_node(Categories.SCATTER)
        node.category = "Unknown"
        node.jd = {}

        with self.assertRaises(GInvalidNode):
            get_handler_for_node(node)

    def test_lgnode_dop_uses_handler_and_caches_result(self):
        node = object.__new__(LGNode)
        node._dop = None

        handler = Mock()
        handler.degree_of_parallelism.return_value = 7

        with patch(
            "dlg.translator.stages.unroll.lg_node.get_handler_for_node",
            return_value=handler,
        ) as get_handler:
            self.assertEqual(7, node.dop)
            self.assertEqual(7, node.dop)

            get_handler.assert_called_once_with(node)
            handler.degree_of_parallelism.assert_called_once_with(node)


class TestGroupByWire(unittest.TestCase):
    """Test GroupBy edge pairing through wire and physical port wiring."""

    def test_wire_connects_numeric_group_pairs_using_link_port_names(self):
        source_port_names = {"source-output-id": "source-output"}
        target_port_names = {"target-input-id": "target-input"}

        def get_port_name(port_names, ports, index=0, portId=None):
            del ports
            if index < 0:
                return port_names
            return port_names.get(portId)

        source = SimpleNamespace(
            id="source",
            name="source",
            category=Categories.PYTHON_APP,
            categoryType="Application",
            jd={"categoryType": "Application"},
            is_group=False,
            is_start_node=False,
            group=None,
            h_level=0,
            getPortName=lambda ports, index=0, portId=None: get_port_name(
                source_port_names, ports, index, portId
            ),
        )
        target = SimpleNamespace(
            id="groupby",
            name="groupby",
            category=Categories.GROUP_BY,
            categoryType="Construct",
            jd={"category": Categories.GROUP_BY, "categoryType": "Construct"},
            is_group=True,
            group_keys=None,
            group_by_scatter_layers=(3, [], []),
            groupby_width=3,
            h_level=0,
            getPortName=lambda ports, index=0, portId=None: get_port_name(
                target_port_names, ports, index, portId
            ),
        )
        source_drops = [
            dropdict({"oid": "source-10", "iid": "0-10"}),
            dropdict({"oid": "source-2", "iid": "0-2"}),
            dropdict({"oid": "source-11", "iid": "0-11"}),
        ]
        target_drops = [
            dropdict({"oid": "group-0"}),
            dropdict({"oid": "group-1"}),
            dropdict({"oid": "group-2"}),
        ]
        logical_link = {
            "from": source.id,
            "to": target.id,
            "fromPort": "source-output-id",
            "toPort": "target-input-id",
        }
        graph = SimpleNamespace(
            _session_id="test",
            _drop_dict=defaultdict(
                list,
                {source.id: source_drops, target.id: target_drops},
            ),
            _done_dict={source.id: source, target.id: target},
            _lg_links=[logical_link],
            _loop_aware_set=set(),
        )

        wire(graph)

        self.assertEqual(
            [
                [{"group-1": "source-output"}],
                [{"group-0": "source-output"}],
                [{"group-2": "source-output"}],
            ],
            [source_drop["outputs"] for source_drop in source_drops],
        )
        self.assertEqual(
            [
                [{"source-2": "target-input"}],
                [{"source-10": "target-input"}],
                [{"source-11": "target-input"}],
            ],
            [target_drop["producers"] for target_drop in target_drops],
        )
        self.assertEqual(
            [{"target-input": "source-output"}] * 3,
            [target_drop["port_map"] for target_drop in target_drops],
        )


if __name__ == "__main__":
    unittest.main()
