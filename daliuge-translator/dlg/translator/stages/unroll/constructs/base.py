from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Iterator, Optional, Protocol, Sequence

from dlg.common import dropdict
from dlg.translator.errors import GInvalidLink
from dlg.translator.vocabulary import Categories

from ..coordinate import InstanceId

if TYPE_CHECKING:
    from ..model import Edge, LGNode, LogicalLink


ANY_CONSTRUCT = "*"


class HLevelRelation(Enum):
    """how does a link's source and target compare in hierarchy (h) level"""

    SOURCE_HIGHER = "source_higher"
    EQUAL = "equal"
    TARGET_HIGHER = "target_higher"

    @classmethod
    def between(cls, source_h_level: int, target_h_level: int) -> "HLevelRelation":
        # Classify a source/target pair by comparing their h levels
        if source_h_level > target_h_level:
            return cls.SOURCE_HIGHER

        if source_h_level < target_h_level:
            return cls.TARGET_HIGHER

        return cls.EQUAL


EdgeKey = tuple[Optional[str], Optional[str], Optional[HLevelRelation]]


class GraphContext(Protocol):
    """read access to logical graph that handlers are working on"""

    session_id: str

    def node(self, node_id: str) -> "LGNode":
        ...


class InstantiationContext(GraphContext, Protocol):
    """Graph context passed to instantiate, with the DROPs made so far"""

    loop_context: Optional[str]

    def drops_of(self, node_id: str) -> list[dropdict]:
        # return the DROPs already instantiated for this node
        ...

    def add_drop(self, node_id: str, drop: dropdict) -> None:
        # record a DROP instantiated for this node
        ...


class WiringContext(GraphContext, Protocol):
    """graph context passed to resolve_edges, with chunking helpers"""

    def chunk_size(self, source: "LGNode", target: "LGNode") -> int:
        # return chunk size for a link.
        # (the Gather or GroupBy width when the target is one, otherwise
        # the DoP ratio between source and target)
        ...

    def split(
        self,
        drops: Sequence[dropdict],
        size: int,
    ) -> Iterator[Sequence[dropdict]]:
        # split DROPs into consecutive chunks of size
        ...


def validate_hierarchy(source: "LGNode", target: "LGNode") -> None:
    """check link's source and target are hierarchically related"""
    if source.h_related(target):
        return

    source_group = source.group
    target_group = target.group
    if source_group is not None and target_group is not None:
        from .registry import is_construct

        if is_construct(source_group, Categories.LOOP) and is_construct(
            target_group, Categories.LOOP
        ):
            while source_group is not None and target_group is not None:
                if not is_construct(
                    source_group, Categories.LOOP
                ) or not is_construct(target_group, Categories.LOOP):
                    break
                if source_group.dop != target_group.dop:
                    raise GInvalidLink(
                        "{0} and {1} are not loop synchronised: {2} <> {3}".format(
                            source_group.id,
                            target_group.id,
                            source_group.dop,
                            target_group.dop,
                        )
                    )
                source_group = source_group.group
                target_group = target_group.group
            return

    raise GInvalidLink(
        "{0} and {1} are not hierarchically related: {2}-({4}) and {3}-({5})".format(
            source.id,
            target.id,
            source.group_hierarchy,
            target.group_hierarchy,
            source.name,
            target.name,
        )
    )


class ConstructHandler(Protocol):
    """Interface each construct handler implements.

    A handler owns one construct type and is looked up through the registry.
    is_group_construct says whether  construct groups other nodes,
    edge_keys lists edge cases it resolves.
    """

    construct_type: str
    is_group_construct: bool
    edge_keys: tuple[EdgeKey, ...]

    def degree_of_parallelism(
        self,
        node: "LGNode",
        ctx: Optional[GraphContext] = None,
    ) -> int:
        # return how many instances of the node to create
        ...

    def instantiate(
        self,
        node: "LGNode",
        coord: InstanceId,
        ctx: InstantiationContext,
    ) -> list[dropdict]:
        # create DROPs for one instance of the node at coord
        ...

    def synthesise_links(
        self,
        node: "LGNode",
        ctx: GraphContext,
    ) -> list[LogicalLink]:
        # return the artificial links the construct adds to the graph
        ...

    def resolve_edges(
        self,
        link: LogicalLink,
        sources: Sequence[dropdict],
        targets: Sequence[dropdict],
        ctx: WiringContext,
    ) -> list[Edge]:
        # pair a link's source and target DROPs into edges
        ...

    def validate_link(
        self,
        source: "LGNode",
        target: "LGNode",
    ) -> None:
        # raise GInvalidLink if the construct does not allow link
        ...
