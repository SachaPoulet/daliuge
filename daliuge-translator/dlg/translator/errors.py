class StageException(Exception):
    def __init__(self, stage: str, message: str = ""):
        self.stage = stage
        detail = f": {message}" if message else ""
        super().__init__(f"stage {stage!r} failed{detail}")
