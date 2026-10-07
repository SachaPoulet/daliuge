import unittest
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import Mock, patch

import dlg.translator.stages.unroll.instantiate as instantiate_module
from dlg.translator.vocabulary import Categories


class TestServiceHandlerInstantiationRouting(unittest.TestCase):

    def test_group_service_routes_through_service_handler(self):
        service = SimpleNamespace(
            id="service",
            category=Categories.SERVICE,
            is_group=True,
            jd={"category": Categories.SERVICE},
            group_keys=None,
            dop=1,
            children=[],
        )

        drops = defaultdict(list)
        graph = SimpleNamespace(
            _session_id="session",
            _done_dict={"service": service},
            _drop_dict=drops,
        )

        handler = Mock()
        handler.instantiate.return_value = [{"oid": "service-drop"}]

        with patch.object(
            instantiate_module,
            "get_handler_for_node",
            return_value=handler,
        ):
            instantiate_module.lgn_to_pgn(graph, service)

        handler.instantiate.assert_called_once()
        self.assertEqual(
            [{"oid": "service-drop"}],
            drops["service"],
        )


if __name__ == "__main__":
    unittest.main()
