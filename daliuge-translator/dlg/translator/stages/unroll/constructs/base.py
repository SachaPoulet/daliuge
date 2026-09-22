from typing import Any, Protocol

from dlg.common import dropdict

from ..coordinate import InstanceId
from ..model import Edge, EdgeKey, LogicalLink


class ConstructHandler(Protocol):
    construct_type: str
    edge_keys: tuple[EdgeKey, ...]

    def degree_of_parallelism(self, node: Any, ctx: Any) -> int:
        ...

    def instantiate(
        self,
        node: Any,
        coord: InstanceId,
        ctx: Any,
    ) -> list[dropdict]:
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
