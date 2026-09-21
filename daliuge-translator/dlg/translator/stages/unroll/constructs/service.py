from typing import Any

from dlg.translator.vocabulary import Categories


class ServiceHandler:
    construct_type = Categories.SERVICE

    def degree_of_parallelism(self, node: Any, ctx: Any) -> int:
        return 1