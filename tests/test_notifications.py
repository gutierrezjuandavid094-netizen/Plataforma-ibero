import datetime as dt
import unittest

from src.services.notifications import due_notifications


class NotificationTests(unittest.TestCase):
    def test_elige_el_aviso_mas_cercano_sin_repetir(self):
        now = dt.datetime(2026, 8, 29, 10, 0)
        delivery = {"id": "a1", "fecha": now + dt.timedelta(minutes=10)}
        pending = due_notifications([delivery], [1440, 120, 15], {}, now)
        self.assertEqual(pending[0][:2], ("a1:15", 15))
        self.assertEqual(due_notifications([delivery], [15], {"a1:15": "sent"}, now), [])

    def test_ignora_vencidas(self):
        now = dt.datetime(2026, 8, 29, 10, 0)
        delivery = {"id": "a1", "fecha": now - dt.timedelta(minutes=1)}
        self.assertEqual(due_notifications([delivery], [15], {}, now), [])


if __name__ == "__main__":
    unittest.main()
