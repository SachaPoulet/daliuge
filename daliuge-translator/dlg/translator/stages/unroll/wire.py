#
#    ICRAR - International Centre for Radio Astronomy Research
#    (c) UWA - The University of Western Australia, 2015
#    Copyright by UWA (in the framework of the ICRAR)
#    All rights reserved
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston,
#    MA 02111-1307  USA
#
# These passes were lifted out of LG.unroll_to_tpl and still work on LG's
# own state; _WireContext adapts it to the handler context API.
# pylint: disable=protected-access
import collections
import logging
from functools import partial
from itertools import product

from dlg.translator.errors import GraphException
from dlg.translator.stages.unroll.constructs.registry import get_handler, is_construct
from dlg.translator.stages.unroll.link import (
    LinkContext,
    _is_stream_link,
    link_drops,
)
from dlg.translator.stages.unroll.model import LogicalLink
from dlg.translator.vocabulary import Categories

logger = logging.getLogger(f"dlg.{__name__}")


class _WireContext(LinkContext):
    """Expose the resolver context while retaining the legacy link state."""

    def __init__(self, lg):
        super().__init__(lg._session_id, lg._drop_dict["new_added"])
        self._nodes = lg._done_dict

    def node(self, node_id):
        return self._nodes[node_id]

    def chunk_size(self, source, target):
        return _get_chunk_size(source, target)

    def split(self, drops, size):
        return _split_list(drops, size)


