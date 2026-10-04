#
#    ICRAR - International Centre for Radio Astronomy Research
#    (c) UWA - The University of Western Australia, 2026
#    Copyright by UWA (in the framework of the ICRAR)
#    All rights reserved
#

import unittest

from dlg.translator.web.translator_utils import filter_dict_to_algo_params


class TestAlgorithmParameterFiltering(unittest.TestCase):
    def test_metis_filters_unrelated_legacy_parameters(self):
        params = {
            "max_load_imb": 100,
            "max_cpu": 8,
            "topk": 30,
        }

        self.assertEqual(
            filter_dict_to_algo_params(params, "metis"),
            {
                "max_load_imb": 100,
            },
        )

    def test_mysarkar_filters_unrelated_legacy_parameters(self):
        params = {
            "max_load_imb": 100,
            "max_cpu": 8,
            "max_mem": 512,
        }

        self.assertEqual(
            filter_dict_to_algo_params(params, "mysarkar"),
            {
                "max_cpu": 8,
                "max_mem": 512,
            },
        )

    def test_filter_without_algorithm_preserves_legacy_behaviour(self):
        params = {
            "max_load_imb": 100,
            "max_cpu": 8,
        }

        self.assertEqual(
            filter_dict_to_algo_params(params),
            params,
        )


if __name__ == "__main__":
    unittest.main()
