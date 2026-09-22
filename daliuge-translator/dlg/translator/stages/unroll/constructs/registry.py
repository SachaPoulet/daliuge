from typing import Any, Iterator, Optional

from dlg.translator.errors import GInvalidNode
from dlg.translator.vocabulary import Categories

from .base import ANY_CONSTRUCT, ConstructHandler, EdgeKey, HLevelRelation
from .gather import GatherHandler
from .groupby import GroupByHandler
from .leaf import LeafHandler
from .loop import LoopHandler
from .mpi import MPIHandler
from .scatter import ScatterHandler
from .service import ServiceHandler
from .subgraph import SubgraphHandler


_handlers: dict[str, ConstructHandler] = {}
_edge_handlers: dict[EdgeKey, ConstructHandler] = {}


def register_handler(handler: ConstructHandler) -> None:
    _handlers[handler.construct_type] = handler

    for key in handler.edge_keys:
        _edge_handlers[key] = handler


def get_handler(construct_type: str) -> ConstructHandler:
    return _handlers[construct_type]


def get_handler_for_node(node: Any) -> ConstructHandler:
    if node.is_group:
        if node.is_scatter:
            return get_handler(Categories.SCATTER)

        if node.is_gather:
            return get_handler(Categories.GATHER)

        if node.is_groupby:
            return get_handler(Categories.GROUP_BY)

        if node.is_loop:
            return get_handler(Categories.LOOP)

        if node.is_service:
            return get_handler(Categories.SERVICE)

        if node.is_subgraph:
            return get_handler(Categories.SUBGRAPH)

        raise GInvalidNode(
            "Unrecognised (Group) Logical Graph Node: '{0}'".format(
                node.jd["category"]
            )
        )

    if node.is_mpi:
        return get_handler(Categories.MPI)

    return get_handler(LeafHandler.construct_type)


def get_edge_handler(
    source_construct: Optional[str],
    target_construct: Optional[str],
    relation: HLevelRelation,
) -> ConstructHandler:
    for key in _edge_key_candidates(source_construct, target_construct, relation):
        handler = _edge_handlers.get(key)

        if handler is not None:
            return handler

    raise KeyError((source_construct, target_construct, relation))


def _edge_key_candidates(
    source_construct: Optional[str],
    target_construct: Optional[str],
    relation: HLevelRelation,
) -> Iterator[EdgeKey]:
    for source in (source_construct, ANY_CONSTRUCT):
        for target in (target_construct, ANY_CONSTRUCT):
            for value in (relation, None):
                yield source, target, value


register_handler(ScatterHandler())
register_handler(GatherHandler())
register_handler(GroupByHandler())
register_handler(LoopHandler())
register_handler(MPIHandler())
register_handler(ServiceHandler())
register_handler(SubgraphHandler())
register_handler(LeafHandler())
