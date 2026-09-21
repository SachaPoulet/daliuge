from typing import Any

from dlg.translator.errors import GInvalidNode
from dlg.translator.vocabulary import Categories

from .base import ConstructHandler
from .gather import GatherHandler
from .groupby import GroupByHandler
from .leaf import LeafHandler
from .loop import LoopHandler
from .mpi import MPIHandler
from .scatter import ScatterHandler
from .service import ServiceHandler
from .subgraph import SubgraphHandler


_handlers: dict[str, ConstructHandler] = {}


def register_handler(handler: ConstructHandler) -> None:
    _handlers[handler.construct_type] = handler


def get_handler(construct_type: str) -> ConstructHandler:
    return _handlers[construct_type]


def get_handler_for_node(node: Any) -> ConstructHandler:
    if node.is_group:
        construct_type = (
            Categories.SUBGRAPH if node.is_subgraph else node.category
        )

        if construct_type not in _handlers:
            raise GInvalidNode(
                "Unrecognised (Group) Logical Graph Node: '{0}'".format(
                    node.category
                )
            )

        return get_handler(construct_type)

    if node.is_mpi:
        return get_handler(Categories.MPI)

    return get_handler("leaf")


register_handler(ScatterHandler())
register_handler(GatherHandler())
register_handler(GroupByHandler())
register_handler(LoopHandler())
register_handler(MPIHandler())
register_handler(ServiceHandler())
register_handler(SubgraphHandler())
register_handler(LeafHandler())
