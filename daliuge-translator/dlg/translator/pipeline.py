from typing import Protocol, Generic, Sequence, TypeVar
from .errors import StageException


TIn = TypeVar("TIn", contravariant=True)
TOut = TypeVar("TOut")
TNext = TypeVar("TNext")


class Stage(Protocol[TIn, TOut]):
    name: str

    def run(self, artefact: TIn) -> TOut:
        ...

    def stamp(self, artefact: TOut) -> TOut:
        ...


class Pipeline(Generic[TIn, TOut]):
    def __init__(self, stages: Sequence[Stage], repro: bool = True):
        self._stages = list(stages)
        self._repro = repro

    def then(self, stage: Stage[TOut, TNext]) -> "Pipeline[TIn, TNext]":
        return Pipeline([*self._stages, stage], repro=self._repro)

    def run(self, artefact: TIn) -> TOut:
        for stage in self._stages:
            try:
                artefact = stage.run(artefact)
                if self._repro:
                    artefact = stage.stamp(artefact)
            except Exception as e:
                raise StageException(stage.name, str(e)) from e

        return artefact  # type: ignore
