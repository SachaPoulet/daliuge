from enum import Enum
from typing import TYPE_CHECKING, Iterator, Optional, Protocol, Sequence

from dlg.common import dropdict
from dlg.translator.errors import GInvalidLink

from ..coordinate import InstanceId
from ..model import Edge, LogicalLink

if TYPE_CHECKING:
    from ..lg_node import LGNode


ANY_CONSTRUCT = "*"


class HLevelRelation(Enum):
    SOURCE_HIGHER = "source_higher"
    EQUAL = "equal"
    TARGET_HIGHER = "target_higher"

    @classmethod
    def between(cls, source_h_level: int, target_h_level: int) -> "HLevelRelation":
        if source_h_level > target_h_level:
            return cls.SOURCE_HIGHER

        if source_h_level < target_h_level:
            return cls.TARGET_HIGHER

        return cls.EQUAL


EdgeKey = tuple[Optional[str], Optional[str], Optional[HLevelRelation]]


class GraphContext(Protocol):
    session_id: str

    def node(self, node_id: str) -> "LGNode":
        ...


class InstantiationContext(GraphContext, Protocol):
    loop_context: Optional[str]

    def drops_of(self, node_id: str) -> list[dropdict]:
        ...

    def add_drop(self, node_id: str, drop: dropdict) -> None:
        ...


class WiringContext(GraphContext, Protocol):
    def chunk_size(self, source: "LGNode", target: "LGNode") -> int:
        ...

    def split(
        self,
        drops: Sequence[dropdict],
        size: int,
    ) -> Iterator[Sequence[dropdict]]:
        ...


def validate_hierarchy(source: "LGNode", target: "LGNode") -> None:
    if source.h_related(target):
        return

    source_group = source.group
    target_group = target.group
    if source_group is not None and target_group is not None:
        if source_group.is_loop and target_group.is_loop:
            while source_group is not None and target_group is not None:
                if not source_group.is_loop or not target_group.is_loop:
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
    construct_type: str
    edge_keys: tuple[EdgeKey, ...]

    def degree_of_parallelism(
        self,
        node: "LGNode",
        ctx: Optional[GraphContext] = None,
    ) -> int:
        ...

    def instantiate(
        self,
        node: "LGNode",
        coord: InstanceId,
        ctx: InstantiationContext,
    ) -> list[dropdict]:
        ...

    def synthesise_links(
        self,
        node: "LGNode",
        ctx: GraphContext,
    ) -> list[LogicalLink]:
        ...

    def resolve_edges(
        self,
        link: LogicalLink,
        sources: Sequence[dropdict],
        targets: Sequence[dropdict],
        ctx: WiringContext,
    ) -> list[Edge]:
        ...

    def validate_link(
        self,
        source: "LGNode",
        target: "LGNode",
    ) -> None:
        ...
