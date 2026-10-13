from dlg.translator.vocabulary import Categories

from .leaf import LeafHandler


class BranchHandler(LeafHandler):
    """branch nodes handler, unroll and wire like leaf nodes."""

    construct_type = Categories.BRANCH