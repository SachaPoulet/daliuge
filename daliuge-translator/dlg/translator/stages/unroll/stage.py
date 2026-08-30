from __future__ import annotations

import logging
from dataclasses import dataclass

from dlg.common.reproducibility.reproducibility import init_pgt_unroll_repro_data
from dlg.translator.artefacts import LogicalGraphTemplate, PhysicalGraphTemplate
from dlg.translator.stages.unroll.lg import LG

logger = logging.getLogger(f"dlg.{__name__}")


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

    Spans prepare *and* unroll for now: `unroll` builds the `LG` itself, so the
    two are not separable until `LG.__init__` is split. The stage owns the
    `unroll` function as of the Tier 1 move; `pg_generator.unroll` is now a
    re-export of it for the engine and `web/`.
    """

    name = "unroll"

    def __init__(self, opts: UnrollOptions = UnrollOptions()):
        self._opts = opts

    def run(self, lgt: LogicalGraphTemplate) -> PhysicalGraphTemplate:
        """
        Delegate to the module-level `unroll` and wrap the drop list.
        """
        return PhysicalGraphTemplate.from_wire(
            unroll(lg=lgt.to_wire(),
                   oid_prefix=self._opts.oid_prefix,
                   zerorun=self._opts.zerorun,
                   app=self._opts.app)
        )

    def stamp(self, pgt: PhysicalGraphTemplate) -> PhysicalGraphTemplate:
        """
        The hook operates on the wire list, so the round trip happens here.

        `to_wire()` also hands it a copy, which matters: the hook annotates
        in place.
        """
        return PhysicalGraphTemplate.from_wire(
            init_pgt_unroll_repro_data(pgt.to_wire()))


def unroll(lg, oid_prefix=None, zerorun=False, app=None):
    """Unrolls a logical graph"""
    lg = LG(lg, ssid=oid_prefix)
    drop_list = lg.unroll_to_tpl()
    if zerorun:
        for dropspec in drop_list:
            if "sleep_time" in dropspec:
                dropspec["sleep_time"] = 0
    if app:
        logger.info("Replacing apps with %s", app)
        for dropspec in drop_list:
            if "dropclass" in dropspec and dropspec["categoryType"] == "Application":
                dropspec["dropclass"] = app
                dropspec["sleep_time"] = (
                    dropspec["execution_time"] if "execution_time" in dropspec else 2
                )
    drop_list.append(lg.reprodata)
    return drop_list
