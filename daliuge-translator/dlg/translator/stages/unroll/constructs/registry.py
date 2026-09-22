from typing import Iterator, Optional

from .base import ConstructHandler
from ..model import ANY_CONSTRUCT, EdgeKey, HLevelRelation


_handlers: dict[str, ConstructHandler] = {}
_edge_handlers: dict[EdgeKey, ConstructHandler] = {}


def register_handler(handler: ConstructHandler) -> None:
    _handlers[handler.construct_type] = handler

    for key in handler.edge_keys:
        _edge_handlers[key] = handler


def get_handler(construct_type: str) -> ConstructHandler:
    return _handlers[construct_type]


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