def wire(lg):
    """
    Wire the drops in lg._drop_dict along every link in lg._lg_links.
    """
    # key - gather drop oid, value - [gather drop, input list, output list, link]
    #
    # A Gather drop is a placeholder: cleanup deletes it, and its inputs are
    # wired straight to its first output drop. Which output that is only
    # becomes known when a link out of the Gather is wired, so the inputs
    # are held here and spliced after every link has been wired.
    gathers = {}
    context = _WireContext(lg)
    link = partial(_link_or_defer, context, gathers)
    for lk in lg._lg_links:
        sid = lk["from"]  # source key
        tid = lk["to"]  # target key
        slgn = lg._done_dict[sid]
        tlgn = lg._done_dict[tid]
        sdrops = lg._drop_dict[sid]
        tdrops = lg._drop_dict[tid]
        chunk_size = _get_chunk_size(slgn, tlgn)
        if slgn.is_group and not tlgn.is_group:
            # this link must be artifically added (within group link)
            # since
            # 1. GroupBy's "natural" output must be a Scatter (i.e. group)
            # 2. Scatter "naturally" does not have output
            if (
                is_construct(slgn, Categories.GATHER) and tlgn.gid != sid
            ):  # not the artifical link between gather and its own start child
                # gather iteration case, tgt must be a Group-Start Component
                # this is a way to manually sequentialise a Scatter that has a high DoP
                for i, ga_drop in enumerate(sdrops):
                    if ga_drop["oid"] not in gathers:
                        logger.warning(
                            "Gather %s Drop not yet in cache, sequentialisation may fail!",
                            slgn.name,
                        )
                        continue
                    ga_inputs = gathers[ga_drop["oid"]][1]
                    if not ga_inputs:
                        # nothing to chain, and j would never advance
                        continue
                    j = (i + 1) * slgn.gather_width
                    if j >= tlgn.group.dop and j % tlgn.group.dop == 0:
                        continue
                    j_end = min((i + 2) * slgn.gather_width, tlgn.group.dop * (i + 1))
                    while j < j_end:
                        # TODO merge this code into link_drops.
                        tname = tlgn.getPortName(ports="inputPorts")
                        # Go through the gather's inputs
                        for gddrop in ga_inputs:
                            if j >= j_end:
                                break
                            gddrop.addConsumer(tdrops[j], name=tname)
                            tdrops[j].addInput(gddrop, name=tname)
                            j += 1

            elif is_construct(slgn, Categories.SUBGRAPH) or is_construct(
                tlgn, Categories.SUBGRAPH
            ):
                _resolve_subgraph_edges(
                    context,
                    link,
                    slgn,
                    tlgn,
                    sdrops,
                    tdrops,
                    lk,
                )
            else:
                # Matrix row 5 assigns this within-group fallback to Scatter.
                # Its source may be GroupBy or Gather; link() still creates
                # the physical connections through the common path.
                logical_link = LogicalLink(
                    source=slgn,
                    target=tlgn,
                    source_port=lk.get("fromPort"),
                    target_port=lk.get("toPort"),
                    is_stream=lk.get("is_stream", False),
                    loop_aware=("%s-%s" % (sid, tid)) in lg._loop_aware_set,
                )
                edges = get_handler(Categories.SCATTER).resolve_edges(
                    logical_link,
                    sdrops,
                    tdrops,
                    context,
                )
                for edge in edges:
                    link(slgn, tlgn, edge.source, edge.target, lk)
        elif slgn.is_group and tlgn.is_group:
            # slgn must be GroupBy and tlgn must be Gather
            _resolve_gather_edges(
                context,
                link,
                slgn,
                tlgn,
                sdrops,
                tdrops,
                lk,
            )
        elif not slgn.is_group and (not tlgn.is_group):
            if slgn.is_start_node:
                _resolve_leaf_edges(
                    context,
                    link,
                    slgn,
                    tlgn,
                    sdrops,
                    tdrops,
                    lk,
                    loop_aware=False,
                )
                continue
            if (
                (slgn.group is not None)
                and is_construct(slgn.group, Categories.LOOP)
                and slgn.gid == tlgn.gid
                and slgn.is_group_end
                and tlgn.is_group_start
            ):
                # Re-link to the next iteration's start
                lsd = len(sdrops)
                if lsd != len(tdrops):
                    raise GraphException(
                        "# of sdrops '{0}' != # of tdrops '{1}'for Loop '{2}'".format(
                            slgn.name, tlgn.name, slgn.group.name
                        )
                    )
                # first add the outer construct (scatter, gather, group-by) boundary
                loop_chunk_size = slgn.group.dop
                for i, chunk in enumerate(
                    _split_list(sdrops, loop_chunk_size)
                ):
                    for j, sdrop in enumerate(chunk):
                        if j < loop_chunk_size - 1:
                            link(
                                slgn,
                                tlgn,
                                sdrop,
                                tdrops[i * loop_chunk_size + j + 1],
                                lk,
                            )
            elif (
                slgn.group is not None
                and is_construct(slgn.group, Categories.LOOP)
                and tlgn.group is not None
                and is_construct(tlgn.group, Categories.LOOP)
                and (not slgn.h_related(tlgn))
            ):
                # stepwise locking for links between two Loops
                for sdrop, tdrop in product(sdrops, tdrops):
                    if sdrop["loop_ctx"] == tdrop["loop_ctx"]:
                        link(slgn, tlgn, sdrop, tdrop, lk)
            else:
                lpaw = ("%s-%s" % (sid, tid)) in lg._loop_aware_set
                if (
                    slgn.group is not None
                    and is_construct(slgn.group, Categories.LOOP)
                    and lpaw
                    and slgn.h_level > tlgn.h_level
                ):
                    loop_iter = slgn.group.dop
                    for i, chunk in enumerate(_split_list(sdrops, chunk_size)):
                        for j, sdrop in enumerate(chunk):
                            # only link drops in the last loop iteration
                            if j % loop_iter == loop_iter - 1:
                                link(slgn, tlgn, sdrop, tdrops[i], lk)
                elif (
                    tlgn.group is not None
                    and is_construct(tlgn.group, Categories.LOOP)
                    and lpaw
                    and slgn.h_level < tlgn.h_level
                ):
                    loop_iter = tlgn.group.dop
                    for i, chunk in enumerate(_split_list(tdrops, chunk_size)):
                        for j, tdrop in enumerate(chunk):
                            # only link drops in the first loop iteration
                            if j % loop_iter == 0:
                                link(slgn, tlgn, sdrops[i], tdrop, lk)

                else:
                    _resolve_leaf_edges(
                        context,
                        link,
                        slgn,
                        tlgn,
                        sdrops,
                        tdrops,
                        lk,
                        loop_aware=lpaw,
                    )
        else:  # slgn is not group, but tlgn is group
            if is_construct(tlgn, Categories.GROUP_BY):
                grpby_dict = collections.defaultdict(list)
                layer_index = tlgn.group_by_scatter_layers[1]
                for gdd in sdrops:
                    src_ctx = gdd["iid"].split("-")
                    if tlgn.group_keys is None:
                        # the last bit of iid (current h id) is the local GrougBy key, i.e. inner most loop context id
                        gby = src_ctx[-1]
                        if (
                            slgn.h_level - 2 == tlgn.h_level and tlgn.h_level > 0
                        ):  # groupby itself is nested inside a scatter
                            # group key consists of group context id + inner most loop context id
                            gctx = "-".join(src_ctx[0:-2])
                            gby = f"{gctx}-{gby}"
                    else:
                        # find the "group by" scatter level
                        gbylist = []
                        if is_construct(
                            slgn.group, Categories.GROUP_BY
                        ):  # a chain of group bys
                            try:
                                src_ctx = gdd["iid"].split("$")[1].split("-")
                            except IndexError as e:
                                raise GraphException(
                                    "The group by hiearchy in the multi-key group by '{0}' is not specified for node '{1}'".format(
                                        slgn.group.name, slgn.name
                                    )
                                ) from e
                        else:
                            src_ctx.reverse()
                        for lid in layer_index:
                            gbylist.append(src_ctx[lid])
                        gby = "-".join(gbylist)
                    grpby_dict[gby].append(gdd)
                grp_keys = grpby_dict.keys()
                if len(grp_keys) != len(tdrops):
                    # this happens when groupby itself is nested inside a scatter
                    raise GraphException(
                        "# of Group keys {0} != # of Group Drops {1} for LGN {2}".format(
                            len(grp_keys), len(tdrops), tlgn.id
                        )
                    )
                grp_keys = sorted(grp_keys)
                for i, gk in enumerate(grp_keys):
                    grpby_drop = tdrops[i]
                    drop_list = grpby_dict[gk]
                    for drp in drop_list:
                        link(slgn, tlgn, drp, grpby_drop, lk)
                        # drp.addOutput(grpby_drop)
                        # grpby_drop.addInput(drp)
            elif is_construct(tlgn, Categories.GATHER):
                _resolve_gather_edges(
                    context,
                    link,
                    slgn,
                    tlgn,
                    sdrops,
                    tdrops,
                    lk,
                )
            elif is_construct(tlgn, Categories.SUBGRAPH):
                _resolve_subgraph_edges(
                    context,
                    link,
                    slgn,
                    tlgn,
                    sdrops,
                    tdrops,
                    lk,
                )
            else:
                raise GraphException(
                    "Unsupported target group {0}".format(tlgn.jd.category)
                )

    for _, v in gathers.items():
        input_list = v[1]
        try:
            output_drop = v[2][0]  # "peek" the first element of the output list
        except IndexError:
            continue  # the gather hasn't got output drops, just move on
        llink = v[-1]
        for data_drop in input_list:
            # TODO merge this code into link_drops.
            sname = slgn.getPortName(ports="outputPorts")
            if llink.get("is_stream", False):
                logger.debug(
                    "link stream connection %s to %s",
                    data_drop["oid"],
                    output_drop["oid"],
                )
                data_drop.addStreamingConsumer(output_drop, name=sname)
                output_drop.addStreamingInput(data_drop, name=sname)
            else:
                data_drop.addConsumer(output_drop, name=sname)
                output_drop.addInput(data_drop, name=sname)

    logger.info(
        "Unroll progress - %d links done for session %s",
        len(lg._lg_links),
        lg._session_id,
    )


