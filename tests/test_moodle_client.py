import datetime as dt
import unittest
from unittest.mock import Mock

from src.services.moodle_client import MoodleClient


class MoodleClientTests(unittest.TestCase):
    def test_login_usa_post_y_no_url_query(self):
        client = MoodleClient("https://campus.test")
        response = Mock()
        response.json.return_value = {"token": "secret"}
        response.raise_for_status.return_value = None
        client.s.post = Mock(return_value=response)
        self.assertEqual(client.login("juan", "clave"), "secret")
        args, kwargs = client.s.post.call_args
        self.assertEqual(args[0], "https://campus.test/login/token.php")
        self.assertEqual(kwargs["data"]["password"], "clave")
        self.assertNotIn("params", kwargs)

    def test_eventos_se_paginan(self):
        client = MoodleClient("https://campus.test", "token")
        first = [{"id": index} for index in range(50)]
        client.ws = Mock(side_effect=[{"events": first}, {"events": [{"id": 101}]}])
        result = client.eventos_calendario(tamano_pagina=100)
        self.assertEqual(len(result["events"]), 51)
        self.assertEqual(client.ws.call_count, 2)
        self.assertEqual(client.ws.call_args_list[0].kwargs["limitnum"], 50)
        self.assertEqual(client.ws.call_args_list[1].kwargs["aftereventid"], 49)


if __name__ == "__main__":
    unittest.main()
