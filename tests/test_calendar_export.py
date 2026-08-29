import datetime as dt
import unittest

from src.services.calendar_export import build_ics, google_calendar_url, outlook_calendar_url


class CalendarExportTests(unittest.TestCase):
    def setUp(self):
        self.delivery = {
            "id": "event:1", "tipo": "Quiz", "titulo": "Evaluación final",
            "curso": "Programación", "descripcion": "Resolver ejercicios",
            "fecha": dt.datetime(2026, 9, 1, 18, 0), "url": "https://campus.test/mod/quiz/1",
        }

    def test_ics_contiene_evento_y_alarma(self):
        content = build_ics([self.delivery])
        self.assertIn("BEGIN:VEVENT", content)
        self.assertIn("SUMMARY:Quiz: Evaluación final", content)
        self.assertIn("BEGIN:VALARM", content)

    def test_urls_de_calendarios(self):
        self.assertTrue(google_calendar_url(self.delivery).startswith("https://calendar.google.com/"))
        self.assertTrue(outlook_calendar_url(self.delivery).startswith("https://outlook.live.com/"))


if __name__ == "__main__":
    unittest.main()
