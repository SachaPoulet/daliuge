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

"""Tests that physical graph template stamping is idempotent."""

import unittest

from dlg.common.reproducibility.constants import ReproducibilityFlags
from dlg.common.reproducibility.reproducibility import (
    init_pgt_partition_repro_data,
    init_pgt_unroll_repro_data,
)


RMODE = ReproducibilityFlags.RECOMPUTE


def _make_drop(oid, outputs=None):
    drop = {
        "oid": oid,
        "categoryType": "Application",
        "dt": 1.0,
        "rank": oid,
        "node": f"#{oid}",
        "island": "#0",
        "reprodata": {
            "rmode": str(RMODE.value),
            RMODE.name: {"lg_blockhash": f"logical-{oid}"},
        },
    }
    if outputs:
        drop["outputs"] = outputs
    return drop


def _make_pgt():
    """Return a small connected PGT followed by its graph-level reprodata."""
    return [
        _make_drop(1, [2]),
        _make_drop(2, [3]),
        _make_drop(3),
        {"rmode": str(RMODE.value)},
    ]


def _pgt_stamp(pgt):
    """Capture the graph signature and every per-drop PGT block hash."""
    return (
        pgt[-1][RMODE.name]["signature"],
        {
            drop["oid"]: drop["reprodata"][RMODE.name]["pgt_blockhash"]
            for drop in pgt[:-1]
        },
    )


class PGTStampingIdempotenceTest(unittest.TestCase):
    """A second stamp must not incorporate hashes produced by the first."""

    def test_pgt_unroll_stamping_is_idempotent(self):
        pgt = init_pgt_unroll_repro_data(_make_pgt())
        first_signature, first_drop_hashes = _pgt_stamp(pgt)

        init_pgt_unroll_repro_data(pgt)
        second_signature, second_drop_hashes = _pgt_stamp(pgt)

        self.assertEqual(first_signature, second_signature)
        self.assertEqual(first_drop_hashes, second_drop_hashes)

    def test_pgt_partition_stamping_is_idempotent(self):
        pgt = init_pgt_unroll_repro_data(_make_pgt())
        init_pgt_partition_repro_data(pgt)
        first_signature, first_drop_hashes = _pgt_stamp(pgt)

        init_pgt_partition_repro_data(pgt)
        second_signature, second_drop_hashes = _pgt_stamp(pgt)

        self.assertEqual(first_signature, second_signature)
        self.assertEqual(first_drop_hashes, second_drop_hashes)
