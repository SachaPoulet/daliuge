from typing import Any, Protocol

from ..coordinate import InstanceId
from ..model import Edge, LogicalLink


DropDict = dict[str, Any]


class ConstructHandler(Protocol):
    construct_type: str

    def degree_of_parallelism(self, node: Any, ctx: Any) -> int:
        ...

    def instantiate(
        self,
        node: Any,
        coord: InstanceId,
        ctx: Any,
    ) -> list[DropDict]:
        ...

    def synthesise_links(
        self,
        node: Any,
        ctx: Any,
    ) -> list[LogicalLink]:
        ...

    def resolve_edges(
        self,
        link: LogicalLink,
        sources: Any,
        targets: Any,
        ctx: Any,
    ) -> list[Edge]:
        ...

    def validate_link(
        self,
        link: LogicalLink,
        ctx: Any,
    ) -> None:
        ...