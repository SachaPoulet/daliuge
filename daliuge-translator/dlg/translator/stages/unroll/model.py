from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from dlg.common import dropdict

if TYPE_CHECKING:
    from .lg_node import LGNode


@dataclass(frozen=True)
class LogicalLink:
    source: "LGNode"
    target: "LGNode"
    source_port: Optional[str] = None
    target_port: Optional[str] = None
    is_stream: bool = False
    loop_aware: bool = False


@dataclass(frozen=True)
class Edge:
    link: LogicalLink
    source: dropdict
    target: dropdict
