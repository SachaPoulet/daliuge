from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LogicalLink:
    source: Any
    target: Any
    source_port: Any = None
    target_port: Any = None
    is_stream: bool = False
    loop_aware: bool = False


@dataclass(frozen=True)
class Edge:
    source: Any
    target: Any