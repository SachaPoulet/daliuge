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
Tests for MapStage (2-3, selected low-risk module migration).

MapStage is a thin wrapper: `run()` delegates to `pg_generator.resource_map()`
and `stamp()` delegates to `init_pg_repro_data()`, converting to/from the
typed artefact envelopes on either side. These tests mock both delegate
functions -- their own behaviour is/should be tested where they're defined --
and check only the glue: are they called with the right arguments, and is
the result wrapped in the right envelope type.

Mirrors the pattern established in test_stages_unroll.py (issue #40).
"""
import unittest
from unittest.mock import patch

from dlg.translator.artefacts import PhysicalGraphTemplatePartitioned, PhysicalGraph
from dlg.translator.stages.map.stage import MapStage, MapOptions


def pgtp_wire():
    # PhysicalArtefact's wire form always ends with a reprodata trailer
    # (possibly empty) -- see artefacts.py: `to_wire()` appends it
    # unconditionally, and `from_wire()` only treats the last element as
    # drops data if it has an 'oid'. Include the trailer here so this
    # round-trips exactly through from_wire()/to_wire().
    return [
        {"oid": "a", "node": "#0"},
        {"oid": "b", "node": "#1"},
        {"repro": "pgtp-reprodata"},
    ]


def pg_drops():
    # bare drop list as returned by pg_generator.resource_map() -- no
    # reprodata trailer, that's added back by MapStage.run() itself.
    return [{"oid": "a", "node": "10.0.0.1"}, {"oid": "b", "node": "10.0.0.2"}]


class TestMapStageRun(unittest.TestCase):
    @patch("dlg.translator.stages.map.stage.resource_map")
    def test_run_delegates_to_pg_generator_resource_map(self, mock_resource_map):
        mock_resource_map.return_value = pg_drops()
        pgtp = PhysicalGraphTemplatePartitioned.from_wire(pgtp_wire())

        result = MapStage(MapOptions(nodes=["10.0.0.1", "10.0.0.2"])).run(pgtp)

        mock_resource_map.assert_called_once()
        _, kwargs = mock_resource_map.call_args
        self.assertEqual(kwargs["pgt"], pgtp.drops)
        self.assertEqual(kwargs["nodes"], ["10.0.0.1", "10.0.0.2"])
        self.assertEqual(kwargs["num_islands"], 1)
        self.assertTrue(kwargs["co_host_dim"])

        self.assertIsInstance(result, PhysicalGraph)
        self.assertEqual(result.drops, pg_drops())
        self.assertEqual(result.reprodata, pgtp.reprodata)

    @patch("dlg.translator.stages.map.stage.resource_map")
    def test_run_passes_through_map_options(self, mock_resource_map):
        mock_resource_map.return_value = pg_drops()
        pgtp = PhysicalGraphTemplatePartitioned.from_wire(pgtp_wire())
        opts = MapOptions(nodes=["10.0.0.1"], num_islands=3, co_host_dim=False)

        MapStage(opts).run(pgtp)

        _, kwargs = mock_resource_map.call_args
        self.assertEqual(kwargs["nodes"], ["10.0.0.1"])
        self.assertEqual(kwargs["num_islands"], 3)
        self.assertFalse(kwargs["co_host_dim"])

    @patch("dlg.translator.stages.map.stage.resource_map")
    def test_run_hands_resource_map_a_copy_not_the_original(self, mock_resource_map):
        # resource_map() is documented as mutating its pgt argument in place
        # (stage.py wraps it in deepcopy for exactly this reason) -- run()
        # must never pass the PhysicalGraphTemplatePartitioned's own drops.
        mock_resource_map.side_effect = lambda pgt, **_: pgt
        pgtp = PhysicalGraphTemplatePartitioned.from_wire(pgtp_wire())

        MapStage(MapOptions(nodes=["10.0.0.1"])).run(pgtp)

        _, kwargs = mock_resource_map.call_args
        self.assertIsNot(kwargs["pgt"], pgtp.drops)

    def test_name_is_map(self):
        self.assertEqual(MapStage.name, "map")


class TestMapStageStamp(unittest.TestCase):
    @patch("dlg.translator.stages.map.stage.init_pg_repro_data")
    def test_stamp_delegates_to_reproducibility_hook(self, mock_stamp):
        stamped_wire = [{"oid": "a", "reprodata": {"stamped": True}}, {}]
        mock_stamp.return_value = stamped_wire
        pg = PhysicalGraph.from_wire([*pg_drops(), {"repro": "pg-reprodata"}])

        result = MapStage(MapOptions(nodes=["10.0.0.1"])).stamp(pg)

        mock_stamp.assert_called_once_with(pg.to_wire())
        self.assertIsInstance(result, PhysicalGraph)
        self.assertEqual(result.to_wire(), stamped_wire)

    @patch("dlg.translator.stages.map.stage.init_pg_repro_data")
    def test_stamp_hands_the_hook_a_copy_not_the_original(self, mock_stamp):
        # The hook mutates its argument in place -- stamp() must round-trip
        # through to_wire() so the PG passed in is never the same object
        # the hook mutates.
        mock_stamp.side_effect = lambda wire: wire
        pg = PhysicalGraph.from_wire([*pg_drops(), {"repro": "pg-reprodata"}])

        MapStage(MapOptions(nodes=["10.0.0.1"])).stamp(pg)

        (passed_wire,), _ = mock_stamp.call_args
        self.assertIsNot(passed_wire, pg.drops)


if __name__ == "__main__":
    unittest.main()
