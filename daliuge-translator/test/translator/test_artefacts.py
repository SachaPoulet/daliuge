#
#    ICRAR - International Centre for Radio Astronomy Research
#    (c) UWA - The University of Western Australia, 2015
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
Tests the typed artefact envelopes.

Scope is the envelopes own behaviour: the wire conventions they decode and
re-encode, the guards on malformed input, the isolation their copies provide,
and the type relationships the Pipeline will later rely on.
"""
import copy
import dataclasses
import unittest

from parameterized import parameterized

from dlg.common import dropdict
from dlg.translator.artefacts import (
    LogicalArtefact,
    LogicalGraph,
    LogicalGraphTemplate,
    PhysicalArtefact,
    PhysicalGraph,
    PhysicalGraphTemplate,
    PhysicalGraphTemplatePartitioned,
)

LOGICAL_TYPES = [
    ("LogicalGraphTemplate", LogicalGraphTemplate),
    ("LogicalGraph", LogicalGraph),
]

PHYSICAL_TYPES = [
    ("PhysicalGraphTemplate", PhysicalGraphTemplate),
    ("PhysicalGraphTemplatePartitioned", PhysicalGraphTemplatePartitioned),
    ("PhysicalGraph", PhysicalGraph),
]

ALL_TYPES = LOGICAL_TYPES + PHYSICAL_TYPES

REPRODATA = {"rmode": "1", "RERUN": {"signature": "abc"}}


def logical_wire(with_reprodata=True):
    """An EAGLE-shaped document. Nested containers are deliberate: the
    isolation tests need something at depth >= 2 to mutate."""
    wire = {
        "modelData": {"filePath": "test.graph"},
        "nodeDataArray": [
            {"id": 1, "categoryType": "Application", "fields": [{"name": "n"}]},
            {"id": 2, "categoryType": "Data", "fields": []},
        ],
        "linkDataArray": [{"from": 1, "to": 2, "fromPort": "p"}],
    }
    if with_reprodata:
        wire["reprodata"] = dict(REPRODATA)
    return wire


def physical_wire(n=2, reprodata=REPRODATA):
    """A flat drop list. `reprodata=None` omits the trailing element entirely,
    which is what `partition` returns and what a hand-made graph may look
    like."""
    wire = [
        dropdict(
            {
                "oid": "session_-1_%d" % i,
                "iid": str(i),
                "categoryType": "Application",
                "inputs": [{"x": "y"}],
            }
        )
        for i in range(n)
    ]
    if reprodata is not None:
        wire.append(dict(reprodata))
    return wire


def wire_for(cls, **kwargs):
    """Dispatch to the right fixture for an artefact class."""
    if issubclass(cls, LogicalArtefact):
        return logical_wire(**kwargs)
    return physical_wire(**kwargs)


class RoundTripTest(unittest.TestCase):
    """
    from_wire and to_wire are inverses, in the directions each is claimed for.
    """

    @parameterized.expand(ALL_TYPES)
    def test_envelope_round_trip(self, _name, cls):
        """from_wire(to_wire(x)) == x holds unconditionally."""
        artefact = cls.from_wire(wire_for(cls))
        self.assertEqual(cls.from_wire(artefact.to_wire()), artefact)

    @parameterized.expand(ALL_TYPES)
    def test_wire_round_trip(self, _name, cls):
        """to_wire(from_wire(w)) == w for the wire forms the translator emits."""
        wire = wire_for(cls)
        self.assertEqual(cls.from_wire(wire).to_wire(), wire)

    @parameterized.expand(LOGICAL_TYPES)
    def test_wire_round_trip_without_reprodata(self, _name, cls):
        """A logical graph that never went through fill has no reprodata key,
        and must not gain one."""
        wire = logical_wire(with_reprodata=False)
        self.assertEqual(cls.from_wire(wire).to_wire(), wire)

    @parameterized.expand(PHYSICAL_TYPES)
    def test_wire_round_trip_with_empty_reprodata(self, _name, cls):
        """unroll appends {} when the logical graph carried no reprodata."""
        wire = physical_wire(reprodata={})
        self.assertEqual(cls.from_wire(wire).to_wire(), wire)

    @parameterized.expand(PHYSICAL_TYPES)
    def test_bare_list_gains_empty_reprodata(self, _name, cls):
        """The one deliberate asymmetry: a list with no trailing element is
        normalised rather than reproduced verbatim.

        This is the fix for `dlg translator partition`, which pops
        unconditionally and so discards the last drop of such a list. A test
        asserting identity here would be asserting the bug.
        """
        drops = physical_wire(reprodata=None)
        self.assertEqual(cls.from_wire(drops).to_wire(), drops + [{}])


class TrailingElementTest(unittest.TestCase):
    """
    Decoding the trailing-element convention: the reason this module exists.
    """

    def test_populated_reprodata_is_split_off(self):
        wire = physical_wire(n=2)
        pgt = PhysicalGraphTemplate.from_wire(wire)
        self.assertEqual(pgt.drops, wire[:-1])
        self.assertEqual(pgt.reprodata, REPRODATA)

    def test_empty_reprodata_is_not_a_drop(self):
        """unroll always appends, so the trailing element is {} whenever the
        logical graph carried no reprodata.

        The engine's competing predicate -- `"rmode" in graphSpec[-1]`, at
        composite_manager.py:451 -- reads this {} as a drop. Ours must not.
        """
        wire = physical_wire(n=2, reprodata={})
        pgt = PhysicalGraphTemplate.from_wire(wire)
        self.assertEqual(len(pgt.drops), 2)
        self.assertEqual(pgt.reprodata, {})

    def test_absent_reprodata_leaves_every_element_a_drop(self):
        """partition neither takes nor returns a trailing element."""
        wire = physical_wire(n=3, reprodata=None)
        pgt = PhysicalGraphTemplate.from_wire(wire)
        self.assertEqual(len(pgt.drops), 3)
        self.assertEqual(pgt.reprodata, {})

    def test_empty_list(self):
        pgt = PhysicalGraphTemplate.from_wire([])
        self.assertEqual(pgt.drops, [])
        self.assertEqual(pgt.reprodata, {})

    def test_falsy_oid_is_read_as_reprodata(self):
        """Characterization, not endorsement.

        The predicate is the absence of a truthy `oid`, matching
        translator_rest.py:955 and start_dlg_cluster.py:347. A trailing drop
        carrying oid="" is therefore taken for reprodata. Pinned here so that
        changing the predicate is a visible decision rather than silent drift.
        """
        wire = [dropdict({"oid": "a"}), {"oid": ""}]
        pgt = PhysicalGraphTemplate.from_wire(wire)
        self.assertEqual(len(pgt.drops), 1)
        self.assertEqual(pgt.reprodata, {"oid": ""})

    def test_reprodata_property_defaults_to_empty_dict(self):
        """Mirrors lg.py:154's `lg.get("reprodata", {})`."""
        lgt = LogicalGraphTemplate.from_wire(logical_wire(with_reprodata=False))
        self.assertEqual(lgt.reprodata, {})


