from dlg.translator.vocabulary import Categories

from .leaf import LeafHandler


class BranchHandler(LeafHandler):
    construct_type = Categories.BRANCH