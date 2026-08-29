import unittest

from src.utils.utils_sys import UtilsSys


class UtilsTests(unittest.TestCase):
    def test_normaliza_url_de_login(self):
        self.assertEqual(
            UtilsSys.normalizar_url("campus.ibero.edu.co/login/index.php?x=1"),
            "https://campus.ibero.edu.co",
        )

    def test_rechaza_http_remoto(self):
        self.assertFalse(UtilsSys.url_es_segura("http://campus.example.com"))
        self.assertTrue(UtilsSys.url_es_segura("http://localhost:8000"))
        self.assertTrue(UtilsSys.url_es_segura("https://campus.example.com"))

    def test_extrae_solo_teams(self):
        links = UtilsSys.extraer_links_teams(
            "Clase https://teams.microsoft.com/l/meetup-join/abc y https://evil.test/x"
        )
        self.assertEqual(links, ["https://teams.microsoft.com/l/meetup-join/abc"])

    def test_limpia_html(self):
        self.assertEqual(UtilsSys.limpiar_html("<p>Hola&nbsp; mundo</p>"), "Hola mundo")


if __name__ == "__main__":
    unittest.main()
