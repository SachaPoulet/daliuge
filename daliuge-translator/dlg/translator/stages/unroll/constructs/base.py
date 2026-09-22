from enum import Enum
from typing import TYPE_CHECKING, Iterator, Optional, Protocol, Sequence

from dlg.common import dropdict

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
        link: LogicalLink,
        ctx: WiringContext,
    ) -> None:
        ...