def _resolve_gather_edges(
    context,
    link,
    source,
    target,
    source_drops,
    target_drops,
    legacy_link,
):
    """Resolve edges into a Gather through the registered GatherHandler."""

    logical_link = LogicalLink(
        source=source,
        target=target,
        source_port=legacy_link.get("fromPort"),
        target_port=legacy_link.get("toPort"),
        is_stream=legacy_link.get("is_stream", False),
    )

    handler = get_handler(Categories.GATHER)
    edges = handler.resolve_edges(
        logical_link,
        source_drops,
        target_drops,
        context,
    )

    for edge in edges:
        link(
            source,
            target,
            edge.source,
            edge.target,
            legacy_link,
        )


def _resolve_subgraph_edges(
    context,
    link,
    source,
    target,
    source_drops,
    target_drops,
    legacy_link,
):
    """Resolve Subgraph edges through the registered SubgraphHandler."""

    logical_link = LogicalLink(
        source=source,
        target=target,
        source_port=legacy_link.get("fromPort"),
        target_port=legacy_link.get("toPort"),
        is_stream=legacy_link.get("is_stream", False),
    )

    handler = get_handler(Categories.SUBGRAPH)
    edges = handler.resolve_edges(
        logical_link,
        source_drops,
        target_drops,
        context,
    )

    for edge in edges:
        link(
            source,
            target,
            edge.source,
            edge.target,
            legacy_link,
        )


