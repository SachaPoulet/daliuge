class StageException(Exception):
    def __init__(self, stage: str, message: str = ""):
        self.stage = stage
        detail = f": {message}" if message else ""
        super().__init__(f"stage {stage!r} failed{detail}")


class GraphConfigException(Exception):
    """
    Base exception for graph configs
    """


class GraphConfigNodeDoesNotExist(GraphConfigException):
    """
    Raised if the Graph Configuration supplies an ID for a Node that does not exist in
    the Logical Graph
    """

    def __init__(self, config_id):
        self.msg = (f"Node in graphConfig does not exist in Logical Graph\n"
                    f"id: {config_id}\n")

    def __str__(self):
        return self.msg


class GraphConfigFieldDoesNotExist(GraphConfigException):
    """
    Raised if the Graph Configuration supplies an ID for a field that does not exist in
    the Logical Graph
    """
    def __init__(self, graph_id):
        self.msg = (f"Field in graphConfig does not exist in Logical Graph\n"
                    f"id: {graph_id}\n")

    def __str__(self):
        return self.msg


class GraphException(Exception):
    pass


class GInvalidLink(GraphException):
    pass


class GInvalidNode(GraphException):
    pass
