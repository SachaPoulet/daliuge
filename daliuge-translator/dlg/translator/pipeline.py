from typing import Protocol, Generic, Sequence, TypeVar
from .errors import StageException


TIn = TypeVar("TIn", contravariant=True)
TOut = TypeVar("TOut")
TNext = TypeVar("TNext")


class Stage(Protocol[TIn, TOut]):
    """
    One transition: one artefact in, the next one out.
    """

    name: str

    def run(self, artefact: TIn) -> TOut:
        """
        Transform the artefact.
        """

    def stamp(self, artefact: TOut) -> TOut:
        """
        Apply this boundary's `init_*_repro_data` hook.
        """


class Pipeline(Generic[TIn, TOut]):
    """
    Pipeline of stages, and the only place in the translator that stamps reprodata.
    Each stage is responsible for stamping its own output, 
    and the pipeline is responsible for calling that stamp method.
    """

    def __init__(self, stages: Sequence[Stage], repro: bool = True):
        """
        `repro`: can be set to False if no stamping is needed on the stages pipeline
        """
        self._stages = list(stages)
        self._repro = repro

    def then(self, stage: Stage[TOut, TNext]) -> "Pipeline[TIn, TNext]":
        """
        Return a new Pipeline with `stage` appended, re-typed to its output.
        """
        return Pipeline([*self._stages, stage], repro=self._repro)

    def run(self, artefact: TIn) -> TOut:
        """
        Run every stage in order. Any failure becomes a StageException.
        """
        for stage in self._stages:
            try:
                artefact = stage.run(artefact)
                if self._repro:
                    artefact = stage.stamp(artefact)
            except Exception as e:
                raise StageException(stage.name, str(e)) from e

        return artefact  # type: ignore
