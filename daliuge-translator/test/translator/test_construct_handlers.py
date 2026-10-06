import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

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
from dlg.translator.vocabulary import Categories


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


class TestGatherEdgeResolution(unittest.TestCase):
    class FakeWiringContext:
        def __init__(self, chunk_size):
            self._chunk_size = chunk_size

        def chunk_size(self, source, target):
            del source, target
            return self._chunk_size

        @staticmethod
        def split(drops, size):
            for index in range(0, len(drops), size):
                yield drops[index:index + size]

    @staticmethod
    def _node(node_id, h_level):
        return SimpleNamespace(
            id=node_id,
            h_level=h_level,
        )

    def test_gather_groups_source_drops_by_chunk_size(self):
        source = self._node("source", 2)
        target = self._node("gather", 1)
        link = LogicalLink(source, target)

        sources = [
            {"oid": "s0"},
            {"oid": "s1"},
            {"oid": "s2"},
            {"oid": "s3"},
        ]
        targets = [
            {"oid": "g0"},
            {"oid": "g1"},
        ]

        edges = GatherHandler().resolve_edges(
            link,
            sources,
            targets,
            self.FakeWiringContext(2),
        )

        self.assertEqual(
            [
                ("s0", "g0"),
                ("s1", "g0"),
                ("s2", "g1"),
                ("s3", "g1"),
            ],
            [
                (edge.source["oid"], edge.target["oid"])
                for edge in edges
            ],
        )

    def test_gather_accepts_equal_h_level(self):
        source = self._node("source", 1)
        target = self._node("gather", 1)
        link = LogicalLink(source, target)

        edges = GatherHandler().resolve_edges(
            link,
            [{"oid": "s0"}],
            [{"oid": "g0"}],
            self.FakeWiringContext(1),
        )

        self.assertEqual(1, len(edges))
        self.assertEqual("s0", edges[0].source["oid"])
        self.assertEqual("g0", edges[0].target["oid"])

    def test_gather_rejects_target_with_higher_level(self):
        source = self._node("source", 1)
        target = self._node("gather", 2)
        link = LogicalLink(source, target)

        with self.assertRaises(GraphException):
            GatherHandler().resolve_edges(
                link,
                [{"oid": "s0"}],
                [{"oid": "g0"}],
                self.FakeWiringContext(1),
            )


if __name__ == "__main__":
    unittest.main()
