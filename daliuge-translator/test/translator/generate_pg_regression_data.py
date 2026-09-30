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

import sys
import json
import pickle


from dlg.translator.stages.unroll.lg import LG
from dlg.translator.stages.partition.pgt import PGT
from dlg.translator.stages.partition.pgtp import MetisPGTP
from dlg.common import path_utils

TEST_SSID = 'test_pg_gen'















if __name__ == '__main__':
    """
    Used to generate the pickle and logical graph files used for testing.

    IMPORTANT: Run this _only_ when the expected output of unroll_to_tpl has been 
    _knowingly_ changed. 
    """
    try:
        arg = sys.argv[1]
        if arg.lower() == "test-gen":
            print("\nRunning test dataset generator on following logical graphs:")
    except IndexError:
        print("You have run the dataset generator for this test suite.\n"
              "\n"
              "This may have been done by accident: if so, double check the unitttest "
              "directive is used when running the file.\n"
              "\n"
              "If this was a deliberate effort to update the test cases due to a known "
              "change in the translator, please use the 'test-gen' argument. "
              "Please ensure that the changes are necessary, as this suite provides"
              "essential regression testing for translator behaviour.")
        exit()

    pickle_dir = "pickle"
    physical_graph_spec = "pg_spec"
    lgnames = [
        "HelloWorld_simple.graph",
        "eagle_gather_empty_update.graph",
        "eagle_gather_simple_update.graph",
        "eagle_gather_update.graph",
        "testLoop.graph",
        "cont_img_mvp.graph",
        "test_grpby_gather.graph",
        "chiles_simple.graph",
        "Plasma_test.graph",
        "SharedMemoryTest_update.graph",
        "test_ports.graph",
        "pyfunc_glob_shell_test.graph"
        # "simpleMKN_update.graph", # Currently broken
    ]

    for lg_name in lgnames:
        print('\t', lg_name)
        fp = path_utils.get_lg_fpath('logical_graphs', lg_name)
        lg = LG(fp, ssid=TEST_SSID)

        lg_unroll = lg.unroll_to_tpl()
        pkl_path = path_utils.get_lg_fpath("pickle", lg_name)
        with open(pkl_path, 'wb') as fp:
            pickle.dump(lg_unroll, fp)

        pgt = PGT(lg_unroll)
        pg_json = pgt.to_gojs_json(visual=True, string_rep=False)
        pg_path = path_utils.get_lg_fpath("go_js_json", lg_name)

        with open(pg_path, 'w') as fp:
            json.dump(pg_json, fp, indent=2)

        node_list = [
            "10.128.0.11",
            "10.128.0.12",
            "10.128.0.13",
            "10.128.0.14",
            "10.128.0.15",
            "10.128.0.16",
        ]
        pgtp = MetisPGTP(lg_unroll,merge_parts=True)
        pgtp.to_gojs_json(visual=True, string_rep=False)
        pg_spec = pgtp.to_pg_spec(node_list=node_list, num_islands=1, ret_str=False)
        fn_spec = lg_name.split('.')[0] + '.spec'
        drop_spec_path = path_utils.get_lg_fpath("drop_spec", lg_name)
        with open(drop_spec_path, 'w') as fp:
            json.dump(pg_spec, fp, indent=2)