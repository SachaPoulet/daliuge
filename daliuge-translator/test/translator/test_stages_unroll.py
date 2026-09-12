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
Tests for UnrollStage (2-3, selected low-risk module migration).

UnrollStage is a thin wrapper: `run()` delegates to `pg_generator.unroll()`
and `stamp()` delegates to `init_pgt_unroll_repro_data()`, converting to/from
the typed artefact envelopes on either side. These tests mock both delegate
functions -- their own behaviour is/should be tested where they're defined --
and check only the glue: are they called with the right arguments, and is
the result wrapped in the right envelope type.

Companion to test_stages_map.py / test_stages_partition.py, same pattern.
"""
import unittest
from unittest.mock import patch

from dlg.translator.artefacts import LogicalGraphTemplate, PhysicalGraphTemplate
from dlg.translator.stages.unroll.stage import UnrollStage, UnrollOptions


def lgt_wire():
    return {
        "modelData": {"filePath": "test.graph"},
        "nodeDataArray": [],
        "linkDataArray": [],
    }


def pgt_wire():
    # PhysicalArtefact's wire form always ends with a reprodata trailer
    # (possibly empty) -- see artefacts.py: `to_wire()` appends it
    # unconditionally, and `from_wire()` only treats the last element as
    # drops data if it has an 'oid'. Include the trailer here so this
    # round-trips exactly through from_wire()/to_wire().
    return [{"oid": "a"}, {"oid": "b"}, {}]


class TestUnrollStageRun(unittest.TestCase):
    @patch("dlg.translator.stages.unroll.stage.unroll")
    def test_run_delegates_to_pg_generator_unroll(self, mock_unroll):
        mock_unroll.return_value = pgt_wire()
        lgt = LogicalGraphTemplate.from_wire(lgt_wire())

        result = UnrollStage().run(lgt)

        mock_unroll.assert_called_once()
        _, kwargs = mock_unroll.call_args
        self.assertEqual(kwargs["lg"], lgt.to_wire())
        self.assertIsNone(kwargs["oid_prefix"])
        self.assertFalse(kwargs["zerorun"])
        self.assertIsNone(kwargs["app"])

        self.assertIsInstance(result, PhysicalGraphTemplate)
        self.assertEqual(result.to_wire(), pgt_wire())

    @patch("dlg.translator.stages.unroll.stage.unroll")
    def test_run_passes_through_unroll_options(self, mock_unroll):
        mock_unroll.return_value = pgt_wire()
        lgt = LogicalGraphTemplate.from_wire(lgt_wire())
        opts = UnrollOptions(oid_prefix="TEST", zerorun=True, app="dlg.apps.Foo")

        UnrollStage(opts).run(lgt)

        _, kwargs = mock_unroll.call_args
        self.assertEqual(kwargs["oid_prefix"], "TEST")
        self.assertTrue(kwargs["zerorun"])
        self.assertEqual(kwargs["app"], "dlg.apps.Foo")

    @patch("dlg.translator.stages.unroll.stage.unroll")
    def test_run_passes_a_copy_not_the_original(self, mock_unroll):
        # unroll() mutates/consumes its `lg` argument -- run() must hand it
        # the wire form produced by to_wire() (already a deepcopy), never
        # the LogicalGraphTemplate's own backing dict.
        mock_unroll.side_effect = lambda lg, **_: pgt_wire()
        lgt = LogicalGraphTemplate.from_wire(lgt_wire())

        UnrollStage().run(lgt)

        _, kwargs = mock_unroll.call_args
        self.assertIsNot(kwargs["lg"], lgt.source)

    def test_name_is_unroll(self):
        self.assertEqual(UnrollStage.name, "unroll")


class TestUnrollStageStamp(unittest.TestCase):
    @patch("dlg.translator.stages.unroll.stage.init_pgt_unroll_repro_data")
    def test_stamp_delegates_to_reproducibility_hook(self, mock_stamp):
        stamped_wire = [{"oid": "a", "reprodata": {"stamped": True}}, {}]
        mock_stamp.return_value = stamped_wire
        pgt = PhysicalGraphTemplate.from_wire(pgt_wire())

        result = UnrollStage().stamp(pgt)

        mock_stamp.assert_called_once_with(pgt.to_wire())
        self.assertIsInstance(result, PhysicalGraphTemplate)
        self.assertEqual(result.to_wire(), stamped_wire)

    @patch("dlg.translator.stages.unroll.stage.init_pgt_unroll_repro_data")
    def test_stamp_hands_the_hook_a_copy_not_the_original(self, mock_stamp):
        # The hook mutates its argument in place -- stamp() must round-trip
        # through to_wire() so the PGT passed in is never the same object
        # the hook mutates.
        mock_stamp.side_effect = lambda wire: wire
        pgt = PhysicalGraphTemplate.from_wire(pgt_wire())

        UnrollStage().stamp(pgt)

        (passed_wire,), _ = mock_stamp.call_args
        self.assertIsNot(passed_wire, pgt.drops)


if __name__ == "__main__":
    unittest.main()
