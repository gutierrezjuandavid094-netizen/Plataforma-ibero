import datetime as dt
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
import src.services.storage as storage
from src.ui.main_window import Ventana


class UiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [
            patch.object(storage, "CONFIG_FILE", root / "config.json"),
            patch.object(storage, "TOKEN_FILE", root / "tokens.json"),
            patch.object(storage, "CACHE_FILE", root / "cache.json"),
            patch.object(storage, "STATE_FILE", root / "state.json"),
            patch.object(storage, "LEGACY_CONFIG_FILE", root / "legacy.json"),
            patch.object(storage.SecureTokenStore, "_keyring", return_value=None),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_ventana_y_datos(self):
        window = Ventana()
        now = dt.datetime.now() + dt.timedelta(hours=2)
        window._aplicar_resultado({
            "entregas": [{
                "id": "event:1", "curso": "Pruebas", "titulo": "Tarea",
                "tipo": "Tarea", "fecha": now, "descripcion": "Detalle", "url": "",
            }],
            "reuniones": [], "calificaciones": [],
            "cursos": [{"id": 1, "nombre": "Pruebas", "progreso": 50, "finalizado": False}],
            "diagnosticos": [], "perfil": {"nombre": "Juan"},
        }, desde_cache=True)
        self.assertEqual(window.tabs.count(), 7)
        self.assertEqual(window.card_proxima.text().splitlines()[0], "Tarea")
        self.assertEqual(window.arbol_cursos.topLevelItemCount(), 1)
        window.close()


if __name__ == "__main__":
    unittest.main()