class ValidationTest(unittest.TestCase):
    """
    The guards, and the quality of what they report.
    """

    @parameterized.expand(LOGICAL_TYPES)
    def test_logical_rejects_non_dict(self, _name, cls):
        # (payload, how the message should name it)
        for payload, shown in (([], "list"), ('{"nodeDataArray": []}', "str"), (None, "NoneType")):
            with self.subTest(payload=shown):
                with self.assertRaises(TypeError) as ctx:
                    cls.from_wire(payload)
                self.assertIn("must be a dict", str(ctx.exception))
                self.assertIn(shown, str(ctx.exception))

    @parameterized.expand(PHYSICAL_TYPES)
    def test_physical_rejects_non_list(self, _name, cls):
        """The wire form is a frozen contract, so this holds regardless of how
        `drops` is represented internally."""
        for payload, shown in (({}, "dict"), ("[]", "str"), (None, "NoneType")):
            with self.subTest(payload=shown):
                with self.assertRaises(TypeError) as ctx:
                    cls.from_wire(payload)
                self.assertIn("must be a list", str(ctx.exception))
                self.assertIn(shown, str(ctx.exception))

    @parameterized.expand(LOGICAL_TYPES)
    def test_logical_rejects_non_dict_reprodata(self, _name, cls):
        """A reprodata slot holding something other than a dict is caught at
        the boundary that owns the key, rather than one stage later where it
        would surface as the PGT's trailing element."""
        for bad, shown in ((None, "NoneType"), ([], "list"), ("x", "str"), (1, "int")):
            with self.subTest(reprodata=shown):
                wire = logical_wire(with_reprodata=False)
                wire["reprodata"] = bad
                with self.assertRaises(TypeError) as ctx:
                    cls.from_wire(wire)
                self.assertIn("'reprodata' must be a dict", str(ctx.exception))
                self.assertIn(shown, str(ctx.exception))

    @parameterized.expand(LOGICAL_TYPES)
    def test_absent_reprodata_key_is_not_rejected(self, _name, cls):
        """The guard keys off the key's *presence*, not its value's nullness.

        `payload.get("reprodata")` returns None for an absent key and for one
        explicitly set to null alike, so a value-based guard cannot separate
        them. `"reprodata" in payload` can: an absent key is fine, an explicit
        null is not -- covered by the null case above.
        """
        wire = logical_wire(with_reprodata=False)
        self.assertNotIn("reprodata", wire)
        self.assertEqual(cls.from_wire(wire).reprodata, {})

    @parameterized.expand(PHYSICAL_TYPES)
    def test_physical_rejects_non_dict_element(self, _name, cls):
        wire = [dropdict({"oid": "a"}), "not a drop", {"rmode": "1"}]
        with self.assertRaises(TypeError) as ctx:
            cls.from_wire(wire)
        self.assertIn("element 1", str(ctx.exception))
        self.assertIn("str", str(ctx.exception))

    @parameterized.expand(ALL_TYPES)
    def test_error_names_the_concrete_subclass(self, name, cls):
        """The bases share one implementation, so the message has to come from
        cls.__name__ rather than a hardcoded string."""
        bad = [] if issubclass(cls, LogicalArtefact) else {}
        with self.assertRaises(TypeError) as ctx:
            cls.from_wire(bad)
        self.assertTrue(str(ctx.exception).startswith(name), str(ctx.exception))


