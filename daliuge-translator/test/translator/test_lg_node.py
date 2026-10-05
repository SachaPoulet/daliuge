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
"""
Unit tests for LGNode's categoryType inference/validation (issue #26).

Covers the two defects fixed by PR #32:

  5d - a node whose ``category`` is in neither APP_TYPES nor DATA_TYPES and
       which omits ``categoryType`` used to die with a bare
       ``KeyError: 'categoryType'`` (no node id, no field name). It must now
       raise ``GInvalidNode`` naming the offending node and category instead.

  5e - ``Categories.DATA`` ("Data") used to appear in *both* APP_TYPES and
       DATA_TYPES. Because the inference in the ``jd`` setter checks
       APP_TYPES first, a ``category: "Data"`` node omitting ``categoryType``
       was silently mis-inferred as ``Application``. The fix removes the
       overlapping entry from APP_TYPES; a "Data" node must now infer as
       ``Data``.
"""

import unittest
from collections import defaultdict

from dlg.common import CategoryType
from dlg.translator.errors import GInvalidNode
from dlg.translator.stages.unroll.lg_node import LGNode
from dlg.translator.stages.unroll.model import LGNode as ModelLGNode
from dlg.translator.vocabulary import Categories


def _make_node(jd):
    """
    Construct a standalone LGNode from a minimal node dict, the same way
    LG._process_node does when it's walking a real graph's nodeDataArray.
    """
    jd.setdefault("fields", [])
    return LGNode(jd, group_q=defaultdict(list), done_dict={}, ssid="test_lg_node")


class TestCategoryTypeInference(unittest.TestCase):
    def test_infers_application_from_app_category(self):
        # category is in APP_TYPES, categoryType omitted -> should infer Application
        node = _make_node({"id": "n1", "name": "n1", "category": Categories.PYTHON_APP})
        self.assertEqual(node.jd["categoryType"], CategoryType.APPLICATION)
        self.assertTrue(node.is_app)
        self.assertFalse(node.is_data)

    def test_infers_data_from_data_category(self):
        # category is in DATA_TYPES, categoryType omitted -> should infer Data
        node = _make_node({"id": "n2", "name": "n2", "category": Categories.FILE})
        self.assertEqual(node.jd["categoryType"], CategoryType.DATA)
        self.assertTrue(node.is_data)
        self.assertFalse(node.is_app)

    def test_data_category_infers_data_not_application(self):
        # Regression test for 5e: "Data" used to be listed in both APP_TYPES
        # and DATA_TYPES, and since APP_TYPES was checked first, a bare
        # `category: "Data"` node (no categoryType) was wrongly inferred as
        # Application. It must infer as Data.
        node = _make_node({"id": "n3", "name": "n3", "category": Categories.DATA})
        self.assertEqual(node.jd["categoryType"], CategoryType.DATA)
        self.assertTrue(node.is_data)
        self.assertFalse(
            node.is_app,
            "'Data' category must not be inferred as Application "
            "(APP_TYPES/DATA_TYPES overlap regression, issue #26)",
        )

    def test_missing_categorytype_uninferable_raises_ginvalidnode(self):
        # Regression test for 5d: a construct-only category (outside both
        # APP_TYPES and DATA_TYPES) with no categoryType must raise
        # GInvalidNode naming the node, rather than a bare KeyError.
        with self.assertRaises(GInvalidNode) as cm:
            _make_node({"id": "n4", "name": "my_scatter", "category": Categories.SCATTER})
        message = str(cm.exception)
        self.assertIn("my_scatter", message)
        self.assertIn("n4", message)
        self.assertIn(Categories.SCATTER, message)

    def test_explicit_categorytype_is_not_overridden(self):
        # A node that already carries an explicit categoryType (e.g. a
        # construct node produced by the translator itself) must be left
        # alone -- inference/validation only runs when categoryType is
        # absent.
        node = _make_node(
            {
                "id": "n5",
                "name": "n5",
                "category": Categories.SCATTER,
                "categoryType": CategoryType.CONSTRUCT,
            }
        )
        self.assertEqual(node.jd["categoryType"], CategoryType.CONSTRUCT)


class TestLGNodeModelSplit(unittest.TestCase):
    def test_model_node_constructs_without_unroll_subclass(self):
        node = ModelLGNode(
            {
                "id": "core-node",
                "name": "core-node",
                "category": Categories.FILE,
                "categoryType": CategoryType.DATA,
                "fields": [],
            },
            group_q=defaultdict(list),
            done_dict={},
            ssid="test_model",
        )

        self.assertEqual("core-node", node.id)
        self.assertEqual({}, node.input_ports)
        self.assertEqual({}, node.output_ports)

    def test_unroll_lgnode_inherits_model_behavior(self):
        node = _make_node(
            {
                "id": "model-node",
                "name": "model-node",
                "category": Categories.FILE,
                "categoryType": CategoryType.DATA,
            }
        )
        target = _make_node(
            {
                "id": "target",
                "name": "target",
                "category": Categories.PYTHON_APP,
                "categoryType": CategoryType.APPLICATION,
            }
        )

        self.assertIsInstance(node, ModelLGNode)
        self.assertEqual("model-node", node.name)
        self.assertTrue(node.is_start)
        self.assertTrue(node.is_dag_root)
        node.add_output(target)
        target.add_input(node)
        self.assertEqual([target], node.outputs)
        self.assertEqual([node], target.inputs)

    def test_structural_predicates_tolerate_missing_category(self):
        node = ModelLGNode(
            {
                "id": "missing-category",
                "name": "missing-category",
                "category": Categories.FILE,
                "categoryType": CategoryType.DATA,
                "fields": [],
            },
            group_q=defaultdict(list),
            done_dict={},
            ssid="test_model",
        )
        del node.jd["category"]

        self.assertTrue(node.is_dag_root)

        node.add_input(object())
        self.assertFalse(node.is_start_listener)

    def test_model_add_child_uses_registry_handler(self):
        parent = _make_node(
            {
                "id": "parent",
                "name": "parent",
                "category": Categories.SCATTER,
                "categoryType": CategoryType.CONSTRUCT,
                "isGroup": True,
            }
        )
        child = _make_node(
            {
                "id": "child",
                "name": "child",
                "category": Categories.LOOP,
                "categoryType": CategoryType.CONSTRUCT,
                "isGroup": True,
            }
        )

        parent.add_child(child)

        self.assertEqual([child], parent.children)


if __name__ == "__main__":
    unittest.main()
