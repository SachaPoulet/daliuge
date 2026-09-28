import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from dlg.translator.errors import GInvalidLink, GInvalidNode
from dlg.translator.stages.unroll.constructs.gather import GatherHandler
from dlg.translator.stages.unroll.constructs.groupby import GroupByHandler
from dlg.translator.stages.unroll.constructs.leaf import LeafHandler
from dlg.translator.stages.unroll.constructs.loop import LoopHandler
from dlg.translator.stages.unroll.constructs.mpi import MPIHandler
from dlg.translator.stages.unroll.constructs.registry import get_handler_for_node
from dlg.translator.stages.unroll.constructs.scatter import ScatterHandler
from dlg.translator.stages.unroll.constructs.service import ServiceHandler
from dlg.translator.stages.unroll.constructs.subgraph import SubgraphHandler
from dlg.translator.stages.unroll.lg_node import LGNode
from dlg.translator.vocabulary import Categories


class TestConstructHandlerDoP(unittest.TestCase):

    def test_gather_rejects_non_data_input(self):
        source = SimpleNamespace(
            id="source",
            jd={"categoryType": "Application"},
            is_groupby=False,
            is_gather=False,
        )
        target = SimpleNamespace(
            id="gather",
            is_gather=True,
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
            is_groupby=True,
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
            is_scatter=False,
            is_gather=False,
            is_groupby=False,
            is_loop=False,
            is_service=False,
            is_subgraph=False,
            is_mpi=False,
            jd={"category": category},
        )

        for name, value in predicates.items():
            setattr(node, name, value)

        return node

    def test_registry_dispatch(self):
        scatter = self._group_node(Categories.SCATTER, is_scatter=True)
        mpi = SimpleNamespace(
            is_group=False,
            is_mpi=True,
        )
        leaf = SimpleNamespace(
            is_group=False,
            is_mpi=False,
        )

        self.assertIsInstance(
            get_handler_for_node(scatter),
            ScatterHandler,
        )
        self.assertIsInstance(
            get_handler_for_node(mpi),
            MPIHandler,
        )
        self.assertIsInstance(
            get_handler_for_node(leaf),
            LeafHandler,
        )

    def test_registry_rejects_group_node_matching_no_construct(self):
        for category in [Categories.MPI, Categories.SUBGRAPH]:
            with self.subTest(category=category):
                with self.assertRaises(GInvalidNode):
                    get_handler_for_node(self._group_node(category))

    def test_registry_dispatch_prefers_construct_over_subgraph_flag(self):
        node = self._group_node(
            Categories.SCATTER,
            is_scatter=True,
            is_subgraph=True,
        )

        self.assertIsInstance(get_handler_for_node(node), ScatterHandler)

    def test_registry_rejects_group_node_without_category(self):
        node = self._group_node(Categories.SCATTER)
        node.jd = {}

        with self.assertRaises(KeyError):
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


if __name__ == "__main__":
    unittest.main()