class IsolationTest(unittest.TestCase):
    """
    The deepcopy contract. Every case here passes under a deep copy and fails
    under a shallow one.
    """

    @staticmethod
    def _scribble(wire):
        """Write into `wire` the way the compiler does: at depth >= 2, where a
        shallow copy still shares the containers."""
        if isinstance(wire, dict):
            wire["linkDataArray"][0]["is_stream"] = True
            wire["nodeDataArray"][0]["fields"].append({"name": "injected"})
        else:
            wire[0]["inputs"].append({"injected": True})

    @parameterized.expand(ALL_TYPES)
    def test_caller_cannot_mutate_the_envelope(self, _name, cls):
        wire = wire_for(cls)
        artefact = cls.from_wire(wire)
        # Snapshot independently: a to_wire() result would share the very
        # containers the mutation targets, and could not witness the leak.
        before = copy.deepcopy(artefact.to_wire())

        self._scribble(wire)

        self.assertEqual(artefact.to_wire(), before)

    @parameterized.expand(ALL_TYPES)
    def test_envelope_survives_mutation_of_its_own_output(self, _name, cls):
        """to_wire() hands out something the caller owns outright. The repro
        hooks mutate it in place; LG.__init__ writes into it too."""
        artefact = cls.from_wire(wire_for(cls))
        before = copy.deepcopy(artefact.to_wire())

        emitted = artefact.to_wire()
        self._scribble(emitted)
        if isinstance(emitted, dict):
            emitted["reprodata"]["clobbered"] = True
        else:
            emitted.pop()

        self.assertEqual(artefact.to_wire(), before)

    @parameterized.expand(ALL_TYPES)
    def test_to_wire_returns_independent_objects(self, _name, cls):
        artefact = cls.from_wire(wire_for(cls))
        first, second = artefact.to_wire(), artefact.to_wire()
        self.assertIsNot(first, second)
        self.assertEqual(first, second)

        self._scribble(first)
        self.assertNotEqual(first, second)

    @parameterized.expand(PHYSICAL_TYPES)
    def test_dropdict_class_survives(self, _name, cls):
        """deepcopy must not degrade dropdict to a plain dict -- the engine's
        graph_loader and the translator both rely on the subclass."""
        artefact = cls.from_wire(physical_wire())
        self.assertIsInstance(artefact.drops[0], dropdict)
        self.assertIsInstance(artefact.to_wire()[0], dropdict)


class TypeIdentityTest(unittest.TestCase):
    """
    The type relationships P1-3's Pipeline typing depends on.
    """

    @parameterized.expand(ALL_TYPES)
    def test_from_wire_returns_the_concrete_subclass(self, _name, cls):
        self.assertIs(type(cls.from_wire(wire_for(cls))), cls)

    def test_no_artefact_is_a_subclass_of_another(self):
        """The five hang off two bases as siblings rather than forming a chain.

        Were PhysicalGraph a subclass of PhysicalGraphTemplate, a type checker
        would accept a mapped PG wherever a PGT is expected -- including
        PartitionStage.run() -- which is exactly the mis-ordering P1-3's
        re-typed Pipeline.then() exists to catch.
        """
        classes = [cls for _name, cls in ALL_TYPES]
        for first in classes:
            for second in classes:
                if first is not second:
                    self.assertFalse(
                        issubclass(first, second),
                        "%s must not be a subclass of %s"
                        % (first.__name__, second.__name__),
                    )

    def test_different_artefacts_with_identical_contents_are_unequal(self):
        wire = physical_wire()
        self.assertNotEqual(
            PhysicalGraphTemplate.from_wire(wire), PhysicalGraph.from_wire(wire)
        )
        logical = logical_wire()
        self.assertNotEqual(
            LogicalGraphTemplate.from_wire(logical), LogicalGraph.from_wire(logical)
        )

    @parameterized.expand(ALL_TYPES)
    def test_artefacts_are_frozen(self, _name, cls):
        artefact = cls.from_wire(wire_for(cls))
        field = "source" if issubclass(cls, LogicalArtefact) else "drops"
        with self.assertRaises(dataclasses.FrozenInstanceError):
            setattr(artefact, field, None)

    def test_bases_are_not_artefacts(self):
        """LogicalArtefact and PhysicalArtefact carry the shared implementation
        but are not themselves members of the chain."""
        for base in (LogicalArtefact, PhysicalArtefact):
            self.assertNotIn(base, [cls for _name, cls in ALL_TYPES])


if __name__ == "__main__":
    unittest.main()
