#
#    ICRAR - International Centre for Radio Astronomy Research
#    (c) UWA - The University of Western Australia, 2026
#    Copyright by UWA (in the framework of the ICRAR)
#    All rights reserved
#

"""Graph linearisation for partition algorithms that require sequential edges."""

from dlg.common import CategoryType, dropdict


def linearise(drop_list, dag, gojs_key_dict):
    """Insert intermediate DROPs between adjacent DROPs of the same type.

    Returns the synthetic DROPs and the corresponding edge projection while
    mutating the DAG in the same way as the legacy PGT serialiser.
    """

    extra_drops = []
    links = []
    remove_edges = []
    add_edges = []
    add_nodes = []

    for drop in drop_list:
        oid = drop["oid"]
        source_key = gojs_key_dict[oid]

        for index, target_key in enumerate(dag.successors(source_key)):
            link = {
                "from": source_key,
            }

            source_type = (
                0
                if drop["categoryType"] in [CategoryType.DATA, "data"]
                else 1
            )
            target_type = dag.nodes[target_key]["drop_type"]

            if source_type == target_type:
                target_drop = dag.nodes[target_key]["drop_spec"]

                if source_type == 0:
                    extra_oid = "{0}_TransApp_{1}".format(oid, index)
                    extra_drop = dropdict(
                        {
                            "oid": extra_oid,
                            "categoryType": CategoryType.APPLICATION,
                            "dropclass": "dlg.drop.BarrierAppDROP",
                            "name": "go_app",
                            "weight": 1,
                        }
                    )

                    drop.addConsumer(extra_drop)
                    extra_drop.addInput(drop)
                    extra_drop.addOutput(target_drop)
                    target_drop.addProducer(extra_drop)
                    extra_type = 1
                else:
                    extra_oid = "{0}_TransData_{1}".format(oid, index)
                    extra_drop = dropdict(
                        {
                            "oid": extra_oid,
                            "categoryType": CategoryType.DATA,
                            "dropclass": (
                                "dlg.data.drops.memory.InMemoryDROP"
                            ),
                            "name": "go_data",
                            "weight": 1,
                        }
                    )

                    drop.addOutput(extra_drop)
                    extra_drop.addProducer(drop)
                    extra_drop.addConsumer(target_drop)
                    target_drop.addInput(extra_drop)
                    extra_type = 0

                extra_drops.append(extra_drop)
                extra_key = len(extra_drops) * -1

                link["to"] = extra_key
                links.append(
                    {
                        "from": extra_key,
                        "to": target_key,
                    }
                )

                add_nodes.append(
                    (
                        extra_key,
                        1,
                        extra_type,
                        extra_drop,
                        dag.nodes[target_key].get("gid", None),
                    )
                )
                remove_edges.append((source_key, target_key))
                add_edges.append((source_key, extra_key))
                add_edges.append((extra_key, target_key))
            else:
                link["to"] = target_key

            links.append(link)

    for node in add_nodes:
        dag.add_node(
            node[0],
            weight=node[1],
            drop_type=node[2],
            drop_spec=node[3],
            gid=node[4],
        )

    dag.remove_edges_from(remove_edges)
    dag.add_edges_from(add_edges)

    return extra_drops, links
