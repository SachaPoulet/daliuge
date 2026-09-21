from .base import ConstructHandler


_handlers: dict[str, ConstructHandler] = {}


def register_handler(handler: ConstructHandler) -> None:
    _handlers[handler.construct_type] = handler


def get_handler(construct_type: str) -> ConstructHandler:
    return _handlers[construct_type]