def _resolve_leaf_edges(
    context,
    link,
    source,
    target,
    source_drops,
    target_drops,
    legacy_link,
    loop_aware,
):
    """Resolve plain leaf edges through the registered LeafHandler."""

    logical_link = LogicalLink(
        source=source,
        target=target,
        source_port=legacy_link.get("fromPort"),
        target_port=legacy_link.get("toPort"),
        is_stream=legacy_link.get("is_stream", False),
        loop_aware=loop_aware,
    )

    handler = get_handler("leaf")
    edges = handler.resolve_edges(
        logical_link,
        source_drops,
        target_drops,
        context,
    )

    for edge in edges:
        link(
            source,
            target,
            edge.source,
            edge.target,
            legacy_link,
        )


def _link_or_defer(context, gathers, slgn, tlgn, src_drop, tgt_drop, llink):
    """
    link_drops, except that links into or out of a Gather are held in gathers
    instead of wired; see wire().
    """
    if is_construct(tlgn, Categories.GATHER):
        if is_construct(slgn, Categories.GROUP_BY):
            sdrop = src_drop["grp-data_drop"]
        elif is_construct(slgn, Categories.GATHER):
            sdrop = None
        else:
            sdrop = src_drop
        gather_oid = tgt_drop["oid"]
        if gather_oid not in gathers:
            gathers[gather_oid] = [tgt_drop, [], [], llink]
        gathers[gather_oid][1].append(sdrop)
        logger.debug(
            "Hit gather, link is from %s to %s", llink["from"], llink["to"]
        )
        return

    s_type = slgn.jd["categoryType"]
    t_type = tlgn.jd["categoryType"]
    if (
        is_construct(slgn, Categories.GATHER)
        and not _is_stream_link(s_type, t_type)
        and s_type not in ["Application", "Control"]
    ):
        gather_oid = src_drop["oid"]
        if gather_oid not in gathers:
            gathers[gather_oid] = [src_drop, [], [], llink]
        gathers[gather_oid][2].append(tgt_drop)
        if Categories.BASH_SHELL_APP == t_type:
            bc = tgt_drop["command"]
            bc.add_input_param(slgn.id, src_drop["oid"])
        return

    link_drops(context, slgn, tlgn, src_drop, tgt_drop, llink)


def _split_list(ls, n):
    """
    Yield successive n-sized chunks from l.
    """
    for i in range(0, len(ls), n):
        yield ls[i: i + n]


def _get_chunk_size(s, t):
    """
    Assumption:
    s or t cannot be Scatter as Scatter does not convert into DROPs
    """
    if is_construct(t, Categories.GATHER):
        ret = t.gather_width
    elif is_construct(t, Categories.GROUP_BY):
        ret = t.groupby_width
    else:
        ret = s.dop_diff(t)
    return ret
