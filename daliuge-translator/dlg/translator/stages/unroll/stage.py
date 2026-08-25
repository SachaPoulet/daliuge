from dataclasses import dataclass
from dlg.translator.artefacts import LogicalGraphTemplate, PhysicalGraphTemplate
from dlg.dropmake.pg_generator import unroll
from dlg.common.reproducibility.reproducibility import init_pgt_unroll_repro_data


@dataclass(frozen=True)
class UnrollOptions:
    """
    Options for unroll algorithm.

    `oid_prefix`: becomes the session id every generated OID is prefixed with.

    `zerorun`: Sets sleep_time = 0 on any dropspec that has one.

    `app`: Dropclass string. Replaces dropclass on every Application drop,
    and overwrites its sleep_time from execution_time (or 2).
    """

    oid_prefix: str | None = None
    zerorun: bool = False
    app: str | None = None


class UnrollStage:
    """
    LGT -> PGT.

    Spans prepare *and* unroll for now: `pg_generator.unroll` builds the `LG`
    itself, so the two are not separable until Phase 2 splits `LG.__init__`.
    Phase 1 only wraps -- no logic moves here.
    """

    name = "unroll"

    def __init__(self, opts: UnrollOptions = UnrollOptions()):
        self._opts = opts

    def run(self, lgt: LogicalGraphTemplate) -> PhysicalGraphTemplate:
        """
        Delegate to `pg_generator.unroll` and wrap the drop list.
        """
        return PhysicalGraphTemplate.from_wire(
            unroll(lgt.source, self._opts.oid_prefix,
                   zerorun=self._opts.zerorun, app=self._opts.app))

    def stamp(self, pgt: PhysicalGraphTemplate) -> PhysicalGraphTemplate:
        """
        The hook operates on the wire list, so the round trip happens here.

        `to_wire()` also hands it a copy, which matters: the hook annotates
        in place.
        """
        return PhysicalGraphTemplate.from_wire(
            init_pgt_unroll_repro_data(pgt.to_wire()))
