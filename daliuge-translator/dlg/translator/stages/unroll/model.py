from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


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
