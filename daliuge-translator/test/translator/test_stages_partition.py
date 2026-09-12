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
Tests for PartitionStage (2-3, selected low-risk module migration).

PartitionStage is a thin wrapper: `run()` delegates to
`pg_generator.partition()` and `stamp()` delegates to
`init_pgt_partition_repro_data()`, converting to/from the typed artefact
envelopes on either side. These tests mock both delegate functions -- their
own behaviour is/should be tested where they're defined -- and check only
the glue: are they called with the right arguments, and is the result
wrapped in the right envelope type.

Mirrors the pattern established in test_stages_unroll.py (issue #40).
"""
import unittest
from unittest.mock import patch

from dlg.translator.artefacts import (
    PhysicalGraphTemplate,
    PhysicalGraphTemplatePartitioned,
)
from dlg.translator.stages.partition.stage import PartitionStage, PartitionOptions


def pgt_wire():
    # PhysicalArtefact's wire form always ends with a reprodata trailer
    # (possibly empty) -- see artefacts.py: `to_wire()` appends it
    # unconditionally, and `from_wire()` only treats the last element as
    # drops data if it has an 'oid'. Include the trailer here so this
    # round-trips exactly through from_wire()/to_wire().
    return [{"oid": "a"}, {"oid": "b"}, {"repro": "pgt-reprodata"}]


def pgtp_drops():
    # bare drop list as returned by pg_generator.partition() -- no
    # reprodata trailer, that's added back by PartitionStage.run() itself.
    return [{"oid": "a", "node": "#0"}, {"oid": "b", "node": "#1"}]


class TestPartitionStageRun(unittest.TestCase):
    @patch("dlg.translator.stages.partition.stage.partition")
    def test_run_delegates_to_pg_generator_partition(self, mock_partition):
        mock_partition.return_value = pgtp_drops()
        pgt = PhysicalGraphTemplate.from_wire(pgt_wire())

        result = PartitionStage().run(pgt)

        mock_partition.assert_called_once()
        _, kwargs = mock_partition.call_args
        self.assertEqual(kwargs["pgt"], pgt.drops)
        self.assertEqual(kwargs["algo"], "metis")
        self.assertEqual(kwargs["num_partitions"], 1)
        self.assertEqual(kwargs["num_islands"], 1)
        self.assertEqual(kwargs["partition_label"], "partition")

        self.assertIsInstance(result, PhysicalGraphTemplatePartitioned)
        self.assertEqual(result.drops, pgtp_drops())
        self.assertEqual(result.reprodata, pgt.reprodata)

    @patch("dlg.translator.stages.partition.stage.partition")
    def test_run_passes_through_partition_options(self, mock_partition):
        mock_partition.return_value = pgtp_drops()
        pgt = PhysicalGraphTemplate.from_wire(pgt_wire())
        opts = PartitionOptions(
            algo="mysarkar",
            num_partitions=4,
            num_islands=2,
            partition_label="island",
            algo_params={"max_load_imb": 0.5},
        )

        PartitionStage(opts).run(pgt)

        _, kwargs = mock_partition.call_args
        self.assertEqual(kwargs["algo"], "mysarkar")
        self.assertEqual(kwargs["num_partitions"], 4)
        self.assertEqual(kwargs["num_islands"], 2)
        self.assertEqual(kwargs["partition_label"], "island")
        self.assertEqual(kwargs["max_load_imb"], 0.5)

    @patch("dlg.translator.stages.partition.stage.partition")
    def test_run_hands_partition_a_copy_not_the_original(self, mock_partition):
        # partition() is documented (via resource_map's sibling) to mutate
        # its pgt argument in place -- run() must pass a copy, never the
        # PhysicalGraphTemplate's own drops list.
        mock_partition.side_effect = lambda pgt, **_: pgt
        pgt = PhysicalGraphTemplate.from_wire(pgt_wire())

        PartitionStage().run(pgt)

        _, kwargs = mock_partition.call_args
        self.assertIsNot(kwargs["pgt"], pgt.drops)

    def test_name_is_partition(self):
        self.assertEqual(PartitionStage.name, "partition")


class TestPartitionStageStamp(unittest.TestCase):
    @patch("dlg.translator.stages.partition.stage.init_pgt_partition_repro_data")
    def test_stamp_delegates_to_reproducibility_hook(self, mock_stamp):
        stamped_wire = [{"oid": "a", "reprodata": {"stamped": True}}, {}]
        mock_stamp.return_value = stamped_wire
        pgtp = PhysicalGraphTemplatePartitioned.from_wire(
            [*pgtp_drops(), {"repro": "pgtp-reprodata"}]
        )

        result = PartitionStage().stamp(pgtp)

        mock_stamp.assert_called_once_with(pgtp.to_wire())
        self.assertIsInstance(result, PhysicalGraphTemplatePartitioned)
        self.assertEqual(result.to_wire(), stamped_wire)

    @patch("dlg.translator.stages.partition.stage.init_pgt_partition_repro_data")
    def test_stamp_hands_the_hook_a_copy_not_the_original(self, mock_stamp):
        # The hook mutates its argument in place -- stamp() must round-trip
        # through to_wire() so the PGT-P passed in is never the same object
        # the hook mutates.
        mock_stamp.side_effect = lambda wire: wire
        pgtp = PhysicalGraphTemplatePartitioned.from_wire(
            [*pgtp_drops(), {"repro": "pgtp-reprodata"}]
        )

        PartitionStage().stamp(pgtp)

        (passed_wire,), _ = mock_stamp.call_args
        self.assertIsNot(passed_wire, pgtp.drops)


if __name__ == "__main__":
    unittest.main()
