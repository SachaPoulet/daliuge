from typing import Any, Iterator, Optional

from dlg.translator.errors import GInvalidNode
from dlg.translator.vocabulary import Categories

from .base import ANY_CONSTRUCT, ConstructHandler, EdgeKey, HLevelRelation
from .branch import BranchHandler
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
        category = node.category
        handler = _handlers.get(category)
        if handler is not None and handler.is_group_construct:
            if (
                category != Categories.SUBGRAPH
                or "isSubGraphApp" not in node.jd
                or node.jd["isSubGraphApp"]
            ):
                return handler

        if node.jd.get("isSubGraphApp"):
            return get_handler(Categories.SUBGRAPH)

        raise GInvalidNode(
            "Unrecognised (Group) Logical Graph Node: '{0}'".format(
                node.category
            )
        )

    handler = _handlers.get(node.category)
    if handler is not None and not handler.is_group_construct:
        return handler

    return get_handler(LeafHandler.construct_type)


def is_construct(node: Any, construct_type: str) -> bool:
    """Check construct identity while preserving node-specific classification rules."""
    handler = _handlers.get(construct_type)
    if handler is None or handler.construct_type != construct_type:
        return False

    if construct_type in (Categories.SCATTER, Categories.LOOP) and not node.is_group:
        return False

    if construct_type == Categories.SUBGRAPH and "isSubGraphApp" in node.jd:
        return bool(node.jd["isSubGraphApp"])

    return node.category == construct_type


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
register_handler(BranchHandler())
register_handler(ServiceHandler())
register_handler(SubgraphHandler())
register_handler(LeafHandler())
